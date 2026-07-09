# Quyết định thiết kế

Tài liệu này giải thích lý do đằng sau mỗi lựa chọn kiến trúc quan trọng, kèm phân tích ưu/nhược điểm và các phương án thay thế đã cân nhắc.

---

## 1. Thực thi nền — TaskIQ + Redis Streams

### Mô tả

Các run không streaming được đẩy thành task `run_background_llm` trên một `RedisStreamBroker` (TaskIQ), được tiêu thụ bởi container `taskiq_worker` riêng qua consumer group, thay vì sinh phản hồi ngay trên task xử lý request.

### Ưu điểm

- **Độ trễ request tách rời khỏi độ trễ LLM** — client nhận `RunObject` trạng thái `queued` ngay lập tức; một lần sinh chậm không giữ kết nối HTTP mở
- **Redis Streams cho log bền vững, replay được, có consumer group** — vận hành rẻ hơn RabbitMQ/Kafka ở quy mô này, và package `taskiq-redis` tích hợp trực tiếp với TaskIQ
- **Scale ngang chỉ là thêm consumer vào cùng group** — không cần đổi code để thêm worker replica

### Nhược điểm

- **Giao at-least-once, không phải exactly-once** — worker chết giữa chừng có thể khiến task bị redeliver; ứng dụng phải tự đảm bảo idempotent (xem mục 2)
- **Thêm một thành phần chạy trong production** — Redis và container worker đều nằm trên đường găng của việc sinh phản hồi nền, mỗi cái cần được giám sát riêng

### Phương án thay thế đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Celery + RabbitMQ | Footprint vận hành nặng hơn cho một loại task duy nhất; API async-native của TaskIQ khớp trực tiếp với stack `asyncpg`/`AsyncOpenAI` hiện có |
| `asyncio.create_task` trong process | Không bền vững — process restart làm mất âm thầm các lần sinh đang chạy dở; không fan-out được đa instance |
| Sinh phản hồi đồng bộ (không hàng đợi) | Chặn request suốt thời gian LLM chạy; không khớp với vòng đời run `queued`/`in_progress` của OpenAI Assistants API |

---

## 2. Ghi Idempotent thay vì giao Exactly-Once

### Mô tả

Thay vì cố ngăn redelivery (distributed lock, bảng dedup có TTL), mọi lệnh ghi trên đường sinh phản hồi đều được làm cho an toàn khi lặp lại: `PostgresRunStore.create_run` và `PostgresMessageStore.insert_messages` dùng `ON CONFLICT (id) DO NOTHING`, và `generation_worker.handle_generation_response` kiểm tra `TERMINAL_RUN_STATUSES` trước khi làm bất cứ việc gì.

### Ưu điểm

- **Không tốn chi phí điều phối** — không cần distributed lock, không cần bảng dedup riêng phải giữ đồng bộ với Postgres
- **Đúng với đảm bảo thật sự của broker** — redelivery qua consumer group của Redis Streams (`idle_timeout`, mặc định 10 phút, qua `XAUTOCLAIM`) là một sự kiện vận hành bình thường ở đây, không phải sự cố
- **Dễ suy luận** — cùng một run/message ID luôn map về đúng một row; một task bị redeliver hoặc là no-op hoặc hoàn tất phần việc mà lần thử đầu chưa tới được

### Nhược điểm

- **Vẫn có thể gọi LLM trùng** — nếu worker chết *sau khi* LLM trả lời nhưng *trước khi* `update_run_status(COMPLETED)` commit, một lần redeliver sẽ gọi lại LLM (xem mục 3 để biết vì sao khoảng hở cụ thể này chưa được đóng)
- **Phụ thuộc vào việc mọi insert mới trên đường này đều nhớ thêm `ON CONFLICT`** — một insert mới thêm sau này mà quên sẽ âm thầm đưa lại rủi ro trùng lặp khi redelivery xảy ra

### Phương án thay thế đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Distributed lock theo `run_id` (Redis `SETNX`) | Thêm một failure mode thứ hai (lock hết hạn so với thời lượng task) cho một vấn đề mà `ON CONFLICT DO NOTHING` đã giải quyết ở tầng dữ liệu |
| Bảng dedup theo task ID | Cần thêm bảng + job dọn dẹp; `ON CONFLICT` trên chính các row nghiệp vụ đơn giản hơn và không cần dọn dẹp |

---

## 3. Tạo Run Row đồng bộ, trước khi Dispatch

### Mô tả

