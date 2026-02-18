# Langchain component
from langchain_openai import ChatOpenAI
from app.db.postgres import PostgresClient
from app.db.minio import MinioService
# Postgres
from asyncpg import PostgresError
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

async def init_model(serving_service_name :str = "vllm",
                     port :int = 8000):
    """
    Initialize the LLM model connection.
    
    Args:
        serving_service_name (str): Name of the serving service (default: "vllm")
        port (int): Port number for the service (default: 8000)
    
    Returns:
        ChatOpenAI: Initialized LLM model instance
        
    Note:
        Tests the connection with a sample message and logs the result.
    """
    global llm
    llm = ChatOpenAI(model = LLM_MODEL_NAME,
                     base_url = f"http://{serving_service_name}:{port}/v1",
                     streaming = True,
                     api_key = SERVING_API_KEY,
                     extra_body={
                         "chat_template_kwargs": {"enable_thinking": False}
                     })

    try:
        resp = await llm.ainvoke("Hello")
        # Response
        SystemLogger.warning(f"[STARTUP] {serving_service_name.capitalize()} service connection test successful")
    except Exception as e:
        # Response
        SystemLogger.error(f"[STARTUP] {serving_service_name.capitalize()} service connection test failed: {e}")
    return llm

def init_postgres():
    """
    Initialize PostgreSQL database connection.
    
    Returns:
        PostgresClient: Initialized PostgreSQL client instance
        
    Note:
        Creates a global postgres_client instance for database operations.
    """
    global postgres_client
    # Init connection
    postgres_client = PostgresClient(user = POSTGRES_USER,
                                       password = POSTGRES_PASSWORD,
                                       database = POSTGRES_DB,
                                       host = POSTGRES_HOST,
                                       port = 5432)
    return postgres_client

def init_minio():
    """
    Initialize MinIO object storage service connection and create MLflow bucket.
    
    This function sets up the MinIO service connection using environment configuration
    and ensures the required MLflow bucket exists. If the bucket doesn't exist,
    it creates one automatically.
    
    Global Variables:
        minio_service: Global MinioService instance for object storage operations
        
    Raises:
        ValueError: If MLFLOW_DEFAULT_ARTIFACT_ROOT has incorrect format
        
    Note:
        - Extracts MinIO endpoint from MLFLOW_S3_ENDPOINT_URL
        - Parses bucket name from MLFLOW_DEFAULT_ARTIFACT_ROOT (s3://bucket-name/...)
        - Creates bucket if it doesn't exist for MLflow artifact storage
    """
    global minio_service
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

def get_model():
    """
    Get the globally initialized LLM model instance.
    
    Returns:
        ChatOpenAI: The initialized LLM model
        
    Raises:
        NameError: If model has not been initialized
    """
    return llm

def get_postgres_pool():
    """
    Get the PostgreSQL connection pool.
    
    Returns:
        asyncpg.Pool: PostgreSQL connection pool
        
    Raises:
        NameError: If PostgreSQL client has not been initialized
    """
    return postgres_client.pool

def wait_for_serving(serving_service_name :str = "vllm",
                     serving_port :int = 8000,
                     wait_time :int = 5):
    """
    Wait for the serving service to become available.
    
    Args:
        serving_service_name (str): Name of the serving service (default: "vllm")
        serving_port (int): Port number for the service (default: 8000)
        wait_time (int): Time to wait between retries in seconds (default: 5)
        
    Note:
        Blocks until the service health endpoint returns 200 status.
        Polls indefinitely until successful connection.
    """
    # Define url
    serving_url = f"http://{serving_service_name}:{serving_port}"

    # Loop
    while True:
        # Try to send response
        try:
            response = requests.get(f"{serving_url}/health")
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