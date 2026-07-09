# Configuration Reference

Config comes from **two independent sources** — there is no single priority chain merging them, so it matters which one actually backs a given parameter:

1. **Environment variables / `.env`** (`os.getenv`, `app/core/config/{api,database,mlflow,models,redis}.py`) — infrastructure and secrets: ports, DB/MinIO credentials, the external LLM endpoint. Not version-controlled (`.env` is gitignored; `.env.sample` is the template).
2. **`config/config.toml`** (`app/utils/config_loader`, a standalone `TomlConfigLoader`) — a small set of static values with **no environment-variable override**: the inbound `FASTAPI_API_KEY`, `REDIS_URL`, and interaction parameters. Version-controlled.
3. **Field defaults in Pydantic schemas** (e.g. `CreateAssistantRequest.model` defaults to `LLM_MODEL_NAME`) — used only when a request doesn't set the field at all.

`app/core/config/__init__.py` loads `.env` via `python-dotenv` then re-exports every module under `app.core.config`, so application code imports everything from `app.core.config` regardless of which of the two sources actually backs it.

## `.env` (environment variables)

| Variable | Sample default | Used by | Description |
|---|---|---|---|
| `FASTAPI_PORT` | `8005` | `docker/compose_web.yml` | Host port the API is published on |
| `REDIS_PORT` | `6379` | `docker/compose_db.yml`, `docker/compose_web.yml` | Host port Redis is published on — **not** what the app connects with, see below |
| `POSTGRES_PORT` | `5432` | `docker/compose_db.yml`, `app/core/config/database.py` | Postgres port |
| `MLFLOW_PORT` | `5000` | `docker/compose_tracking.yml` | Host port the MLflow UI is published on |
| `MINIO_API_PORT` | `9000` | `docker/compose_tracking.yml` | MinIO S3 API port |
| `MINIO_CONSOLE_PORT` | `9001` | `docker/compose_tracking.yml` | MinIO web console port |
| `NUM_WORKERS` | `1` | `docker/compose_web.yml` (`uvicorn --workers`) | Number of `uvicorn` worker processes — each gets its own Postgres pool, see [DESIGN_DECISIONS.md](en/DESIGN_DECISIONS.md#11-postgres-connection-pooling--per-process-pool) |
| `SERVING_API_KEY` | `token` | `app/core/config/api.py`, `app/startup/startup.py` | API key this service sends **to** the external LLM server. Not the same thing as `FASTAPI_API_KEY` below |
| `LLM_MODEL_NAME` | `Qwen/Qwen3-4B-AWQ` | `app/core/config/models.py` | Model name passed to the external LLM server and used as `CreateAssistantRequest`'s default `model` |
| `LLM_BASE_URL` | `http://172.17.0.1:8100/v1` | `app/startup/startup.py` | Base URL of the external OpenAI-compatible serving backend (vLLM/SGLang/...) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` | `postgres` / `postgres123` / `chat-db` / `postgres` | `app/core/config/database.py` | Postgres connection parameters, read individually — not from a single `DATABASE_URL` |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `admin` / `admin12345` | `app/core/config/mlflow.py`, `docker/compose_tracking.yml` | MinIO credentials; also exported as `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` at startup for MLflow's S3 client |
| `MLFLOW_EXPERIMENT_NAME` | `Experiment` | `app/core/config/mlflow.py` | MLflow experiment all traces are logged under |
| `MLFLOW_DEFAULT_ARTIFACT_ROOT` | `s3://mlflow/artifacts` | `app/core/config/mlflow.py` | Artifact root, backed by MinIO |
| `MLFLOW_S3_ENDPOINT_URL` | `http://minio:9000` | `app/core/config/mlflow.py` | S3 endpoint MLflow's artifact client talks to |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | `app/core/config/mlflow.py` | MLflow tracking server the app logs traces to |

### Known dead/unused variables

These are set in `docker/compose_web.yml` but **not read by the application** — kept here so they're not mistaken for load-bearing config:

| Variable | Set in | Why it's dead |
|---|---|---|
| `REDIS_URL` (on the `worker` service) | `docker/compose_web.yml` | `app/core/config/redis.py` reads `REDIS_URL` from `config/config.toml` only, with no env override. The TaskIQ broker (used by both the `web` and `worker` processes, via `taskiq_worker.py`) always uses the TOML value. Changing `REDIS_PORT` in `.env` does **not** change what the broker connects to. |
| `DATABASE_URL` (on the `worker` service) | `docker/compose_web.yml` | Never referenced in `app/`. Postgres connection parameters come from the individual `POSTGRES_*` variables above. |

## `config/config.toml`

No environment-variable override for any of these — edit the file directly (and redeploy) to change them.

| Key | Default | Used by | Description |
|---|---|---|---|
| `api.FASTAPI_API_KEY` | `token` | `app/security/auth.py` | Bearer token required on every `/v1/...` request (`verify_api_key`). Distinct from `SERVING_API_KEY` above — this one authenticates **inbound** requests to this service |
| `redis.REDIS_URL` | `redis://redis:6379` | `taskiq_worker.py` (via `app/core/config/redis.py`) | Redis connection string for the TaskIQ broker — see the dead-variable note above |
| `interaction.NUMS_OF_PREVIOUS_INTERACTION` | `3` | `app/utils/messaging/preparation.py` | Number of most-recent thread messages fetched as context for a `CreateRunRequest` generation (not used for `create_thread_and_run`, which uses the thread's own seed messages) |

## Code-level defaults

Defined directly in `app/core/config/`, not overridable via `.env` or TOML:

| Name | Value | Location | Description |
|---|---|---|---|
| `LLM_EXTRA_BODY` | `{"chat_template_kwargs": {"enable_thinking": False}}` | `app/core/config/models.py` | Passed as `extra_body` on every chat completion call — disables Qwen3's `<think>` reasoning trace by default |
| `DEFAULT_ASSISTANT_PROMPT` | *(generic helpful-assistant prompt)* | `app/core/config/prompts.py` | Fallback instructions when neither the run nor the assistant specifies any |

## Other tunables (not environment-driven)

| Name | Value | Location | Description |
|---|---|---|---|
| Postgres pool size | `min_size=5`, `max_size=10` | `app/db/postgres/client.py` (`PostgresClient.__init__`) | Per-process connection pool bounds; change requires editing the constructor call, not config |
| Redis Stream `idle_timeout` | `600000` ms (10 min) | `taskiq_redis` default, used as-is in `taskiq_worker.py` | How long an unacked message waits before being reclaimed and redelivered — see [FLOW.md](en/FLOW.md#redelivery--idempotency) |
