# Design Decisions

This document explains the rationale behind each major architectural choice, including trade-offs and alternatives considered.

---

## 1. Background Execution — TaskIQ + Redis Streams

### Description

Non-streaming runs are dispatched as a `run_background_llm` task on a `RedisStreamBroker` (TaskIQ), consumed by a separate `taskiq_worker` container via a consumer group, instead of generating inline on the request task.

### Pros

- **Request latency is decoupled from LLM latency** — the client gets a `queued` `RunObject` immediately; a slow generation doesn't hold an HTTP connection open
- **Redis Streams gives a durable, replayable log with consumer groups** — cheaper to operate than RabbitMQ/Kafka for this scale, and TaskIQ's `taskiq-redis` package integrates directly
- **Horizontal scaling is just more consumers in the same group** — no code change needed to add worker replicas

### Cons

- **At-least-once, not exactly-once delivery** — a worker crash after partial work means the task can be redelivered; the app has to be idempotent itself (see §2)
- **One more moving part in production** — Redis and the worker container are both now on the critical path for background generation, each needing its own monitoring

### Alternatives considered

| Option | Reason not chosen |
|---|---|
| Celery + RabbitMQ | Heavier operational footprint for a single task type; TaskIQ's async-native API fits the existing `asyncpg`/`AsyncOpenAI` stack directly |
| In-process `asyncio.create_task` | No durability — a process restart silently drops in-flight generations; no multi-instance fan-out |
| Synchronous generation (no queue) | Blocks the request for the full LLM latency; doesn't match the OpenAI Assistants API's `queued`/`in_progress` run lifecycle |

---

## 2. Idempotent Writes Instead of Exactly-Once Delivery

### Description

Rather than trying to prevent redelivery (distributed locks, dedup tables with TTLs), every write on the generation path is made safe to repeat: `PostgresRunStore.create_run` and `PostgresMessageStore.insert_messages` use `ON CONFLICT (id) DO NOTHING`, and `generation_worker.handle_generation_response` checks `TERMINAL_RUN_STATUSES` before doing any work.

### Pros

- **No coordination overhead** — no distributed lock, no separate dedup store to keep consistent with Postgres
- **Correct under the broker's actual guarantee** — Redis Streams' consumer-group redelivery (`idle_timeout`, default 10 minutes, via `XAUTOCLAIM`) is a normal operational event here, not an outage
- **Cheap to reason about** — the same run/message ID always maps to the same row; a redelivered task either no-ops or completes work the first attempt never reached

### Cons

