# Detailed Request / Run Flow

## Component Graph

```text
App Startup  (app/app.py @app.on_event("startup"))
        ├── wait_for_serving()            block until the external LLM server responds
        ├── init_model()                  AsyncOpenAI client, sends one test completion
        ├── init_postgres() + _create_pool()   asyncpg pool
        ├── wait_for_postgres()           poll until reachable
        ├── _create_table()               CREATE TABLE IF NOT EXISTS ×4 (idempotent)
        └── init_minio()                  MinIO client (backs MLflow artifact storage)

Client (openai SDK)
        │  HTTP  Authorization: Bearer <FASTAPI_API_KEY>
        ▼
FastAPI Router  (assistant_router | thread_router | message_router | run_router)
        │  verify_api_key()          Bearer token == FASTAPI_API_KEY?  NO → 401
        │  validate_id_prefix() / *IdPath   path IDs match expected prefix?  NO → 400
        ▼
Service layer  (AssistantService | ThreadService | MessageService | RunDispatchService)
        │
        ▼
PostgresXxxStore  (asyncpg, connection from pool per call)
```

---

## Flow A — Create Thread and Run (`POST /v1/threads/runs`)

This is the path the recent reliability fixes target. IDs are generated **before** any database write, and the run row is written **synchronously**, before the response is returned — not left for the background worker to create lazily.

```text
① thread_router.create_thread_and_run(request)
    │  validate_id_prefix(request.assistant_id, "assistant")
    │
    │  run_id, step_id, message_id = generate_assistant_object(...) × 3
    │      ← generated up front so seed messages can be tagged with run_id
    │        without a second insert later
    ▼
② ThreadService.create_thread(payload, run_id, assistant_id)
    │  INSERT INTO threads (...)
    │  IF payload.messages:
    │      PostgresMessageStore.insert_messages(data, run_id=run_id, assistant_id=assistant_id)
    │          ON CONFLICT (id) DO NOTHING   ← safe to retry
    ▼
③ RunDispatchService.create_and_dispatch_run(thread_id, run_id, step_id, message_id, request)
    │  resolve_run_params()
    │      instructions  = request.instructions  or assistant.instructions or DEFAULT_ASSISTANT_PROMPT
    │      temperature   = request.temperature   or assistant.temperature
    │      top_p         = request.top_p         or assistant.top_p
    │
    │  PostgresRunStore.create_run(run_id, thread_id, assistant_id, max_prompt_tokens, max_completion_tokens)
    │      INSERT INTO runs (..., status='queued') ON CONFLICT (id) DO NOTHING
    │      ★ FIX: this now runs HERE, before dispatch — not lazily inside the worker.
    │        A client that GETs the run right after this call always finds it;
    │        previously the row didn't exist until the worker dequeued the task,
    │        so an immediate GET could 404 on a run the API had just called "queued".
    ▼
④ RunDispatchService.dispatch_run(...)
    │  request.stream == True?
    │      NO  → run_background_llm.kiq(thread_id, run_id, request, ...)   [Flow B]
    │             return RunObject(status="queued")            ← row already exists (step ③)
    │      YES → StreamingResponse(handle_streaming_response(...))         [Flow C]
    ▼
Client receives RunObject(status="queued") or an SSE stream
    │  GET /threads/{thread_id}/runs/{run_id}  at any point from here on
    ▼
    → 200 with the current status (queued / in_progress / completed / failed)
      — never 404, because the row was written in step ③, before this response.
```

`POST /v1/threads/{thread_id}/runs` (run on an *existing* thread) is the same from step ③ onward — `RunDispatchService.create_and_dispatch_run` is shared by both routers so their dispatch logic can't drift apart.

---

## Flow B — Background Worker (non-streaming)

