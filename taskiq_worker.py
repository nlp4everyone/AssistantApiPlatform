from taskiq import TaskiqEvents, TaskiqDepends, Context
from taskiq.state import TaskiqState
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker
from app.startup import init_postgres, init_model
from app.services.background import handle_generation_response
from app.core.config import REDIS_URL

# Initialize Redis broker and result backend for task queue
result_backend = RedisAsyncResultBackend(redis_url=REDIS_URL)
broker = RedisStreamBroker(url=REDIS_URL).with_result_backend(result_backend)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def on_worker_startup(state: TaskiqState) -> None:
    """Initialize the Postgres pool and LLM client once per worker process."""
    postgres_client = init_postgres()
    await postgres_client._create_pool()

    state.postgres_client = postgres_client
    state.llm = await init_model()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def on_worker_shutdown(state: TaskiqState) -> None:
    """Close the Postgres pool when the worker process shuts down."""
    await state.postgres_client.close()


@broker.task
async def run_background_llm(thread_id: str,
                             run_id: str,
                             request: dict,
                             assistant_id: str,
                             instructions: str,
                             message_id: str = None,
                             temperature: float = None,
                             top_p: float = None,
                             endpoint_path: str = None,
                             context: Context = TaskiqDepends()):
    """
    Background task to run LLM generation and store results.

    Reuses the Postgres pool and LLM client initialized once at worker
    startup (see on_worker_startup) instead of reconnecting per task.

    Args:
        thread_id: ID of the conversation thread
        run_id: Unique identifier for this generation run
        request: The generation request payload
        assistant_id: ID of the assistant handling the request
        instructions: System instructions for the LLM
        message_id: Optional ID of the message being processed
        temperature: Optional sampling temperature for generation
        top_p: Optional top-p sampling parameter
        endpoint_path: Optional endpoint path for span naming
        context: Injected by taskiq; provides access to the worker's shared state

    Returns:
        None
    """
    # Process the generation request and store results
    await handle_generation_response(postgres_pool=context.state.postgres_client.pool,
                                     llm=context.state.llm,
                                     thread_id=thread_id,
                                     request=request,
                                     run_id=run_id,
                                     assistant_id=assistant_id,
                                     instructions=instructions,
                                     message_id=message_id,
                                     temperature=temperature,
                                     top_p=top_p,
                                     endpoint_path=endpoint_path)
    return None