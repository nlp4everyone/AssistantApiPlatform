# Luồng Request / Run chi tiết

## Sơ đồ component

```text
App Startup  (app/app.py @app.on_event("startup"))
        ├── wait_for_serving()            chờ tới khi LLM server bên ngoài phản hồi
        ├── init_model()                  tạo client AsyncOpenAI, gửi 1 completion thử
        ├── init_postgres() + _create_pool()   pool asyncpg
        ├── wait_for_postgres()           poll tới khi kết nối được
        ├── _create_table()               CREATE TABLE IF NOT EXISTS ×4 (idempotent)
        └── init_minio()                  client MinIO (phục vụ artifact storage của MLflow)

Client (openai SDK)
        │  HTTP  Authorization: Bearer <FASTAPI_API_KEY>
        ▼
FastAPI Router  (assistant_router | thread_router | message_router | run_router)
        │  verify_api_key()          Bearer token == FASTAPI_API_KEY?  KHÔNG → 401
        │  validate_id_prefix() / *IdPath   ID trong path đúng prefix?  KHÔNG → 400
        ▼
Tầng Service  (AssistantService | ThreadService | MessageService | RunDispatchService)
        │
        ▼
PostgresXxxStore  (asyncpg, lấy connection từ pool mỗi lần gọi)
```

---

## Luồng A — Tạo Thread và Run (`POST /v1/threads/runs`)

Đây là luồng mà các bản fix ổn định gần đây tập trung xử lý. ID được sinh **trước** mọi lệnh ghi DB, và row của run được ghi **đồng bộ**, trước khi trả response — không để worker nền tạo trễ.

```text
① thread_router.create_thread_and_run(request)
    │  validate_id_prefix(request.assistant_id, "assistant")
    │
    │  run_id, step_id, message_id = generate_assistant_object(...) × 3
    │      ← sinh trước để seed message có thể gắn run_id ngay
    │        mà không cần insert lần hai về sau
    ▼
② ThreadService.create_thread(payload, run_id, assistant_id)
    │  INSERT INTO threads (...)
    │  NẾU payload.messages:
    │      PostgresMessageStore.insert_messages(data, run_id=run_id, assistant_id=assistant_id)
    │          ON CONFLICT (id) DO NOTHING   ← an toàn khi gọi lại
    ▼
③ RunDispatchService.create_and_dispatch_run(thread_id, run_id, step_id, message_id, request)
    │  resolve_run_params()
    │      instructions  = request.instructions  hoặc assistant.instructions hoặc DEFAULT_ASSISTANT_PROMPT
    │      temperature   = request.temperature   hoặc assistant.temperature
    │      top_p         = request.top_p         hoặc assistant.top_p
    │
    │  PostgresRunStore.create_run(run_id, thread_id, assistant_id, max_prompt_tokens, max_completion_tokens)
    │      INSERT INTO runs (..., status='queued') ON CONFLICT (id) DO NOTHING
    │      ★ FIX: bước này giờ chạy Ở ĐÂY, trước khi dispatch — không còn nằm trễ trong worker.
    │        Client GET run ngay sau lời gọi này luôn thấy nó tồn tại;
    │        trước đây row chỉ tồn tại sau khi worker dequeue task,
    │        nên GET ngay lập tức có thể 404 trên một run mà API vừa báo "queued".
    ▼
④ RunDispatchService.dispatch_run(...)
    │  request.stream == True?
    │      KHÔNG → run_background_llm.kiq(thread_id, run_id, request, ...)   [Luồng B]
    │              trả về RunObject(status="queued")          ← row đã tồn tại (bước ③)
    │      CÓ    → StreamingResponse(handle_streaming_response(...))         [Luồng C]
    ▼
Client nhận RunObject(status="queued") hoặc một stream SSE
    │  GET /threads/{thread_id}/runs/{run_id}  tại bất kỳ thời điểm nào sau đây
    ▼
    → 200 với status hiện tại (queued / in_progress / completed / failed)
      — không bao giờ 404, vì row đã được ghi ở bước ③, trước response này.
```

`POST /v1/threads/{thread_id}/runs` (chạy run trên thread *có sẵn*) giống hệt từ bước ③ trở đi — `RunDispatchService.create_and_dispatch_run` dùng chung cho cả hai router nên logic dispatch không thể lệch nhau.

---

## Luồng B — Worker nền (không streaming)

