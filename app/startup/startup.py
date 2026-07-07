# OpenAI-compatible client
from fastapi import Request
from openai import AsyncOpenAI
from app.db.postgres import PostgresClient
from app.db.minio import MinioService
# Postgres
from asyncpg import PostgresError
import asyncpg
# Config
from app.core.config import *
# Other component
import os, requests, time, asyncio, mlflow, re
# Logger
from loggers import SystemLogger

# Set MLflow params
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
# Correct MLFlow and Minio for logging messages
os.environ["AWS_ACCESS_KEY_ID"] = MINIO_ROOT_USER
os.environ["AWS_SECRET_ACCESS_KEY"] = MINIO_ROOT_PASSWORD
os.environ["MLFLOW_S3_ENDPOINT_URL"] = MLFLOW_S3_ENDPOINT_URL
os.environ["MLFLOW_DEFAULT_ARTIFACT_ROOT"] = MLFLOW_DEFAULT_ARTIFACT_ROOT

async def init_model(base_url :str = None) -> AsyncOpenAI:
    """
    Initialize the LLM model connection.

    Args:
        base_url (str): OpenAI-compatible base URL for the LLM serving endpoint
                        (default: LLM_BASE_URL from environment)

    Returns:
        AsyncOpenAI: Initialized LLM client instance

    Note:
        Tests the connection with a sample message and logs the result.
    """
    base_url = base_url or LLM_BASE_URL
    llm = AsyncOpenAI(base_url = base_url,
                      api_key = SERVING_API_KEY)

    try:
        await llm.chat.completions.create(
            model = LLM_MODEL_NAME,
            messages = [{"role": "user", "content": "Hello"}],
            extra_body = LLM_EXTRA_BODY
        )
        # Response
        SystemLogger.warning(f"[STARTUP] LLM serving connection test successful ({base_url})")
    except Exception as e:
        # Response
        SystemLogger.error(f"[STARTUP] LLM serving connection test failed ({base_url}): {e}")
    return llm

def init_postgres() -> PostgresClient:
    """
    Initialize PostgreSQL database connection.

    Returns:
        PostgresClient: Initialized PostgreSQL client instance
    """
    # Init connection
    postgres_client = PostgresClient(user = POSTGRES_USER,
                                       password = POSTGRES_PASSWORD,
                                       database = POSTGRES_DB,
                                       host = POSTGRES_HOST,
                                       port = POSTGRES_PORT)
    return postgres_client

def init_minio() -> MinioService:
    """
    Initialize MinIO object storage service connection and create MLflow bucket.

    This function sets up the MinIO service connection using environment configuration
    and ensures the required MLflow bucket exists. If the bucket doesn't exist,
    it creates one automatically.

    Returns:
        MinioService: Initialized MinIO service instance

    Raises:
        ValueError: If MLFLOW_DEFAULT_ARTIFACT_ROOT has incorrect format

    Note:
        - Extracts MinIO endpoint from MLFLOW_S3_ENDPOINT_URL
        - Parses bucket name from MLFLOW_DEFAULT_ARTIFACT_ROOT (s3://bucket-name/...)
        - Creates bucket if it doesn't exist for MLflow artifact storage
    """
    # Define url
    minio_endpoint_url = MLFLOW_S3_ENDPOINT_URL.replace("http://","")
    # Get bucket name
    match = re.search(r'^s3://([^/]+)/', MLFLOW_DEFAULT_ARTIFACT_ROOT)

    # Raise exception when not found
    if not match:
        raise ValueError(f"MLFLOW_DEFAULT_ARTIFACT_ROOT with incorrect format: {MLFLOW_DEFAULT_ARTIFACT_ROOT}")
    bucket_name = match.group(1)

    # Init connection
    minio_service = MinioService(endpoint_url = minio_endpoint_url,
                                 access_key = MINIO_ROOT_USER,
                                 secret_key = MINIO_ROOT_PASSWORD)

    # Create bucket for mlflow
    if not minio_service.client.bucket_exists(bucket_name):
        minio_service.client.make_bucket(bucket_name)
        SystemLogger.success(f"Create Minio bucker for MLflow ({bucket_name}) done!")

    return minio_service

def get_model(request: Request) -> AsyncOpenAI:
    """FastAPI dependency returning the LLM client initialized at app startup."""
    return request.app.state.llm

def get_postgres_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency returning the PostgreSQL connection pool initialized at app startup."""
    return request.app.state.postgres_client.pool

def wait_for_serving(base_url :str = None,
                     wait_time :int = 5):
    """
    Wait for the serving service to become available.

    Args:
        base_url (str): OpenAI-compatible base URL for the LLM serving endpoint
                        (default: LLM_BASE_URL from environment)
        wait_time (int): Time to wait between retries in seconds (default: 5)

    Note:
        Blocks until the service health endpoint returns 200 status.
        Polls indefinitely until successful connection.
    """
    # Health endpoint lives at the server root, not under /v1
    base_url = base_url or LLM_BASE_URL
    health_url = base_url.rsplit("/v1", 1)[0].rstrip("/") + "/health"

    # Loop
    while True:
        # Try to send response
        try:
            response = requests.get(health_url)
            if response.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            pass
        # Wait time
        time.sleep(wait_time)

async def wait_for_postgres(pool,
                            retries: int = 5,
                            delay: float = 0.5):
    """
    Wait for PostgreSQL database to become ready.

    Args:
        pool: PostgreSQL connection pool
        retries (int): Number of retry attempts (default: 5)
        delay (float): Delay between retries in seconds (default: 0.5)

    Raises:
        ConnectionRefusedError: If connection fails after all retries
        PostgresError: If database error occurs after all retries

    Note:
        Tests connection with a simple query and logs each attempt.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            # Test the connection with a simple query
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            SystemLogger.warning(f"[STARTUP] PostgreSQL connection established (attempt {attempt}/{retries})")
            return
        except (ConnectionRefusedError, PostgresError) as e:
            last_exc = e
            SystemLogger.error(f"[STARTUP] PostgreSQL connection failed (attempt {attempt}/{retries}): {e!r}")
            if attempt < retries:
                await asyncio.sleep(delay)
