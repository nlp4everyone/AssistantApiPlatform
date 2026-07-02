from fastapi import FastAPI
# Define startup
from .startup import *
# Router
from .router import (thread_router,
                     assistant_router,
                     message_router,
                     run_router)
# Exception
from .exceptions import AppException
from .exceptions.handlers import common_exception_handler
# Config
from .core.config import *

# Components
import time, logging
# Logger
from loggers import SystemLogger
logging.getLogger("uvicorn.error").propagate = False

# Tags
tags_metadata = [
    {
        "name": "Chat Completion",
        "description": "Contains functions for chat completion",
    },
    {
        "name": "Assistant",
        "description": "Contains features related to Assistant",
    }
]
# Define app
app = FastAPI(openapi_tags = tags_metadata)

# Add assistant route
app.include_router(assistant_router,
                   prefix = "/v1",
                   tags = [tags_metadata[1].get("name")])
# # Add thread route
app.include_router(thread_router,
                   prefix = "/v1",
                   tags = [tags_metadata[1].get("name")])
# Add message route
app.include_router(message_router,
                   prefix = "/v1/threads",
                   tags = [tags_metadata[1].get("name")])
# Add run route
app.include_router(run_router,
                   prefix = "/v1/threads",
                   tags = [tags_metadata[1].get("name")])
# Add exception
app.add_exception_handler(AppException, common_exception_handler)

@app.on_event("startup")
async def startup_event():
    SystemLogger.info("[APP] Starting application warm up...")
    # Start
    start = time.perf_counter()
    # # Wait until vllm done
    wait_for_serving(serving_service_name = SERVING_SERVICE_NAME,
                     serving_port = 8000) # Default port for vLLM
    # # Init ml model
    await init_model(serving_service_name = SERVING_SERVICE_NAME,
                     port = 8000) # Default port for vLLM
    SystemLogger.info("[APP] ✅ Serving LLM ready")
    # Init Postgres
    postgres_client = init_postgres()
    # Create pool and wait for postgres
    await postgres_client._create_pool()
    await wait_for_postgres(postgres_client.pool)
    # Create table if not existed
    await postgres_client._create_table()
    # Init Minio
    init_minio()
    SystemLogger.info("[APP] ✅ MinIO ready")

    # Logging
    SystemLogger.info("[APP] ✅ Postgres ready")
    SystemLogger.success(f"[APP] Service started in {round(time.perf_counter() - start,1)}s")