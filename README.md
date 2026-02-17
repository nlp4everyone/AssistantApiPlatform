# 🛸 Introduction:
A fully modular, production-ready LLM Assistant framework built with FastAPI and vLLM, integrating PostgreSQL, Redis + TaskIQ, MLflow, and MinIO for a complete AI lifecycle — from request handling to background tasks, experiment tracking, and artifact storage.

This repository demonstrates how to design an OpenAI-style conversational assistant with persistent memory, async background execution, and traceable model performance — all running locally and fully open-source.

<br />

# 🧠 Key Features
### 💬 Conversational Flow

- Clean, modular assistant API implementation.

- Each dialogue turn is processed efficiently — maintainable and scalable.

- Stateful user context powered by PostgreSQL + Redis.

<br />

### 🧍 User Management (PostgreSQL)

- Store and manage user accounts, sessions, and chat logs.

- PostgreSQL ensures durable, queryable conversation history and analytics.

<br />

### ⚙️ Background Tasks (Redis + TaskIQ)

- Offload heavy inference or post-processing tasks using TaskIQ + Redis.

- Ideal for streaming inference, embedding generation, or async analytics.

- Scales horizontally with distributed workers.

<br />

### 📊 Model Tracking (MLflow + MinIO)

- Every inference or training run is logged to MLflow.

- Model weights and outputs are stored in MinIO (S3-compatible) for reproducibility.

- Perfect for fine-tuning loops or prompt evaluation experiments.

<br />

### 🧩 Local LLM Runtime (vLLM)

- High-performance local inference using vLLM.

- Supports OpenAI-compatible API format, enabling drop-in replacements.

- Fully offline and GPU-accelerated for enterprise/private deployment.

<br />

# 🔗 Installing:
1. Clone this project:
```
git clone -b assistant/vllm https://github.com/nlp4everyone/PrivateAI.git
```
2. Go inside project:
```
cd PrivateAI/
```
3. Create .env file from .env.sample:
```
cp .env.sample .env
```
4. Run services:
```
bash run_service.sh
```
5. View logs:
```
bash view_log.sh
```
7. Access tracing view:
```
http://localhost:5000/
```
<br />

# 💴 Intergrations:
- 📄 Framework: Langchain
- 💻 Core LLM: vLLM 
- 🐥 Features: Same feature with OpenAI Assistant API (Refer: https://platform.openai.com/docs/api-reference/introduction)
- 🗄️ User Management: Postgres
- 🔔 Task Queue: Redis + TaskIQ
- 📦 Tracking: MLflow + MinIO
- ⚙️ API Layer: FastAPI
- 🧰 Runtime: Docker Compose

<br />

# 📁 Project Structure:
```
ChatEngine/
├── app/                    # Main application code
│   ├── core/              # Core configuration and utilities
│   ├── db/                # Database models and connections
│   ├── exceptions/        # Custom exception handlers
│   ├── router/            # API routes (FastAPI routers)
│   ├── schemas/           # Pydantic models for request/response
│   ├── security/          # Authentication and security
│   ├── services/          # Business logic services
│   ├── startup/           # Application startup configuration
│   └── utils/             # Utility functions
├── config/                # Configuration files
├── docker/                # Docker compose files and Dockerfiles
├── initdb/               # Database initialization scripts
├── loggers/              # Logging configuration
├── requirements/         # Python dependencies
├── .env.sample          # Environment variables template
├── run_service.sh       # Script to start all services
└── view_log.sh          # Script to view service logs
```
<br />

# 🚀 Services:
The application runs multiple services via Docker Compose:
1. **FastAPI Web Application**: Main API server
2. **vLLM Server**: Local LLM inference server
3. **PostgreSQL**: Database for user management and chat history
4. **Redis**: Message broker for background tasks
5. **TaskIQ Worker**: Background task processor
6. **MLflow**: Experiment tracking and model registry
7. **MinIO**: S3-compatible object storage for artifacts

<br />

