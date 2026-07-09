# AssistantApiPlatform — Backend tương thích OpenAI Assistants API

Backend hướng production hiện thực mô hình resource của OpenAI Assistants, sử dụng:

- FastAPI (`app/app.py`) làm tầng API
- PostgreSQL (`asyncpg`) cho assistants/threads/messages/runs
- Redis Streams + TaskIQ cho sinh phản hồi nền, redelivery qua consumer group
- LLM server bên ngoài tương thích OpenAI (vLLM/SGLang/...) để inference thực sự
- MLflow (trace, token usage, latency) + MinIO (kho artifact tương thích S3) cho observability

---

# Kiến trúc

## Tổng quan

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
   (đẩy vào Redis Stream)          (chạy ngay trên task của request)
              │                             │
              ▼                             │
┌──────────────────────────────┐            │
│   TaskIQ Worker (container    │            │
│   riêng, consumer group)     │            │
│   run_background_llm task    │            │
└──────────────┬────────────────┘           │
               └─────────────┬───────────────┘
                             ▼
              prepare_generation_context()
              (create_run idempotent, prepare_messages)
                             │
                             ▼
              AsyncOpenAI.chat.completions.create()
              ──▶ LLM server bên ngoài (vLLM/SGLang/...)
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
      MLflow span (tag, usage,    persist_and_complete() /
      latency) ──▶ MinIO (S3)     fail_run() ──▶ Postgres
```

## Luồng request tổng quan

**Bước 1 — Auth + validate**

Mọi route (trừ health/docs) phụ thuộc `verify_api_key`, kiểm tra header `Authorization: Bearer <FASTAPI_API_KEY>` tĩnh. Path parameter tham chiếu ID (`thread_id`, `assistant_id`, `message_id`, `run_id`) được kiểm tra đúng prefix (`thread_`, `asst_`, `msg_`, `run_`) trước khi vào phần xử lý chính.

**Bước 2 — Tạo thread / create-and-run**

`POST /v1/threads/runs` (create-and-run) sinh sẵn ID run/step/message, tạo thread và gắn `run_id` vào các seed message trong cùng một lời gọi, rồi chuyển tiếp sang cùng `RunDispatchService.create_and_dispatch_run` mà `POST /v1/threads/{id}/runs` cũng dùng — để hai điểm vào này không bị lệch nhau. Xem [FLOW_vi.md](FLOW_vi.md) để biết trình tự chính xác, bao gồm fix giúp row của run hiện diện cho `GET` ngay trước cả khi response được trả về.

**Bước 3 — Dispatch: hàng đợi hay stream**

- **Không streaming** (`stream` để trống hoặc `false`): row của run được tạo, một task `run_background_llm` được đẩy vào Redis Stream, và một `RunObject` trạng thái `queued` được trả về ngay. Việc sinh phản hồi diễn ra sau, ngoài vòng đời request/response.
- **Streaming** (`stream: true`): không có task nào được đẩy vào hàng đợi — `handle_streaming_response` chạy cùng bước chuẩn bị context ngay tại chỗ và trả trực tiếp Server-Sent Events.

**Bước 4 — Sinh phản hồi**

Cả hai đường đều hội tụ về cùng các khối dùng chung (`app/services/common/`): `prepare_generation_context` (tạo run row idempotent + ghép lịch sử message), `build_chat_request` (message theo định dạng OpenAI + kwargs), một MLflow span bọc quanh lệnh gọi `chat.completions.create` thực sự, và `persist_and_complete` (insert message của assistant + usage + trạng thái `completed`) hoặc `fail_run` (trạng thái `failed`) khi lỗi.

**Bước 5 — An toàn với redelivery**

Worker TaskIQ chỉ ack message sau khi task hoàn tất. Nếu worker chết giữa chừng, consumer group của Redis sẽ redeliver message đó (`idle_timeout`, mặc định 10 phút) cho một consumer khác. Mọi lệnh ghi trên đường này — tạo run, insert seed message, insert message được sinh ra — đều dùng `ON CONFLICT (id) DO NOTHING`, và một run đã ở trạng thái kết thúc thì không bao giờ bị sinh lại. Xem [FLOW_vi.md](FLOW_vi.md) và [DESIGN_DECISIONS_vi.md](DESIGN_DECISIONS_vi.md).

> Để biết chính xác tên hàm và thứ tự gọi: [FLOW_vi.md](FLOW_vi.md)

---

# HTTP Endpoints

Mọi route có tiền tố `/v1` và yêu cầu `Authorization: Bearer <FASTAPI_API_KEY>`.

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/assistants` | Tạo assistant |
| `GET` | `/assistants` | Liệt kê assistants (phân trang theo cursor) |
| `GET` | `/assistants/{assistant_id}` | Lấy thông tin assistant |
| `DELETE` | `/assistants/{assistant_id}` | Xóa assistant |
| `POST` | `/threads` | Tạo thread (có thể kèm seed message) |
| `GET` | `/threads/{thread_id}` | Lấy thông tin thread |
| `DELETE` | `/threads/{thread_id}` | Xóa thread (cascade message/run) |
| `POST` | `/threads/runs` | Tạo thread **và** chạy run trong một lần gọi |
| `POST` | `/threads/{thread_id}/runs` | Tạo run trên thread có sẵn |
| `GET` | `/threads/{thread_id}/runs` | Liệt kê run của thread |
| `GET` | `/threads/{thread_id}/runs/{run_id}` | Lấy thông tin run |
| `POST` | `/threads/{thread_id}/messages` | Tạo message |
| `GET` | `/threads/{thread_id}/messages` | Liệt kê message (có thể lọc theo `run_id`) |
| `GET` | `/threads/{thread_id}/messages/{message_id}` | Lấy thông tin message |
| `DELETE` | `/threads/{thread_id}/messages/{message_id}` | Xóa message |

Chưa có: endpoint hủy run, run steps như một resource độc lập, upload file. Xem [README_vi.md](README_vi.md#hạn-chế-hiện-tại--roadmap).

---

# Background Worker

| | |
|---|---|
| Hàng đợi | Redis Streams (`RedisStreamBroker`, consumer group `taskiq`) |
| Task | `run_background_llm` (`taskiq_worker.py`) |
| Container | `taskiq_worker`, `restart: always`, healthcheck ping Redis mỗi 15s |
| Cửa sổ redelivery | `idle_timeout` = 10 phút (mặc định của broker) trước khi message chưa ack bị reclaim |
| Concurrency | Mặc định 1 replica; mô hình consumer group của TaskIQ hỗ trợ nhiều hơn mà không cần đổi code |

---

# Cấu hình

Xem [CONFIGURATION.md](../CONFIGURATION.md) để có bảng tham số đầy đủ: `.env` (hạ tầng/secret) so với `config/config.toml` (tham số tĩnh) so với giá trị mặc định trong code.

---

> Chi tiết từng component và API reference: [DETAILED_COMPONENTS_vi.md](DETAILED_COMPONENTS_vi.md)
