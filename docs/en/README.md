# 🤖 AssistantApiPlatform

In plain terms — this gives you a ready-made backend for an AI chat assistant: something that remembers conversations, handles many requests at once without stalling, and keeps a record of every reply it produces, so you don't have to build all of that yourself. You bring the AI model; AssistantApiPlatform takes care of everything around it.

An **OpenAI Assistants API–compatible** backend — assistants, threads, messages and runs — built with FastAPI, backed by Postgres, dispatched through a Redis-Stream task queue (TaskIQ), and traced end-to-end with MLflow.

Bring your own OpenAI-compatible LLM server (vLLM, SGLang, ...); AssistantApiPlatform handles persistence, conversation state, background generation, streaming, and observability around it.

<br />

## Key Features

- **OpenAI Assistants API compatibility** — `assistants`, `threads`, `messages`, `runs` with the same resource shapes and semantics as the OpenAI SDK (`client.beta.threads...`), including `create_thread_and_run`
- **Background generation** — non-streaming runs are dispatched to a TaskIQ worker over Redis Streams instead of blocking the request; the run row is written synchronously before the response returns, so a client can `GET` the run immediately without racing the queue
- **Streaming** — streaming runs skip the queue entirely and generate Server-Sent Events inline on the request task
- **Redelivery-safe by design** — Redis Streams consumer-group redelivery is expected, not avoided: run/message inserts use `ON CONFLICT DO NOTHING`, and a run already in a terminal state is never reprocessed
- **Full observability** — every generation is an MLflow span tagged with `thread_id`/`run_id`/`message_id`/`assistant_id`, with token usage and latency recorded as span attributes; artifacts land in MinIO (S3-compatible)
- **Config layering** — environment variables for infrastructure/secrets (`.env`), TOML for static interaction parameters (`config/config.toml`), Python defaults as the final fallback

<br />

## Prerequisite: LLM Serving Backend

AssistantApiPlatform does not run inference itself — it forwards chat completions to an external **OpenAI-compatible** serving endpoint (e.g. [vLLM](https://github.com/vllm-project/vllm) or [SGLang](https://github.com/sgl-project/sglang)) and does everything else (persistence, threading, background dispatch, tracing) around it. See [framework_benchmarks.md](../framework_benchmarks.md) for a vLLM vs SGLang comparison on Qwen3 models.

Point `LLM_BASE_URL` (below) at any server that implements `POST /v1/chat/completions`.

<br />

## Installation

```bash
git clone https://github.com/nlp4everyone/AssistantApiPlatform.git
cd AssistantApiPlatform/
cp .env.sample .env
```

Configure the external LLM server in `.env`:
```
LLM_MODEL_NAME=Qwen/Qwen3-4B-AWQ
LLM_BASE_URL=http://172.17.0.1:8100/v1
SERVING_API_KEY=token
```

> Infrastructure/secrets (ports, DB credentials, LLM endpoint) live in `.env` (not version-controlled). The inbound API key (`FASTAPI_API_KEY`) and static interaction params live in `config/config.toml` (version-controlled). See [CONFIGURATION.md](../CONFIGURATION.md).

Run with Docker Compose:
```bash
make up      # build + start postgres, redis, web, worker, mlflow, minio
make logs    # tail web + worker logs
make ps      # service status
make down    # stop everything
```

The API is served at `http://localhost:8005/v1`; MLflow tracking UI at `http://localhost:5000`.

<br />

## Quick Start (Python Client)

AssistantApiPlatform implements the same resource shapes as the OpenAI Assistants API, so the official `openai` Python SDK works unmodified — just point `base_url` at AssistantApiPlatform and use any bearer token matching `FASTAPI_API_KEY`.

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8005/v1", api_key="token")

assistant = client.beta.assistants.create(
    name="Math Tutor",
    model="Qwen/Qwen3-4B-AWQ",
    instructions="You are a personal math tutor.",
)

run = client.beta.threads.create_and_run(
    assistant_id=assistant.id,
    thread={"messages": [{"role": "user", "content": "Explain deep learning to a 5 year old."}]},
    stream=False,
)

while run.status in ("queued", "in_progress"):
    run = client.beta.threads.runs.retrieve(run_id=run.id, thread_id=run.thread_id)

for msg in client.beta.threads.messages.list(thread_id=run.thread_id).data:
    print(msg.role, msg.content)
```

The `examples/` directory has runnable scripts for each resource:

```bash
python examples/assistant_example.py
python examples/thread_example.py
python examples/message_example.py
python examples/run_example.py
python examples/streaming_run_example.py
```

<br />

## Integrations

- **API framework**: FastAPI
- **LLM client**: OpenAI Python SDK (`AsyncOpenAI`), pointed at any OpenAI-compatible serving backend
- **Persistence**: PostgreSQL (`asyncpg`) — assistants, threads, messages, runs
- **Task queue**: Redis Streams via [TaskIQ](https://taskiq-python.github.io/) — background generation, at-least-once delivery with a consumer group
- **Observability**: MLflow (tracing, token usage, latency) + MinIO (S3-compatible artifact store)
- **Runtime**: Docker Compose (`docker/compose_db.yml` + `compose_web.yml` + `compose_tracking.yml`, combined via `Makefile`)

<br />

## Documentation

- [Technical Overview](TECHNICAL_OVERVIEW.md) — architecture diagram, HTTP endpoints, request flow at a glance
- [Detailed Flow](FLOW.md) — step-by-step create-run → dispatch → background worker → completion, including the redelivery/idempotency path
- [Detailed Components](DETAILED_COMPONENTS.md) — router/service/store breakdown
- [Design Decisions](DESIGN_DECISIONS.md) — rationale, trade-offs, and alternatives considered for each major choice
- [Configuration Reference](../CONFIGURATION.md) — every config parameter, its source, and its default

<br />

## Known Limitations / Roadmap

### ✅ Implemented
- [x] Assistants, threads, messages, runs (CRUD + list with cursor pagination)
- [x] Background (queued) and streaming (SSE) run execution
- [x] MLflow tracing with token usage + latency per generation

<br />

## Model Citation

Default example model: **Qwen3** — https://huggingface.co/Qwen
