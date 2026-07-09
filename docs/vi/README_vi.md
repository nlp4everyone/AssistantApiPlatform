# 🤖 AssistantApiPlatform

Nói đơn giản — đây là một backend làm sẵn cho một trợ lý AI (chatbot): nó nhớ được hội thoại, xử lý được nhiều yêu cầu cùng lúc mà không bị treo, và lưu lại đầy đủ mọi câu trả lời đã tạo ra, để bạn không phải tự xây những phần đó từ đầu. Bạn chỉ cần mang theo mô hình AI; AssistantApiPlatform lo mọi thứ còn lại xung quanh nó.

Backend **tương thích với OpenAI Assistants API** — assistants, threads, messages và runs — xây dựng bằng FastAPI, lưu trữ trên PostgreSQL, điều phối qua hàng đợi task Redis Stream (TaskIQ), và trace toàn bộ bằng MLflow.

Bạn tự mang LLM server tương thích OpenAI (vLLM, SGLang, ...); AssistantApiPlatform lo phần lưu trữ, trạng thái hội thoại, sinh phản hồi nền, streaming, và observability xung quanh nó.

<br />

## Tính năng chính

- **Tương thích OpenAI Assistants API** — `assistants`, `threads`, `messages`, `runs` có cùng cấu trúc và ngữ nghĩa như OpenAI SDK (`client.beta.threads...`), bao gồm cả `create_thread_and_run`
- **Sinh phản hồi nền** — các run không streaming được đẩy sang worker TaskIQ qua Redis Streams thay vì chặn request; row của run được ghi đồng bộ trước khi trả response, nên client có thể `GET` run ngay lập tức mà không bị đua với hàng đợi
- **Streaming** — các run streaming bỏ qua hàng đợi hoàn toàn, sinh Server-Sent Events ngay trên task xử lý request
- **An toàn khi bị redeliver, ngay từ thiết kế** — cơ chế redeliver của consumer group trong Redis Streams được xem là chuyện bình thường sẽ xảy ra, không phải thứ cần né tránh: các insert run/message dùng `ON CONFLICT DO NOTHING`, và một run đã ở trạng thái kết thúc thì không bao giờ bị xử lý lại
- **Observability đầy đủ** — mỗi lần sinh phản hồi là một MLflow span được gắn tag `thread_id`/`run_id`/`message_id`/`assistant_id`, cùng token usage và latency ghi làm span attribute; artifact lưu ở MinIO (tương thích S3)
- **Cấu hình theo tầng** — biến môi trường cho hạ tầng/secret (`.env`), TOML cho tham số tương tác tĩnh (`config/config.toml`), giá trị mặc định trong code làm phương án cuối

<br />

## Điều kiện tiên quyết: LLM Serving Backend

AssistantApiPlatform không tự chạy inference — nó chuyển tiếp chat completion tới một endpoint **tương thích OpenAI** bên ngoài (ví dụ [vLLM](https://github.com/vllm-project/vllm) hoặc [SGLang](https://github.com/sgl-project/sglang)) và đảm nhiệm mọi thứ còn lại (lưu trữ, threading, đẩy tác vụ nền, tracing) xung quanh nó. Xem [framework_benchmarks.md](../framework_benchmarks.md) để so sánh vLLM và SGLang trên các model Qwen3.

Trỏ `LLM_BASE_URL` (bên dưới) tới bất kỳ server nào hiện thực `POST /v1/chat/completions`.

<br />

## Cài đặt

```bash
git clone https://github.com/nlp4everyone/AssistantApiPlatform.git
cd AssistantApiPlatform/
cp .env.sample .env
```

Cấu hình LLM server bên ngoài trong `.env`:
```
LLM_MODEL_NAME=Qwen/Qwen3-4B-AWQ
LLM_BASE_URL=http://172.17.0.1:8100/v1
SERVING_API_KEY=token
```

> Hạ tầng/secret (port, thông tin đăng nhập DB, endpoint LLM) nằm trong `.env` (không version-controlled). API key nhận request (`FASTAPI_API_KEY`) và tham số tương tác tĩnh nằm trong `config/config.toml` (version-controlled). Xem [CONFIGURATION.md](../CONFIGURATION.md).

Chạy bằng Docker Compose:
```bash
make up      # build + khởi động postgres, redis, web, worker, mlflow, minio
make logs    # xem log web + worker
make ps      # trạng thái service
make down    # dừng toàn bộ
```

API được phục vụ tại `http://localhost:8005/v1`; giao diện MLflow tại `http://localhost:5000`.

<br />

## Bắt đầu nhanh (Python Client)

AssistantApiPlatform hiện thực cùng cấu trúc resource như OpenAI Assistants API, nên SDK Python chính thức `openai` chạy được ngay — chỉ cần trỏ `base_url` về AssistantApiPlatform và dùng bearer token khớp `FASTAPI_API_KEY`.

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

Thư mục `examples/` có sẵn script chạy được cho từng resource:

```bash
python examples/assistant_example.py
python examples/thread_example.py
python examples/message_example.py
python examples/run_example.py
python examples/streaming_run_example.py
```

<br />

## Tích hợp

- **API framework**: FastAPI
- **LLM client**: OpenAI Python SDK (`AsyncOpenAI`), trỏ tới bất kỳ serving backend tương thích OpenAI nào
- **Lưu trữ**: PostgreSQL (`asyncpg`) — assistants, threads, messages, runs
- **Hàng đợi task**: Redis Streams qua [TaskIQ](https://taskiq-python.github.io/) — sinh phản hồi nền, giao at-least-once qua consumer group
- **Observability**: MLflow (tracing, token usage, latency) + MinIO (kho artifact tương thích S3)
- **Runtime**: Docker Compose (`docker/compose_db.yml` + `compose_web.yml` + `compose_tracking.yml`, gộp qua `Makefile`)

<br />

## Tài liệu

- [Technical Overview](TECHNICAL_OVERVIEW_vi.md) — sơ đồ kiến trúc, danh sách HTTP endpoint, luồng request tổng quan
- [Detailed Flow](FLOW_vi.md) — luồng chi tiết create-run → dispatch → worker nền → hoàn tất, gồm cả đường xử lý redelivery/idempotency
- [Detailed Components](DETAILED_COMPONENTS_vi.md) — phân tích từng router/service/store
- [Design Decisions](DESIGN_DECISIONS_vi.md) — lý do, đánh đổi, và phương án thay thế cho từng quyết định kiến trúc lớn
- [Configuration Reference](../CONFIGURATION.md) — mọi tham số cấu hình, nguồn gốc, và giá trị mặc định

<br />

## Hạn chế hiện tại / Roadmap

### ✅ Đã có
- [x] Assistants, threads, messages, runs (CRUD + list phân trang theo cursor)
- [x] Chạy run nền (queued) và streaming (SSE)
- [x] MLflow trace kèm token usage + latency cho mỗi lần sinh

<br />

## Model Citation

Model mẫu mặc định: **Qwen3** — https://huggingface.co/Qwen