```text
Redis Stream  (consumer group "taskiq", queue "taskiq")
    │  XREADGROUP
    ▼
taskiq_worker.run_background_llm(thread_id, run_id, request, assistant_id,
                                  instructions, message_id, temperature, top_p, endpoint_path)
    │  dùng context.state.postgres_client.pool và context.state.llm
    │      ← cả hai được khởi tạo MỘT LẦN mỗi worker process lúc WORKER_STARTUP, tái sử dụng cho mọi task
    ▼
generation_worker.handle_generation_response(...)
    │
    ├─① current_status = PostgresRunStore.get_run_status(run_id)
    │     status thuộc (COMPLETED, FAILED, CANCELED, EXPIRED)?
    │         CÓ → log "already <status>, skipping reprocessing" → return
    │         ← chặn việc xử lý lại khi Redis redeliver task này: trường hợp này
    │           xảy ra khi worker trước đó đã xử lý xong run rồi mới chết,
    │           chỉ là chưa kịp ack message
    │
    ├─② prepare_generation_context(request, thread_id, run_id, assistant_id, instructions)
    │     PostgresRunStore.create_run(...)  ON CONFLICT DO NOTHING
    │         ← lưới an toàn idempotent; row thật đã được tạo đồng bộ
    │           ở Luồng A bước ③ rồi
    │     prepare_messages(request, thread_id, ...)
    │         CreateRunRequest        → lịch sử = NUMS_OF_PREVIOUS_INTERACTION
    │                                    message gần nhất từ Postgres + additional_messages
    │                                    (external_messages = additional_messages, cần insert)
    │         CreateThreadRunRequest  → lịch sử = request.thread.messages
    │                                    (external_messages = [] — đã được lưu
    │                                    bởi ThreadService.create_thread ở Luồng A bước ②)
    │     NẾU external_messages:
    │         PostgresMessageStore.insert_messages(..., run_id=run_id)
    │             ON CONFLICT (id) DO NOTHING
    │
    ▼
generation_worker.generate_response_from_messages(...)
    │
    ├─③ PostgresRunStore.update_run_status(run_id, IN_PROGRESS)   → set started_at
    │
    ├─④ mlflow.start_span(name=endpoint_path, span_type=CHAT_MODEL)
    │     tag_span()             tag: thread_id, run_id, message_id, assistant_id
    │     llm.chat.completions.create(messages=chat_messages, **request_kwargs)
    │         ──▶ LLM server bên ngoài (vLLM/SGLang/...)
    │     record_span_metrics()  config, token usage, latency, throughput
    │
    ├─⑤ persist_and_complete(thread_id, run_id, assistant_id, message_id, response_message, ...)
    │     PostgresMessageStore.insert_messages(...)   ON CONFLICT DO NOTHING
    │     PostgresRunStore.update_run_usage(run_id, usage)
    │     PostgresRunStore.update_run_status(run_id, COMPLETED)   → set completed_at
    │     mlflow.flush_async_logging()
    │
    └─  Có exception ở bất kỳ bước nào trên?
            fail_run(run_id, error, "GENERATION_WORKER")
                SystemLogger.error(...)
                PostgresRunStore.update_run_status(run_id, FAILED)   → set failed_at
                ← lỗi bị "nuốt" ở đây, không raise lại: task vẫn hoàn tất và được
                  ack bình thường. Vì vậy lỗi tạm thời từ LLM KHÔNG kích hoạt
                  retry tự động của TaskIQ — chỉ có worker chết cứng (trước khi ack)
                  mới kích hoạt redelivery, và bước ① cùng các guard ON CONFLICT
                  ở trên chính là để xử lý trường hợp đó.
```

---

## Luồng C — Streaming (`stream: true`)

Không có Redis Stream nào tham gia — cùng bước chuẩn bị context chạy ngay trên task xử lý request, kết quả được trả dưới dạng Server-Sent Events thay vì được ghi bởi một worker process riêng.

```text
RunDispatchService.dispatch_run(..., request.stream=True)
    ▼
StreamingResponse(handle_streaming_response(...), media_type="text/event-stream")
    │
    ├─ prepare_generation_context(...)     giống Luồng B bước ②
    ├─ update_run_status(run_id, IN_PROGRESS)
    ├─ llm.chat.completions.create(..., stream=True)
    │     mỗi chunk → yield sự kiện SSE cho client
    ├─ persist_and_complete(...)           giống Luồng B bước ⑤, khi stream kết thúc
    └─ có exception → fail_run(...)        giống Luồng B
```

---

## Redelivery & Idempotency

Redis Streams đảm bảo giao **at-least-once** qua consumer group, không phải exactly-once — đây là điều được thiết kế để xử lý sẵn, không phải trường hợp biên bất ngờ:

```text
Worker A dequeue task, bắt đầu handle_generation_response(), rồi PROCESS CHẾT
   (OOM, restart node, bị kill cứng) trước khi kịp ack message
        │
        ▼
Message ở trạng thái PENDING trong consumer group
        │  hết idle_timeout (mặc định broker: 10 phút)
        ▼
XAUTOCLAIM gán lại message cho Worker B (hoặc A sau khi restart)
        │
        ▼
Worker B chạy lại handle_generation_response() từ đầu:
    ① kiểm tra trạng thái kết thúc — nếu Worker A đã kịp đánh dấu run
       COMPLETED/FAILED trước khi chết, Worker B thấy vậy và return ngay
    ② create_run / insert_messages — ON CONFLICT (id) DO NOTHING bỏ qua
       mọi row Worker A đã ghi rồi; mỗi lần bỏ qua đều được log lại
        │
        ▼
Run đạt đúng một trạng thái kết thúc; không có message trùng của assistant; không
tốn thêm lệnh gọi LLM nếu Worker A đã nhận được phản hồi trước khi chết
   (chỉ khi Worker A chết trước khi run đạt IN_PROGRESS/COMPLETED thì Worker B
   mới gọi lại LLM thật sự — đây là đánh đổi khó tránh của giao at-least-once
   khi không dùng distributed lock, xem DESIGN_DECISIONS_vi.md)
```

---

## Sơ đồ ID

```text
generate_assistant_object(object) → f"{PREFIX_MAP[object]}_{uuid4().hex[:24]}"

assistant → asst_...     thread → thread_...     message → msg_...
run       → run_...      step   → step_...
```

Path parameter được kiểm tra đúng prefix trước khi vào handler (`ThreadIdPath`, `AssistantIdPath`, `MessageIdPath`, `RunIdPath` — dependency của FastAPI bọc `validate_id_prefix`), nên một `thread_id` vô tình được truyền làm `run_id` sẽ bị từ chối ngay với lỗi 400 thay vì một lỗi 404 khó hiểu ở tầng sâu hơn.