`RunDispatchService.create_and_dispatch_run` tự gọi `PostgresRunStore.create_run`, trước khi đẩy task vào hàng đợi hay trả response. Trước đây lệnh insert này chỉ xảy ra bên trong `prepare_generation_context`, tức là sau khi worker đã dequeue task — nên một client gọi `GET /runs/{run_id}` ngay sau khi tạo có thể nhận 404 cho một run mà API vừa báo là `queued`, nếu worker chưa kịp nhận task (hàng đợi đang backlog, worker vừa restart, v.v.).

### Ưu điểm

- **Không còn race GET-ngay-sau-khi-tạo** — khi response rời server, row đã được commit; mọi lần đọc sau đó đều thấy nó
- **Lệnh `create_run` của worker trở thành lưới an toàn idempotent vô hại** (`ON CONFLICT DO NOTHING`) thay vì là nơi ghi duy nhất — không thay đổi hành vi ở đường nhanh, bình thường

### Nhược điểm

- **Thêm một round-trip DB đồng bộ trên đường request** — không đáng kể so với việc đẩy hàng đợi + lệnh gọi LLM sau đó, nhưng giờ nó nằm trên đường găng thay vì được đẩy hết sang worker

### Phương án thay thế đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Trả `status: "queued"` mà không có row, ghi tài liệu về khoảng hở eventual-consistency | Sai lệch âm thầm so với hợp đồng của OpenAI Assistants API, nơi một run ID trả về phải đọc lại được ngay |
| Để client tự retry `GET` với backoff | Đẩy một lỗi phía server sang mọi client tích hợp thay vì sửa một lần cho tất cả |

---

## 4. Hai đường thực thi dùng chung một bước chuẩn bị Context

### Mô tả

Run không streaming (worker nền) và run streaming (SSE tại chỗ) đều gọi `prepare_generation_context` và cùng các helper `build_chat_request` / gắn tag span / `persist_and_complete` / `fail_run` trong `app/services/common/`, thay vì mỗi đường tự hiện thực lại việc ghép message và lưu trữ.

### Ưu điểm

- **Hai đường không thể lệch nhau âm thầm** — một fix bug hay đổi schema ở bước chuẩn bị message tự động áp dụng cho cả hai
- **Streaming bỏ qua hàng đợi hoàn toàn** — không có độ trễ giả tạo do enqueue/dequeue cho một request vốn đã giữ kết nối mở sẵn

### Nhược điểm

- **Streaming không có lưới an toàn redelivery/idempotency** — nếu kết nối request bị rớt giữa chừng, không có consumer group nào để redeliver phần việc đó; client phải tự gọi lại toàn bộ. Đây là đánh đổi được chấp nhận vì SSE vốn gắn chặt với vòng đời của một kết nối.

---

## 5. Sơ đồ ID — UUID có tiền tố

### Mô tả

Mọi ID resource có dạng `f"{prefix}_{uuid4().hex[:24]}"` (`asst_...`, `thread_...`, `msg_...`, `run_...`, `step_...`), được kiểm tra đúng prefix ở tầng path-parameter của FastAPI trước khi vào handler.

### Ưu điểm

- **Khớp với định dạng ID của chính OpenAI Assistants API** — code và tooling của client viết cho API thật không cần đổi định dạng ID
- **Tự mô tả và fail-fast** — một `thread_id` vô tình được truyền vào chỗ cần `run_id` bị từ chối ngay với lỗi 400 ở tầng biên, không phải một lỗi not-found khó hiểu ở sâu bên trong
- **Không cần điều phối để sinh ID** — không cần sequence auto-increment, không cần round-trip tới DB trước khi ID tồn tại (đây chính là điều cho phép sinh ID sớm mà vẫn đồng bộ ở mục 3)

### Nhược điểm

- **Chỉ dùng 24 ký tự hex của UUID4, không phải đủ 32** — tăng nhẹ (gần như không đáng kể ở quy mô dự kiến) xác suất trùng ID so với UUID đầy đủ

---

## 6. Cấu hình theo tầng — Env Var so với TOML so với mặc định trong Code

### Mô tả

Hạ tầng và secret (port, thông tin đăng nhập Postgres/MinIO/MLflow, endpoint LLM bên ngoài) đến từ `.env` (`os.getenv`, không version-controlled). Một số ít giá trị tĩnh — `FASTAPI_API_KEY` nhận request, `REDIS_URL`, và tham số tương tác như `NUMS_OF_PREVIOUS_INTERACTION` — đến từ `config/config.toml` (version-controlled) qua một `TomlConfigLoader` riêng, độc lập với biến môi trường.

### Ưu điểm

- **Secret không bao giờ cần commit** — `.env` nằm trong gitignore; giá trị mặc định trong `config/config.toml` đã commit đều không nhạy cảm
- **Giá trị TOML review được qua diff** — thay đổi `NUMS_OF_PREVIOUS_INTERACTION` hiện trong `git log`, khác với thay đổi biến môi trường trên server

