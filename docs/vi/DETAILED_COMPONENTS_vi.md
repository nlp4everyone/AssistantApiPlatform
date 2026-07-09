# Các thành phần chính

## Router (`app/router/`)

Tầng FastAPI mỏng — validate input, gọi một method service, trả kết quả. Mọi route phụ thuộc `verify_api_key`; ID trong path dùng các dependency `*IdPath` (`ThreadIdPath`, `AssistantIdPath`, `MessageIdPath`, `RunIdPath`) để từ chối ID sai prefix trước khi vào phần xử lý chính.

- **`assistant_router.py`** — `POST/GET /assistants`, `GET/DELETE /assistants/{assistant_id}`
- **`thread_router.py`** — `POST /threads`, `GET/DELETE /threads/{thread_id}`, và `POST /threads/runs` (create-and-run: sinh sẵn ID run/step/message, tạo thread qua `ThreadService`, rồi chuyển tiếp sang `RunDispatchService.create_and_dispatch_run`)
- **`message_router.py`** — `POST/GET /{thread_id}/messages`, `GET/DELETE /{thread_id}/messages/{message_id}` (gắn dưới prefix `/v1/threads` trong `app.py`)
- **`run_router.py`** — `POST /{thread_id}/runs`, `GET /{thread_id}/runs`, `GET /{thread_id}/runs/{run_id}` (gắn dưới prefix `/v1/threads`)

## AssistantService (`app/services/assistants/assistant_service.py`)

CRUD trên bảng `assistants`. `create_assistant` sinh ID `asst_...`, lưu các field của request, và trả về `AssistantObject`. `CreateAssistantRequest` lấy mặc định `model`/`instructions` từ `app/core/config` (`LLM_MODEL_NAME`, `DEFAULT_ASSISTANT_PROMPT`) khi caller không set.

## ThreadService (`app/services/threads/thread_service.py`)

`create_thread(payload, run_id=None, assistant_id=None)` — insert row `threads`, sau đó nếu `payload.messages` có giá trị thì lưu chúng qua `PostgresMessageStore.insert_messages`. `run_id`/`assistant_id` tùy chọn cho phép `create_thread_and_run` gắn các seed message này với run sắp xử lý chúng, thay vì insert lần hai từ trong worker. `retrieve_thread` / `delete_thread` hoàn thiện resource này.

## MessageService (`app/services/messages/message_service.py`)

CRUD + list phân trang theo cursor trên bảng `messages`, có tùy chọn filter theo `run_id` khi list (`GET /messages?run_id=...`) để chỉ lấy các message mà một run cụ thể đã xử lý.

## RunDispatchService (`app/services/runs/run_dispatch.py`)

Phần lõi dùng chung giữa `POST /threads/{id}/runs` và `POST /threads/runs` (create-and-run) — cả hai đều gọi `create_and_dispatch_run` để logic dispatch không thể lệch nhau.

- `resolve_run_params(assistant_id, request_instructions, request_temperature, request_top_p)` — giá trị ở request được ưu tiên; nếu không có thì lấy từ cấu hình của assistant, rồi tới `DEFAULT_ASSISTANT_PROMPT` cho instructions
- `create_and_dispatch_run(...)` — sinh ID run/step/message nếu caller chưa sinh, resolve params, **tạo run row đồng bộ** (`PostgresRunStore.create_run`, trước khi dispatch — xem [FLOW_vi.md](FLOW_vi.md)), rồi gọi `dispatch_run`
- `dispatch_run(...)` — `request.stream` quyết định đường đi: `run_background_llm.kiq(...)` (đẩy vào hàng đợi) + trả về `RunObject` trạng thái `queued`, hoặc `StreamingResponse(handle_streaming_response(...))`

## RunService (`app/services/runs/run_service.py`)