```text
Redis Stream  (consumer group "taskiq", queue "taskiq")
    │  XREADGROUP
    ▼
taskiq_worker.run_background_llm(thread_id, run_id, request, assistant_id,
                                  instructions, message_id, temperature, top_p, endpoint_path)
    │  uses context.state.postgres_client.pool and context.state.llm
    │      ← both initialized ONCE per worker process at WORKER_STARTUP, reused per task
    ▼
generation_worker.handle_generation_response(...)
    │
    ├─① current_status = PostgresRunStore.get_run_status(run_id)
    │     status IN (COMPLETED, FAILED, CANCELED, EXPIRED)?
    │         YES → log "already <status>, skipping reprocessing" → return
    │         ← guards against Redis redelivering this task after a worker
    │           crashed AFTER completing the run but BEFORE acking the message
    │
    ├─② prepare_generation_context(request, thread_id, run_id, assistant_id, instructions)
    │     PostgresRunStore.create_run(...)  ON CONFLICT DO NOTHING
    │         ← idempotent no-op safety net; the real row was already created
    │           synchronously in Flow A step ③
    │     prepare_messages(request, thread_id, ...)
    │         CreateRunRequest        → history = last NUMS_OF_PREVIOUS_INTERACTION
    │                                    messages from Postgres + additional_messages
    │                                    (external_messages = additional_messages, to insert)
    │         CreateThreadRunRequest  → history = request.thread.messages
    │                                    (external_messages = [] — already persisted
    │                                    by ThreadService.create_thread in Flow A step ②)
    │     IF external_messages:
    │         PostgresMessageStore.insert_messages(..., run_id=run_id)
    │             ON CONFLICT (id) DO NOTHING
    │
    ▼
generation_worker.generate_response_from_messages(...)
    │
    ├─③ PostgresRunStore.update_run_status(run_id, IN_PROGRESS)   → sets started_at
    │
    ├─④ mlflow.start_span(name=endpoint_path, span_type=CHAT_MODEL)
    │     tag_span()             tags: thread_id, run_id, message_id, assistant_id
    │     llm.chat.completions.create(messages=chat_messages, **request_kwargs)
    │         ──▶ external LLM server (vLLM/SGLang/...)
    │     record_span_metrics()  config, token usage, latency, throughput
    │
    ├─⑤ persist_and_complete(thread_id, run_id, assistant_id, message_id, response_message, ...)
    │     PostgresMessageStore.insert_messages(...)   ON CONFLICT DO NOTHING
    │     PostgresRunStore.update_run_usage(run_id, usage)
    │     PostgresRunStore.update_run_status(run_id, COMPLETED)   → sets completed_at
    │     mlflow.flush_async_logging()
    │
    └─  Exception at any point above?
            fail_run(run_id, error, "GENERATION_WORKER")
                SystemLogger.error(...)
                PostgresRunStore.update_run_status(run_id, FAILED)   → sets failed_at
                ← swallowed here, not re-raised: the task still completes and gets
                  acked normally. A transient LLM error therefore does NOT trigger
                  an automatic TaskIQ retry — only a hard worker crash (before ack)
                  does, and that path is what step ① and the ON CONFLICT guards
                  above are for.
```

---

## Flow C — Streaming (`stream: true`)

No Redis Stream involved — the same context preparation runs inline on the request-handling task, and results are yielded as Server-Sent Events instead of being written by a separate worker process.

```text
RunDispatchService.dispatch_run(..., request.stream=True)
    ▼
StreamingResponse(handle_streaming_response(...), media_type="text/event-stream")
    │
    ├─ prepare_generation_context(...)     same as Flow B step ②
    ├─ update_run_status(run_id, IN_PROGRESS)
    ├─ llm.chat.completions.create(..., stream=True)
    │     for each chunk → yield SSE event to the client
    ├─ persist_and_complete(...)           same as Flow B step ⑤, once the stream ends
    └─ on exception → fail_run(...)        same as Flow B
```

---

## Redelivery & Idempotency

Redis Streams gives **at-least-once** delivery via consumer groups, not exactly-once — this is expected and designed around, not treated as an edge case:

```text
Worker A dequeues task, starts handle_generation_response(), then the PROCESS DIES
   (OOM, node restart, hard kill) before acking the message
        │
        ▼
Message stays PENDING in the consumer group
        │  idle_timeout elapses (broker default: 10 minutes)
        ▼
XAUTOCLAIM reassigns the message to Worker B (or A after restart)
        │
        ▼
Worker B runs handle_generation_response() again, from the top:
    ① terminal-status check — if Worker A got far enough to mark the run
       COMPLETED/FAILED before dying, Worker B sees that and returns immediately
    ② create_run / insert_messages — ON CONFLICT (id) DO NOTHING absorbs any
       row Worker A already wrote; every skip is logged
        │
        ▼
Run reaches exactly one terminal state; no duplicate assistant message; no
double-billed LLM call if Worker A had already gotten a response back before dying
   (only if it died before the run reached IN_PROGRESS/COMPLETED does Worker B
   redo the actual LLM call — an unavoidable trade-off of at-least-once delivery
   without a distributed lock, see DESIGN_DECISIONS.md)
```

---

## ID Scheme

```text
generate_assistant_object(object) → f"{PREFIX_MAP[object]}_{uuid4().hex[:24]}"

assistant → asst_...     thread → thread_...     message → msg_...
run       → run_...      step   → step_...
```

Path parameters are validated against this prefix before the handler runs (`ThreadIdPath`, `AssistantIdPath`, `MessageIdPath`, `RunIdPath` — FastAPI dependencies wrapping `validate_id_prefix`), so a `thread_id` accidentally passed as `run_id` fails fast with a 400 instead of a confusing 404 deeper in the stack.
