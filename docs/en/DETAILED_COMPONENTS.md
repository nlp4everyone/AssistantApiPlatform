# Core Components

## Routers (`app/router/`)

Thin FastAPI layers — validate input, call one service method, return its result. All routes depend on `verify_api_key`; path IDs use the `*IdPath` dependencies (`ThreadIdPath`, `AssistantIdPath`, `MessageIdPath`, `RunIdPath`) to reject a wrong-prefix ID before the handler body runs.

- **`assistant_router.py`** — `POST/GET /assistants`, `GET/DELETE /assistants/{assistant_id}`
- **`thread_router.py`** — `POST /threads`, `GET/DELETE /threads/{thread_id}`, and `POST /threads/runs` (create-and-run: generates run/step/message IDs up front, creates the thread via `ThreadService`, then hands off to `RunDispatchService.create_and_dispatch_run`)
- **`message_router.py`** — `POST/GET /{thread_id}/messages`, `GET/DELETE /{thread_id}/messages/{message_id}` (mounted under `/v1/threads` prefix in `app.py`)
- **`run_router.py`** — `POST /{thread_id}/runs`, `GET /{thread_id}/runs`, `GET /{thread_id}/runs/{run_id}` (mounted under `/v1/threads` prefix)

## AssistantService (`app/services/assistants/assistant_service.py`)

CRUD over the `assistants` table. `create_assistant` generates the `asst_...` ID, persists the request fields, and returns the composed `AssistantObject`. `CreateAssistantRequest` defaults `model`/`instructions` from `app/core/config` (`LLM_MODEL_NAME`, `DEFAULT_ASSISTANT_PROMPT`) when the caller doesn't set them.

## ThreadService (`app/services/threads/thread_service.py`)

`create_thread(payload, run_id=None, assistant_id=None)` — inserts the `threads` row, then, if `payload.messages` was supplied, persists them via `PostgresMessageStore.insert_messages`. The optional `run_id`/`assistant_id` let `create_thread_and_run` tag those seed messages with the run that's about to process them, instead of inserting them a second time from inside the worker. `retrieve_thread` / `delete_thread` round out the resource.

## MessageService (`app/services/messages/message_service.py`)

CRUD + cursor-paginated list over the `messages` table, with an optional `run_id` filter on list (`GET /messages?run_id=...`) to fetch only the messages a specific run touched.

## RunDispatchService (`app/services/runs/run_dispatch.py`)

The shared core between `POST /threads/{id}/runs` and `POST /threads/runs` (create-and-run) — both call `create_and_dispatch_run` so their dispatch logic can't drift apart.

- `resolve_run_params(assistant_id, request_instructions, request_temperature, request_top_p)` — request-level values win; otherwise fall back to the assistant's own config, then `DEFAULT_ASSISTANT_PROMPT` for instructions
- `create_and_dispatch_run(...)` — generates run/step/message IDs if the caller didn't already, resolves params, **synchronously creates the run row** (`PostgresRunStore.create_run`, before dispatch — see [FLOW.md](FLOW.md)), then calls `dispatch_run`
- `dispatch_run(...)` — `request.stream` decides the path: `run_background_llm.kiq(...)` (enqueue) + return a `queued` `RunObject`, or `StreamingResponse(handle_streaming_response(...))`

## RunService (`app/services/runs/run_service.py`)

Read-only: `list_runs` (cursor pagination over `runs.seq`) and `retrieve_run`, both scoped to a thread (raise `ThreadNotFoundException` if the thread doesn't exist, `RunNotFoundException` if the run doesn't).

## Generation Context (`app/services/common/generation_context.py`)

`prepare_generation_context(postgres_pool, request, thread_id, run_id, assistant_id, instructions)` is the entry point both the background worker and the streaming handler call before touching the LLM:

1. Validates `request` into `CreateRunRequest` or `CreateThreadRunRequest`
2. `PostgresRunStore.create_run(...)` — `ON CONFLICT (id) DO NOTHING`; idempotent no-op in the normal path since `RunDispatchService` already created the row, but the real safety net against Redis Stream redelivery
3. `prepare_messages(...)` (`app/utils/messaging/preparation.py`) — for `CreateRunRequest`, fetches the last `NUMS_OF_PREVIOUS_INTERACTION` thread messages plus any `additional_messages`; for `CreateThreadRunRequest`, uses the thread's seed messages directly (already persisted by `ThreadService.create_thread`, so nothing new to insert)
4. Persists any `external_messages` (only non-empty on the `CreateRunRequest` + `additional_messages` path) via `PostgresMessageStore.insert_messages`

## LLM Generation Helpers (`app/services/common/llm_generation.py`)