- **A duplicated LLM call is still possible** — if the worker dies *after* the LLM responds but *before* `update_run_status(COMPLETED)` commits, a redelivery will call the LLM again (see §3 for why this specific gap isn't closed)
- **Relies on every insert on this path remembering `ON CONFLICT`** — a new insert added later without it would silently reintroduce duplication risk under redelivery

### Alternatives considered

| Option | Reason not chosen |
|---|---|
| Distributed lock per `run_id` (Redis `SETNX`) | Adds a second failure mode (lock expiry vs task duration) for a problem `ON CONFLICT DO NOTHING` already solves at the data layer |
| Dedup table keyed by task ID | Extra table + cleanup job; `ON CONFLICT` on the actual domain rows is simpler and doesn't need cleanup |

---

## 3. Run Row Created Synchronously, Before Dispatch

### Description

`RunDispatchService.create_and_dispatch_run` calls `PostgresRunStore.create_run` itself, before enqueueing the task or returning the response. Previously this insert only happened inside `prepare_generation_context`, i.e. after the worker had already dequeued the task — so a client that called `GET /runs/{run_id}` immediately after create could get a 404 for a run the API had just told it was `queued`, if the worker hadn't picked up the task yet (queue backlog, worker restart, etc.).

### Pros

- **No GET-after-create race** — by the time the response leaves the server, the row is committed; any subsequent read sees it
- **The worker's own `create_run` call becomes a harmless, idempotent safety net** (`ON CONFLICT DO NOTHING`) rather than the only writer — no behavior changes for the normal, fast path

### Cons

- **One extra synchronous DB round-trip on the request path** — negligible compared to enqueueing + the eventual LLM call, but it is on the critical path now instead of fully offloaded to the worker

### Alternatives considered

| Option | Reason not chosen |
|---|---|
| Return `status: "queued"` without a row, document the eventual-consistency window | Silently wrong relative to the OpenAI Assistants API contract, where a returned run ID is immediately retrievable |
| Have the client retry `GET` with backoff | Pushes a server-side bug onto every client integration instead of fixing it once |

---

## 4. Two Execution Paths Sharing One Context-Preparation Step

### Description

Non-streaming (background worker) and streaming (inline SSE) runs both call `prepare_generation_context` and the same `build_chat_request` / span-tagging / `persist_and_complete` / `fail_run` helpers in `app/services/common/`, rather than each path reimplementing message assembly and persistence.

### Pros

- **The two paths cannot silently diverge** — a bug fix or schema change to message preparation applies to both automatically
- **Streaming skips the queue entirely** — no artificial latency from enqueue/dequeue for a request that's already going to hold the connection open

### Cons

- **Streaming has no redelivery/idempotency safety net** — if the request connection drops mid-stream, there's no consumer group to redeliver the work; the client must retry the whole call. This is an accepted trade-off since SSE is inherently tied to one connection's lifetime.

---

## 5. ID Scheme — Prefixed UUID Suffix

### Description

Every resource ID is `f"{prefix}_{uuid4().hex[:24]}"` (`asst_...`, `thread_...`, `msg_...`, `run_...`, `step_...`), validated against its expected prefix at the FastAPI path-parameter layer before the handler runs.

### Pros

- **Matches the OpenAI Assistants API's own ID shape** — client code and tooling built against the real API needs no ID-format changes
- **Self-describing and fail-fast** — a `thread_id` accidentally passed where a `run_id` is expected is rejected with a 400 at the edge, not a confusing not-found several calls deep
- **No coordination needed to generate an ID** — no auto-increment sequence, no round-trip to the DB before an ID exists (this is what enables the synchronous-yet-early ID generation in §3)

### Cons

- **24 hex chars of a UUID4, not the full 32** — a (very small, effectively negligible at expected scale) increase in collision probability over a full UUID

---

## 6. Config Layering — Env Vars vs TOML vs Code Defaults

### Description

Infrastructure and secrets (ports, Postgres/MinIO/MLflow credentials, the external LLM endpoint) come from `.env` (`os.getenv`, not version-controlled). A small set of static values — the inbound `FASTAPI_API_KEY`, `REDIS_URL`, and interaction params like `NUMS_OF_PREVIOUS_INTERACTION` — come from `config/config.toml` (version-controlled) via a dedicated `TomlConfigLoader`, independent of the environment.

### Pros

- **Secrets never need to be committed** — `.env` is gitignored; `config/config.toml`'s committed defaults are non-sensitive
- **TOML values are reviewable in a diff** — a change to `NUMS_OF_PREVIOUS_INTERACTION` shows up in `git log`, unlike an env var change on a server

### Cons — a real gotcha in the current setup

- **`config/config.toml`'s `REDIS_URL` has no environment-variable override.** `app/core/config/redis.py` reads it purely from TOML. `docker/compose_web.yml` sets a `REDIS_URL` environment variable on the `worker` container, but **the app never reads it** — the broker always connects using the TOML value (`redis://redis:6379`), which happens to match the compose network today by coincidence, not by design. Changing `REDIS_PORT` in `.env` would silently *not* change what the worker actually connects to.
- **`DATABASE_URL`, set as an env var on the `worker` container in `compose_web.yml`, is unused entirely** — Postgres connection parameters come from the separate `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_HOST`/`POSTGRES_PORT` env vars instead.
- **Two visually-identical-looking API keys, two different directions**: `FASTAPI_API_KEY` (`config/config.toml`, default `"token"`) authenticates *inbound* requests to this service; `SERVING_API_KEY` (`.env`, default `"token"`) is the key this service sends *outbound* to the external LLM server. Both defaulting to the literal string `"token"` makes it easy to assume they're the same setting.

These are documented here rather than silently fixed because changing them (removing the dead env vars, or wiring `REDIS_URL`/`DATABASE_URL` to actually flow through) is an operational decision, not just a docs fix — see [CONFIGURATION.md](../CONFIGURATION.md) for the full parameter table.

---

## 7. Auth — Static Bearer Token

### Description

`verify_api_key` compares the `Authorization: Bearer <token>` header against a single, static `FASTAPI_API_KEY` for every request. No per-user identity, no scopes, no token expiry or rotation mechanism.

### Pros

- **Matches the OpenAI SDK's own auth shape** (`OpenAI(api_key=...)`) — zero client-side changes needed
- **Trivial to operate for a single-tenant / internal deployment** — one secret, one place it's checked

### Cons

- **No multi-tenancy** — every caller with the token has full access to every assistant/thread/run; there's no way to scope a token to a subset of resources
- **No revocation without a redeploy** — rotating the key means updating `config/config.toml` and restarting the service, not revoking a row in a database

### Alternatives considered

| Option | Reason not chosen |
|---|---|
| Per-user API keys (DB-backed) | Not needed yet — no multi-tenant requirement today; would be a natural next step if one appears |
| OAuth2 / JWT | Significant added complexity for a backend currently consumed by trusted internal clients only |

---

## 8. Tools / Function Calling — Accepted, Not Executed

### Description

`CreateAssistantRequest`/`CreateRunRequest` accept `tools`/`tool_choice` (including `code_interpreter`-shaped entries, for API compatibility) and store them, but `build_chat_request` never forwards them to `llm.chat.completions.create`, and there is no tool-call execution loop anywhere in `app/services/`.

### Pros

- **Keeps the request/response shape compatible** with clients built against the real OpenAI Assistants API, even before tool execution exists
- **No half-built execution sandbox to secure** — running `code_interpreter` safely is a substantial project on its own; not pretending to support it avoids a false sense of capability

### Cons

- **A client that sets `tools` and expects tool calls back will silently get plain text instead** — there's no error or warning that tools are a no-op today. Documented here and in [README.md](README.md#known-limitations--roadmap) specifically because the schema accepting the field could otherwise read as "supported."

---

## 9. Observability — MLflow Tracing + MinIO

### Description

Every generation call opens an MLflow span tagged with the four resource IDs (`thread_id`, `run_id`, `message_id`, `assistant_id`) and records token usage/latency/throughput as attributes. MLflow's backend store is Postgres (a separate `mlflow` database) and its artifact/trace storage is MinIO (S3-compatible), rather than local disk.

### Pros

- **Every generation is traceable back to the exact thread/run/message** that produced it — essential for debugging a specific user-reported bad response
- **MinIO gives S3 semantics locally** — the same `MLFLOW_S3_ENDPOINT_URL`/artifact-root config works unchanged against real S3 in a cloud deployment

### Cons

- **Another two containers to run and monitor** (`mlflow`, `minio`) beyond the core API/worker/Postgres/Redis set
- **Async MLflow logging (`mlflow.config.enable_async_logging()`) means a trace can lag slightly behind the actual request** — acceptable for observability, not suitable if traces were ever needed synchronously

---

## 10. Worker Reliability — `restart: always` + Redis-Reachability Healthcheck

### Description

The `worker` service in `docker/compose_web.yml` sets `restart: always` and a `healthcheck` that runs `redis.from_url(REDIS_URL).ping()` from inside the container every 15 seconds. `web`'s `depends_on.worker` condition was raised from `service_started` to `service_healthy` to match.

### Pros

- **A crashed worker (OOM, unhandled exception at startup, ...) restarts automatically** instead of leaving queued tasks stranded in Redis with no consumer and no alert
- **The healthcheck tests the thing that actually matters for a worker with no HTTP endpoint** — that it can reach its broker — rather than just "the process exists"

### Cons

- **Docker's healthcheck status alone does not trigger a restart** — `restart: always` handles process death; an unhealthy-but-alive worker (e.g. stuck in a deadlock while still holding its Redis connection) needs an external monitor (or a tool like `autoheal`) acting on the health status to be caught automatically
- **A crash loop (e.g. a bad deploy) will restart indefinitely** rather than backing off or paging after N attempts — acceptable for now given single-replica deployment, worth revisiting before running many worker replicas

### Alternatives considered

| Option | Reason not chosen |
|---|---|
| No healthcheck, `restart: always` only | Loses the `depends_on: condition: service_healthy` signal other services already use for Postgres/Redis/MLflow; `web` could start before the worker can actually reach Redis |
| HTTP healthcheck endpoint on the worker | Would need a second HTTP server just for health, inside a process whose job is consuming a queue — the Redis ping is a truer signal for the same cost |

---

## 11. Postgres Connection Pooling — Per-Process Pool

### Description

Each process (each `uvicorn` worker under `NUM_WORKERS`, and the single `taskiq_worker` process) owns its own `asyncpg.Pool` (`min_size=5`, `max_size=10`), created once at startup and reused for every request/task in that process.

### Pros

- **No cross-process coordination needed** — `asyncpg.Pool` is not fork-safe, so per-process pools are the correct model here, not a limitation
- **Bounded resource usage per process** — `max_size=10` caps how many concurrent Postgres connections one process can hold

### Cons

- **Total connections scale with `NUM_WORKERS` × pool size**, plus the worker's own pool — needs to be sized against Postgres' `max_connections` explicitly as `NUM_WORKERS` or worker replicas grow, rather than being self-limiting
- **A single busy generation path (many concurrent runs in one worker process) can exhaust that process's 10-connection pool**, queueing on `pool.acquire()` rather than failing fast — there is currently no explicit concurrency cap on the TaskIQ worker tied to the pool size