Chỉ đọc: `list_runs` (phân trang theo cursor trên `runs.seq`) và `retrieve_run`, đều giới hạn trong phạm vi một thread (raise `ThreadNotFoundException` nếu thread không tồn tại, `RunNotFoundException` nếu run không tồn tại).

## Generation Context (`app/services/common/generation_context.py`)

`prepare_generation_context(postgres_pool, request, thread_id, run_id, assistant_id, instructions)` là điểm vào mà cả worker nền lẫn streaming handler đều gọi trước khi chạm tới LLM:

1. Validate `request` thành `CreateRunRequest` hoặc `CreateThreadRunRequest`
2. `PostgresRunStore.create_run(...)` — `ON CONFLICT (id) DO NOTHING`; là no-op idempotent trong đường bình thường vì `RunDispatchService` đã tạo row rồi, nhưng là lưới an toàn thật sự trước redelivery của Redis Stream
3. `prepare_messages(...)` (`app/utils/messaging/preparation.py`) — với `CreateRunRequest`, lấy `NUMS_OF_PREVIOUS_INTERACTION` message gần nhất của thread cộng thêm `additional_messages`; với `CreateThreadRunRequest`, dùng trực tiếp seed message của thread (đã được `ThreadService.create_thread` lưu sẵn, không cần insert thêm)
4. Lưu mọi `external_messages` (chỉ khác rỗng ở đường `CreateRunRequest` + `additional_messages`) qua `PostgresMessageStore.insert_messages`

## LLM Generation Helpers (`app/services/common/llm_generation.py`)

- `build_chat_request(messages, instructions, max_completion_tokens, temperature, top_p)` — chuyển sang định dạng chat của OpenAI, chèn system instructions lên đầu, dựng `request_kwargs` (`model`, `max_tokens`, `extra_body`, `temperature`/`top_p` nếu có)
- `tag_span(span, ...)` / `record_span_metrics(span, ...)` — gắn tag MLflow span (`thread_id`, `run_id`, `message_id`, `assistant_id`) và attribute (config, token usage qua `approximate_count_tokens`, latency, throughput)
- `persist_and_complete(...)` — insert message trả lời của assistant, cập nhật `runs.usage`, set trạng thái `COMPLETED`, flush log MLflow bất đồng bộ
- `fail_run(postgres_pool, run_id, error, log_tag)` — log lỗi và set trạng thái `FAILED`; được gọi từ khối `except` rộng ở cả worker lẫn streaming handler, nên một lỗi sinh phản hồi luôn kết thúc bằng trạng thái terminal thay vì run kẹt mãi ở `in_progress`

## Worker nền (`taskiq_worker.py`, `app/services/background/generation_worker.py`)

`taskiq_worker.py` khởi tạo một `RedisStreamBroker` (queue `taskiq`, consumer group `taskiq`) với result backend dùng Redis, và định nghĩa task `run_background_llm`. Hook `WORKER_STARTUP`/`WORKER_SHUTDOWN` tạo/đóng một pool Postgres và một client `AsyncOpenAI` **mỗi worker process**, tái sử dụng qua các task thay vì kết nối lại mỗi lần.

`generation_worker.py`:
- `TERMINAL_RUN_STATUSES = (COMPLETED, FAILED, CANCELED, EXPIRED)` — `handle_generation_response` kiểm tra trạng thái hiện tại của run trước, return ngay nếu đã ở trạng thái kết thúc (chặn xử lý lại một task bị redeliver cho run đã xong)
- `handle_generation_response(...)` — gọi `prepare_generation_context`, rồi `generate_response_from_messages`; bọc cả hai trong `try/except` → `fail_run` khi có lỗi
- `generate_response_from_messages(...)` — set trạng thái `IN_PROGRESS`, mở MLflow span, gọi LLM, rồi `persist_and_complete`

## Streaming (`app/services/streaming/streaming_services.py`)

