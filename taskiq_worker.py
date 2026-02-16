from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker
from app.startup import init_postgres, init_model
from app.services.background import handle_generation_response
from app.core.config import REDIS_URL

# Initialize Redis broker and result backend for task queue
result_backend = RedisAsyncResultBackend(redis_url=REDIS_URL)
broker = RedisStreamBroker(url=REDIS_URL).with_result_backend(result_backend)

@broker.task
async def run_background_llm(thread_id: str,
                             run_id: str,
                             request: dict,
                             assistant_id: str,
                             instructions: str,
                             message_id: str = None,
                             temperature: float = None,
                             top_p: float = None):
    """
    Background task to run LLM generation and store results.
    
    This task initializes the necessary dependencies (PostgreSQL and LLM),
    processes the generation request, and stores the results in the database.
    
    Args:
        thread_id: ID of the conversation thread
        run_id: Unique identifier for this generation run
        request: The generation request payload
        assistant_id: ID of the assistant handling the request
        instructions: System instructions for the LLM
        message_id: Optional ID of the message being processed
        temperature: Optional sampling temperature for generation
        top_p: Optional top-p sampling parameter
        
    Returns:
        None
    """
    # Initialize PostgreSQL connection
    postgres_client = init_postgres()
    # Wait for connection pool to be ready
    await postgres_client._create_pool()
    
    # Initialize LLM model
    llm = await init_model()

    # Process the generation request and store results
    await handle_generation_response(postgres_pool=postgres_client.pool,
                                     llm=llm,
                                     thread_id=thread_id,
                                     request=request,
                                     run_id=run_id,
                                     assistant_id=assistant_id,
                                     instructions=instructions,
                                     message_id=message_id,
                                     temperature=temperature,
                                     top_p=top_p)
    return None