- `build_chat_request(messages, instructions, max_completion_tokens, temperature, top_p)` — converts to OpenAI chat format, prepends the system instructions, builds `request_kwargs` (`model`, `max_tokens`, `extra_body`, optional `temperature`/`top_p`)
- `tag_span(span, ...)` / `record_span_metrics(span, ...)` — MLflow span tagging (`thread_id`, `run_id`, `message_id`, `assistant_id`) and attributes (config, token usage via `approximate_count_tokens`, latency, throughput)
- `persist_and_complete(...)` — insert the assistant's reply message, update `runs.usage`, set status `COMPLETED`, flush async MLflow logging
- `fail_run(postgres_pool, run_id, error, log_tag)` — log the error and set status `FAILED`; called from a broad `except` in both the worker and the streaming handler, so a generation error always ends in a terminal run status instead of a run stuck `in_progress` forever

## Background Worker (`taskiq_worker.py`, `app/services/background/generation_worker.py`)

`taskiq_worker.py` wires a `RedisStreamBroker` (queue `taskiq`, consumer group `taskiq`) with a Redis-backed result backend, and defines the `run_background_llm` task. `WORKER_STARTUP`/`WORKER_SHUTDOWN` hooks create/close one Postgres pool and one `AsyncOpenAI` client **per worker process**, reused across tasks instead of reconnecting each time.

`generation_worker.py`:
- `TERMINAL_RUN_STATUSES = (COMPLETED, FAILED, CANCELED, EXPIRED)` — `handle_generation_response` checks the run's current status first and returns immediately if it's already terminal (guards against reprocessing a redelivered task for a run that already finished)
- `handle_generation_response(...)` — calls `prepare_generation_context`, then `generate_response_from_messages`; wraps both in `try/except` → `fail_run` on any error
- `generate_response_from_messages(...)` — sets status `IN_PROGRESS`, opens the MLflow span, calls the LLM, then `persist_and_complete`

## Streaming (`app/services/streaming/streaming_services.py`)

`handle_streaming_response(...)` is the streaming twin of the worker: same `prepare_generation_context` → `IN_PROGRESS` → LLM call → `persist_and_complete`/`fail_run` sequence, but it runs inline on the request-handling task (no Redis Stream involved) and yields Server-Sent Events as `llm.chat.completions.create(..., stream=True)` produces chunks.

## Postgres Layer (`app/db/postgres/`)

- **`client.py` — `PostgresClient`** — owns the `asyncpg.Pool` (`min_size=5`, `max_size=10` by default); `_create_pool()` / `_create_table()` (runs the DDL in `schema/database_schema.py`, all `CREATE TABLE IF NOT EXISTS`) / `close()`
- **`schema/database_schema.py`** — DDL for `assistants`, `threads`, `messages`, `runs`; `messages.run_id` and `runs.assistant_id`/`thread_id` carry referential meaning but only `thread_id` is an enforced `REFERENCES ... ON DELETE CASCADE` — deleting a thread cascades its messages and runs
- **`assistant_store.py` / `thread_store.py` / `message_store.py` / `run_store.py`** — one class per resource, static methods taking an explicit `pool` argument (no ORM). Inserts on the hot generation path (`insert_messages`, `create_run`) use `ON CONFLICT (id) DO NOTHING` and log any skipped duplicate — see [FLOW.md](FLOW.md#redelivery--idempotency)
- **`existence.py` — `check_row_exists`** — shared existence check used before raising `ThreadNotFoundException`/`RunNotFoundException`/etc., instead of duplicating the same `SELECT 1 ... LIMIT 1` in every store

## ID Generation (`app/utils/id_generation/`)

`generate_assistant_object(object)` → `f"{prefix}_{uuid4().hex[:24]}"` (`PREFIX_MAP`: `assistant→asst`, `thread→thread`, `message→msg`, `run→run`, `step→step`). `validate_id_prefix` / the `*IdPath` FastAPI dependencies enforce that an ID passed as `thread_id` actually starts with `thread_`, etc., failing fast on a mismatched ID instead of a confusing not-found deeper in a query.

## Security (`app/security/auth.py`)

`verify_api_key` — single static bearer token check: `Authorization: Bearer <token>` where `token == FASTAPI_API_KEY` (from `config/config.toml`). No per-user identity, scopes, or expiry — see [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

## Exceptions (`app/exceptions/`)

`AppException` is the common base for domain errors (`ThreadNotFoundException`, `RunNotFoundException`, `MessageNotFoundException`, `InvalidIdFormatException`, `BearerMissingException`, `APIKeyIncorrectException`, ...); `app.add_exception_handler` maps it and raw `asyncpg.PostgresError`/`socket.gaierror` (DB unreachable) to consistent JSON error responses in `app/app.py`.

## Observability (MLflow + MinIO)

Every generation call (worker or streaming) opens an MLflow span (`SpanType.CHAT_MODEL`) tagged with `thread_id`/`run_id`/`message_id`/`assistant_id`, with model config, token usage, latency, and throughput recorded as attributes, and the response text as the span output. `MLFLOW_TRACKING_URI` points at the `mlflow` container; MLflow's own artifact/trace storage is backed by MinIO (S3-compatible) via `MLFLOW_S3_ENDPOINT_URL`. MinIO is not currently exposed to application code for user file storage — it's wired to MLflow only.