`handle_streaming_response(...)` là bản song sinh streaming của worker: cùng trình tự `prepare_generation_context` → `IN_PROGRESS` → gọi LLM → `persist_and_complete`/`fail_run`, nhưng chạy ngay trên task xử lý request (không có Redis Stream nào tham gia) và yield Server-Sent Events khi `llm.chat.completions.create(..., stream=True)` sinh ra từng chunk.

## Tầng Postgres (`app/db/postgres/`)

- **`client.py` — `PostgresClient`** — sở hữu `asyncpg.Pool` (mặc định `min_size=5`, `max_size=10`); `_create_pool()` / `_create_table()` (chạy DDL trong `schema/database_schema.py`, toàn bộ `CREATE TABLE IF NOT EXISTS`) / `close()`
- **`schema/database_schema.py`** — DDL cho `assistants`, `threads`, `messages`, `runs`; `messages.run_id` và `runs.assistant_id`/`thread_id` mang ý nghĩa tham chiếu nhưng chỉ `thread_id` là `REFERENCES ... ON DELETE CASCADE` thật sự — xóa một thread sẽ cascade message và run của nó
- **`assistant_store.py` / `thread_store.py` / `message_store.py` / `run_store.py`** — mỗi resource một class, static method nhận trực tiếp `pool` (không dùng ORM). Các lệnh insert trên đường sinh phản hồi (`insert_messages`, `create_run`) dùng `ON CONFLICT (id) DO NOTHING` và log lại mọi lần bỏ qua bản trùng — xem [FLOW_vi.md](FLOW_vi.md#redelivery--idempotency)
- **`existence.py` — `check_row_exists`** — helper kiểm tra tồn tại dùng chung trước khi raise `ThreadNotFoundException`/`RunNotFoundException`/..., thay vì lặp lại cùng một `SELECT 1 ... LIMIT 1` ở mỗi store

## Sinh ID (`app/utils/id_generation/`)

`generate_assistant_object(object)` → `f"{prefix}_{uuid4().hex[:24]}"` (`PREFIX_MAP`: `assistant→asst`, `thread→thread`, `message→msg`, `run→run`, `step→step`). `validate_id_prefix` / các dependency `*IdPath` của FastAPI đảm bảo một ID truyền làm `thread_id` thực sự bắt đầu bằng `thread_`, v.v., báo lỗi ngay khi ID không khớp thay vì một lỗi not-found khó hiểu ở tầng sâu hơn.

## Bảo mật (`app/security/auth.py`)

`verify_api_key` — kiểm tra một bearer token tĩnh duy nhất: `Authorization: Bearer <token>` với `token == FASTAPI_API_KEY` (từ `config/config.toml`). Không có identity theo user, scope, hay hạn dùng — xem [DESIGN_DECISIONS_vi.md](DESIGN_DECISIONS_vi.md).

## Exception (`app/exceptions/`)

`AppException` là base chung cho lỗi nghiệp vụ (`ThreadNotFoundException`, `RunNotFoundException`, `MessageNotFoundException`, `InvalidIdFormatException`, `BearerMissingException`, `APIKeyIncorrectException`, ...); `app.add_exception_handler` map nó cùng `asyncpg.PostgresError`/`socket.gaierror` (DB không kết nối được) thành response lỗi JSON nhất quán trong `app/app.py`.

## Observability (MLflow + MinIO)

Mỗi lần sinh phản hồi (worker hoặc streaming) đều mở một MLflow span (`SpanType.CHAT_MODEL`) gắn tag `thread_id`/`run_id`/`message_id`/`assistant_id`, với config model, token usage, latency, throughput ghi làm attribute, và text phản hồi làm output của span. `MLFLOW_TRACKING_URI` trỏ tới container `mlflow`; kho artifact/trace của MLflow được backing bởi MinIO (tương thích S3) qua `MLFLOW_S3_ENDPOINT_URL`. MinIO hiện chưa được expose cho code ứng dụng để lưu file người dùng — chỉ phục vụ MLflow.
