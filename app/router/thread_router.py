# FastAPI components
from fastapi import APIRouter, Depends, Body
# Schema
from app.schemas.threads import (ThreadObject,
                                 CreateThreadRequest,
                                 DeletedThreadResponse)
from app.schemas.runs.requests import CreateThreadRunRequest
# Exception
from app.exceptions.postgres import PostgresConnectionException
from app.exceptions import InvalidIdFormatException

# Postgres Components
from app.startup import get_postgres_pool, get_model
from app.db.postgres import PostgresThreadStore
# Utils
from app.utils.id_generation import generate_assistant_object
# Thread service
from app.services.threads import ThreadService
# Run dispatch
from app.services.runs import RunDispatchService
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# Other components
import asyncpg, socket

# Define router
thread_router = APIRouter()

@thread_router.post("/threads",
                    summary = "[Thread] Create a thread",
                    response_model = ThreadObject)
async def create_thread(payload: CreateThreadRequest = Body(default = CreateThreadRequest()),
                        api_key: str = Depends(verify_api_key)):
    """
    ## Create a thread with optional messages and metadata.

    Reference: [OpenAI Create Thread API](https://platform.openai.com/docs/api-reference/threads/createThread)
    
    ### Args
        - `messages` (Optional[List[ChatMessage]]): A list of messages to start the thread with. Default: None
        - `metadata` (Optional[Dict[str, Any]]): Set of 16 key-value pairs that can be attached to the thread. Default: {}
        - `tool_resources` (Optional[ToolResource]): A set of resources that are made available to the assistant's tools in this thread. Default: {}
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()

    try:
        # Create thread and persist any seed messages
        return await ThreadService.create_thread(postgres_pool = postgres_pool, payload = payload)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        SystemLogger.error(f"[THREAD_ROUTER] Failed to create thread: {e}")
        raise PostgresConnectionException()

@thread_router.post("/threads/runs",
                    summary = "[Thread] Create thread and run")
async def create_thread_and_run(request: CreateThreadRunRequest,
                                api_key: str = Depends(verify_api_key)):
    """
    ## Create a thread and run it with an assistant.

    Reference: [OpenAI Create Thread and Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create_and_run)

    ### Args
        - `request` (CreateThreadRunRequest): The thread and run creation request containing assistant ID, optional thread configuration, and run parameters.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    llm = get_model()

    # Check assistant_id
    if not request.assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input=request.assistant_id,
                                       params="assistant_id",
                                       prefix="asst")

    # Default value
    run_id = generate_assistant_object(object="run")
    step_id = generate_assistant_object(object="step")
    message_id = generate_assistant_object(object="message")
    thread_id = generate_assistant_object(object = "thread")

    # Normally here you'd forward request to OpenAI or process internally
    try:
        # Create new thread
        await PostgresThreadStore.insert_thread(pool = postgres_pool,
                                                thread_id = thread_id)

        # Resolve instructions/temperature/top_p, falling back to the assistant's own config
        instructions, temperature, top_p = await RunDispatchService.resolve_run_params(
            postgres_pool, request.assistant_id, request.instructions, request.temperature, request.top_p)

        # Enqueue background generation or return a streaming response
        return await RunDispatchService.dispatch_run(postgres_pool = postgres_pool,
                                                      llm = llm,
                                                      request = request,
                                                      thread_id = thread_id,
                                                      run_id = run_id,
                                                      step_id = step_id,
                                                      message_id = message_id,
                                                      instructions = instructions,
                                                      temperature = temperature,
                                                      top_p = top_p,
                                                      endpoint_path = "/v1/threads/runs")
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[THREAD_ROUTER] Failed to create thread and run: {e}")
        raise PostgresConnectionException()

@thread_router.get("/threads/{thread_id}",
                   summary = "[Thread] Retrieve a thread",
                   response_model = ThreadObject)
async def retrieve_thread(thread_id: str,
                          api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a thread by its ID.

    Reference: [OpenAI Get Thread API](https://platform.openai.com/docs/api-reference/threads/getThread)
    
    ### Args
        - `thread_id` (str): The ID of the thread to retrieve.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()

    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id,
                                       params = "thread_id")
    # Get information from thread
    try:
        return await ThreadService.retrieve_thread(postgres_pool = postgres_pool, thread_id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[THREAD_ROUTER] Failed to retrieve thread {thread_id}: {e}")
        raise PostgresConnectionException()

@thread_router.delete("/threads/{thread_id}",
                      summary = "[Thread] Delete a thread",
                      response_model = DeletedThreadResponse)
async def delete_thread(thread_id: str,
                        api_key: str = Depends(verify_api_key)):
    """
    ## Delete a thread by its ID.

    Reference: [OpenAI Delete Thread API](https://platform.openai.com/docs/api-reference/threads/deleteThread)
    
    ### Args
        - `thread_id` (str): The ID of the thread to delete.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()

    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    try:
        # Try delete
        return await ThreadService.delete_thread(postgres_pool = postgres_pool, thread_id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[THREAD_ROUTER] Failed to delete thread {thread_id}: {e}")
        raise PostgresConnectionException()