### Nhược điểm — một gotcha thật sự trong cấu hình hiện tại

- **`REDIS_URL` trong `config/config.toml` không có cơ chế override qua biến môi trường.** `app/core/config/redis.py` đọc nó thuần túy từ TOML. `docker/compose_web.yml` set biến môi trường `REDIS_URL` cho container `worker`, nhưng **ứng dụng không bao giờ đọc nó** — broker luôn kết nối bằng giá trị TOML (`redis://redis:6379`), giá trị này trùng khớp với network của compose hiện tại là do trùng hợp, không phải do thiết kế. Đổi `REDIS_PORT` trong `.env` sẽ âm thầm **không** đổi nơi worker thực sự kết nối tới.
- **`DATABASE_URL`, được set làm biến môi trường cho container `worker` trong `compose_web.yml`, hoàn toàn không được dùng** — tham số kết nối Postgres đến từ các biến môi trường riêng lẻ `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_HOST`/`POSTGRES_PORT`.
- **Hai API key trông giống nhau nhưng hai chiều khác nhau**: `FASTAPI_API_KEY` (`config/config.toml`, mặc định `"token"`) xác thực request *đi vào* service này; `SERVING_API_KEY` (`.env`, mặc định `"token"`) là key mà service này gửi *đi ra* LLM server bên ngoài. Cả hai cùng mặc định là chuỗi `"token"` khiến dễ nhầm tưởng chúng là cùng một setting.

Những điều này được ghi lại ở đây thay vì âm thầm sửa, vì việc thay đổi chúng (bỏ các biến môi trường chết, hoặc đấu nối `REDIS_URL`/`DATABASE_URL` để thực sự có tác dụng) là một quyết định vận hành, không chỉ là sửa tài liệu — xem [CONFIGURATION.md](../CONFIGURATION.md) để có bảng tham số đầy đủ.

---

## 7. Xác thực — Bearer Token tĩnh

### Mô tả

`verify_api_key` so sánh header `Authorization: Bearer <token>` với một `FASTAPI_API_KEY` tĩnh, duy nhất, cho mọi request. Không có identity theo user, không có scope, không có cơ chế hết hạn hay xoay vòng token.

### Ưu điểm

- **Khớp với chính định dạng xác thực của OpenAI SDK** (`OpenAI(api_key=...)`) — phía client không cần đổi gì
- **Cực kỳ đơn giản để vận hành cho triển khai single-tenant / nội bộ** — một secret, một chỗ kiểm tra

### Nhược điểm

- **Không hỗ trợ multi-tenant** — mọi caller có token đều truy cập toàn bộ assistant/thread/run; không có cách nào giới hạn một token chỉ trong một tập resource con
- **Không thu hồi được mà không redeploy** — xoay key nghĩa là sửa `config/config.toml` và restart service, không phải revoke một row trong database

### Phương án thay thế đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| API key theo từng user (lưu DB) | Chưa cần thiết — hiện chưa có yêu cầu multi-tenant; sẽ là bước tự nhiên tiếp theo nếu phát sinh nhu cầu |
| OAuth2 / JWT | Độ phức tạp tăng đáng kể cho một backend hiện chỉ phục vụ client nội bộ đáng tin cậy |

---

## 8. Tools / Function Calling — Chấp nhận nhưng chưa thực thi

### Mô tả

`CreateAssistantRequest`/`CreateRunRequest` chấp nhận `tools`/`tool_choice` (kể cả entry dạng `code_interpreter`, để tương thích API) và lưu lại, nhưng `build_chat_request` không bao giờ chuyển chúng tới `llm.chat.completions.create`, và không có vòng lặp thực thi tool call nào trong `app/services/`.

### Ưu điểm

- **Giữ cấu trúc request/response tương thích** với client viết cho OpenAI Assistants API thật, kể cả trước khi có thực thi tool
- **Không có sandbox thực thi nửa vời cần bảo mật** — chạy `code_interpreter` an toàn là cả một dự án riêng; không giả vờ hỗ trợ tránh được cảm giác an toàn giả

### Nhược điểm

