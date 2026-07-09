# AssistantApiPlatform — OpenAI Assistants API–compatible Backend

Production-oriented backend implementing the OpenAI Assistants resource model, using:

- FastAPI (`app/app.py`) as the API layer
- PostgreSQL (`asyncpg`) for assistants/threads/messages/runs
- Redis Streams + TaskIQ for background generation, consumer-group redelivery
- An external OpenAI-compatible LLM server (vLLM/SGLang/...) for actual inference
- MLflow (traces, token usage, latency) + MinIO (S3-compatible artifact store) for observability

---

# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         CLIENT (openai Python SDK)                       │
│         client.beta.{assistants,threads,messages}... / Bearer token      │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ HTTP  /v1/...
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Application  (app/app.py)                    │
│   verify_api_key (Bearer)  ·  ID-prefix path validators  ·  routers      │
└───┬─────────────┬─────────────────┬─────────────────┬────────────────────┘
    │              │                 │                 │
    ▼              ▼                 ▼                 ▼
assistant_router  thread_router   message_router    run_router
    │              │                 │                 │
    ▼              ▼                 ▼                 ▼
AssistantService  ThreadService   MessageService   RunDispatchService
    │              │                 │                 │
    └──────────────┴────────┬────────┴─────────────────┘
                            ▼
                  PostgresXxxStore (asyncpg pool)
                  assistants · threads · messages · runs
                            │
              ┌─────────────┴──────────────┐
              │ request.stream == True?    │
              ▼ NO                         ▼ YES
   run_background_llm.kiq(...)     handle_streaming_response()
   (enqueue to Redis Stream)       (runs inline on the request task)
              │                             │
              ▼                             │
┌──────────────────────────────┐            │
│   TaskIQ Worker (separate    │            │
│   container, consumer group) │            │
│   run_background_llm task    │            │
└──────────────┬────────────────┘           │
               └─────────────┬───────────────┘
                             ▼
              prepare_generation_context()
              (idempotent create_run, prepare_messages)
                             │
                             ▼
              AsyncOpenAI.chat.completions.create()
              ──▶ external LLM server (vLLM/SGLang/...)
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
      MLflow span (tags, usage,   persist_and_complete() /
      latency) ──▶ MinIO (S3)     fail_run() ──▶ Postgres
```

## Request Flow at a Glance

**Stage 1 — Auth + validation**

Every route (except health/docs) depends on `verify_api_key`, which checks a static `Authorization: Bearer <FASTAPI_API_KEY>` header. Path parameters that reference an object ID (`thread_id`, `assistant_id`, `message_id`, `run_id`) are validated against that object's ID prefix (`thread_`, `asst_`, `msg_`, `run_`) before the handler body runs.

**Stage 2 — Create thread / create-and-run**

`POST /v1/threads/runs` (create-and-run) generates the run/step/message IDs up front, creates the thread and tags its seed messages with `run_id` in one call, then hands off to the same `RunDispatchService.create_and_dispatch_run` used by `POST /v1/threads/{id}/runs`. This keeps the two entry points from drifting apart. See [FLOW.md](FLOW.md) for the exact sequence, including the fix that makes the run row visible to `GET` before the response is even returned.

**Stage 3 — Dispatch: queue or stream**

- **Non-streaming** (`stream` unset or `false`): the run row is created, a `run_background_llm` task is enqueued on the Redis Stream, and a `queued` `RunObject` is returned immediately. Generation happens later, out of the request/response cycle.
- **Streaming** (`stream: true`): no task is enqueued — `handle_streaming_response` runs the same context-preparation step inline and yields Server-Sent Events directly on the request task.

**Stage 4 — Generation**

Both paths converge on the same building blocks (`app/services/common/`): `prepare_generation_context` (idempotent run-row creation + message history assembly), `build_chat_request` (OpenAI-format messages + kwargs), an MLflow span around the actual `chat.completions.create` call, and `persist_and_complete` (assistant message insert + usage + `completed` status) or `fail_run` (`failed` status) on error.

**Stage 5 — Redelivery safety**

The TaskIQ worker acknowledges a message only after the task returns. If the worker process dies mid-task, Redis' consumer group redelivers the message (`idle_timeout`, default 10 minutes) to another consumer. Every write on that path — run creation, seed-message insert, generated-message insert — is `ON CONFLICT (id) DO NOTHING`, and a run already in a terminal status is never regenerated. See [FLOW.md](FLOW.md) and [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

> For exact function names and call order: [FLOW.md](FLOW.md)

---

# HTTP Endpoints

All routes are prefixed with `/v1` and require `Authorization: Bearer <FASTAPI_API_KEY>`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/assistants` | Create an assistant |
| `GET` | `/assistants` | List assistants (cursor pagination) |
| `GET` | `/assistants/{assistant_id}` | Retrieve an assistant |
| `DELETE` | `/assistants/{assistant_id}` | Delete an assistant |
| `POST` | `/threads` | Create a thread (optionally seeded with messages) |
| `GET` | `/threads/{thread_id}` | Retrieve a thread |
| `DELETE` | `/threads/{thread_id}` | Delete a thread (cascades messages/runs) |
| `POST` | `/threads/runs` | Create a thread **and** run it in one call |
| `POST` | `/threads/{thread_id}/runs` | Create a run on an existing thread |
| `GET` | `/threads/{thread_id}/runs` | List runs on a thread |
| `GET` | `/threads/{thread_id}/runs/{run_id}` | Retrieve a run |
| `POST` | `/threads/{thread_id}/messages` | Create a message |
| `GET` | `/threads/{thread_id}/messages` | List messages (optionally filtered by `run_id`) |
| `GET` | `/threads/{thread_id}/messages/{message_id}` | Retrieve a message |
| `DELETE` | `/threads/{thread_id}/messages/{message_id}` | Delete a message |

Not implemented yet: run cancellation, run steps as a first-class resource, file uploads. See [README.md](README.md#known-limitations--roadmap).

---

# Background Worker

| | |
|---|---|
| Queue | Redis Streams (`RedisStreamBroker`, consumer group `taskiq`) |
| Task | `run_background_llm` (`taskiq_worker.py`) |
| Container | `taskiq_worker`, `restart: always`, healthcheck pings Redis every 15s |
| Redelivery window | `idle_timeout` = 10 minutes (broker default) before an unacked message is reclaimed |
| Concurrency | Single replica by default; TaskIQ's consumer-group model supports more without code changes |

---

# Configuration

See [CONFIGURATION.md](../CONFIGURATION.md) for the full parameter reference: `.env` (infra/secrets) vs `config/config.toml` (static params) vs code defaults.

---

> For component internals and API reference: [DETAILED_COMPONENTS.md](DETAILED_COMPONENTS.md)