- **Client set `tools` và mong đợi nhận lại tool call sẽ âm thầm nhận text thường thay vào đó** — không có lỗi hay cảnh báo rằng tools hiện là no-op. Được ghi rõ ở đây và trong [README_vi.md](README_vi.md#hạn-chế-hiện-tại--roadmap) vì việc schema chấp nhận field này có thể khiến người đọc hiểu nhầm là "đã hỗ trợ."

---

## 9. Observability — MLflow Tracing + MinIO

### Mô tả

Mỗi lần sinh phản hồi mở một MLflow span gắn tag 4 ID resource (`thread_id`, `run_id`, `message_id`, `assistant_id`) và ghi token usage/latency/throughput làm attribute. Backend store của MLflow là Postgres (một database `mlflow` riêng) và kho artifact/trace là MinIO (tương thích S3), thay vì đĩa cục bộ.

### Ưu điểm

- **Mọi lần sinh phản hồi đều truy vết được về đúng thread/run/message** đã tạo ra nó — thiết yếu khi debug một phản hồi tệ mà user báo cáo cụ thể
- **MinIO cho ngữ nghĩa S3 ngay tại chỗ** — cùng cấu hình `MLFLOW_S3_ENDPOINT_URL`/artifact-root chạy được không đổi với S3 thật khi triển khai lên cloud

### Nhược điểm

- **Thêm hai container phải chạy và giám sát** (`mlflow`, `minio`) ngoài bộ API/worker/Postgres/Redis lõi
- **Log MLflow bất đồng bộ (`mlflow.config.enable_async_logging()`) nghĩa là trace có thể trễ hơn một chút so với request thật** — chấp nhận được cho mục đích observability, không phù hợp nếu có lúc cần trace đồng bộ

---

## 10. Độ tin cậy của Worker — `restart: always` + Healthcheck kiểm tra Redis

### Mô tả

Service `worker` trong `docker/compose_web.yml` được set `restart: always` và một `healthcheck` chạy `redis.from_url(REDIS_URL).ping()` từ bên trong container mỗi 15 giây. Điều kiện `depends_on.worker` của `web` được nâng từ `service_started` lên `service_healthy` cho khớp.

### Ưu điểm

- **Worker crash (OOM, exception chưa bắt lúc khởi động, ...) tự khởi động lại** thay vì để task trong hàng đợi Redis mắc kẹt mà không ai tiêu thụ và không có cảnh báo
- **Healthcheck kiểm tra đúng thứ quan trọng với một worker không có HTTP endpoint** — khả năng kết nối tới broker của nó — thay vì chỉ "process còn tồn tại"

### Nhược điểm

- **Riêng trạng thái healthcheck của Docker không tự kích hoạt restart** — `restart: always` chỉ xử lý khi process chết; một worker unhealthy nhưng vẫn sống (ví dụ deadlock trong khi vẫn giữ kết nối Redis) cần một công cụ giám sát bên ngoài (hoặc như `autoheal`) hành động dựa trên health status để được tự động phát hiện
- **Vòng lặp crash (ví dụ một bản deploy lỗi) sẽ restart vô hạn** thay vì backoff hay báo động sau N lần thử — chấp nhận được với triển khai 1 replica hiện tại, cần xem lại trước khi chạy nhiều worker replica

### Phương án thay thế đã cân nhắc

| Phương án | Lý do không chọn |
|---|---|
| Không healthcheck, chỉ `restart: always` | Mất tín hiệu `depends_on: condition: service_healthy` mà các service khác (Postgres/Redis/MLflow) đã dùng; `web` có thể khởi động trước khi worker thực sự kết nối được Redis |
| Endpoint HTTP healthcheck cho worker | Cần thêm một HTTP server chỉ để health, trong một process vốn chỉ để tiêu thụ hàng đợi — ping Redis là tín hiệu đúng bản chất hơn với cùng chi phí |

---

## 11. Connection Pooling Postgres — Pool theo từng Process

### Mô tả

Mỗi process (mỗi `uvicorn` worker theo `NUM_WORKERS`, và process `taskiq_worker` duy nhất) sở hữu `asyncpg.Pool` riêng (`min_size=5`, `max_size=10`), tạo một lần lúc khởi động và tái sử dụng cho mọi request/task trong process đó.

### Ưu điểm

- **Không cần điều phối liên process** — `asyncpg.Pool` không an toàn khi fork, nên pool theo từng process là mô hình đúng ở đây, không phải một hạn chế
- **Giới hạn tài nguyên rõ ràng theo process** — `max_size=10` giới hạn số kết nối Postgres đồng thời mà một process có thể giữ

### Nhược điểm

- **Tổng số kết nối tăng theo `NUM_WORKERS` × kích thước pool**, cộng với pool riêng của worker — cần tính toán tường minh theo `max_connections` của Postgres khi `NUM_WORKERS` hoặc số worker replica tăng, thay vì tự giới hạn
- **Một đường sinh phản hồi bận rộn (nhiều run đồng thời trong một worker process) có thể làm cạn pool 10 kết nối của process đó**, xếp hàng ở `pool.acquire()` thay vì fail nhanh — hiện chưa có giới hạn concurrency tường minh nào trên worker TaskIQ gắn với kích thước pool
