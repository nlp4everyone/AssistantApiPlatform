# FastAPI components
from fastapi import APIRouter, Depends, Body
# Schema
from app.schemas.threads import (ThreadObject,
                                 CreateThreadRequest,
                                 DeletedThreadResponse)
from app.schemas.runs.requests import CreateThreadRunRequest
# Exception
from app.exceptions import InvalidIdFormatException

# Postgres Components
from app.startup import get_postgres_pool, get_model
# Thread service
from app.services.threads import ThreadService
# Run dispatch
from app.services.runs import RunDispatchService
# Security
from app.security.auth import verify_api_key
# Other components
import asyncpg

# Define router
thread_router = APIRouter()

@thread_router.post("/threads",
                    summary = "[Thread] Create a thread",
                    response_model = ThreadObject)
async def create_thread(payload: CreateThreadRequest = Body(default = CreateThreadRequest()),
                        postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                        api_key: str = Depends(verify_api_key)):
    """
    ## Create a thread with optional messages and metadata.

    Reference: [OpenAI Create Thread API](https://platform.openai.com/docs/api-reference/threads/createThread)

    ### Args
        - `messages` (Optional[List[ChatMessage]]): A list of messages to start the thread with. Default: None
        - `metadata` (Optional[Dict[str, Any]]): Set of 16 key-value pairs that can be attached to the thread. Default: {}
        - `tool_resources` (Optional[ToolResource]): A set of resources that are made available to the assistant's tools in this thread. Default: {}
    """
    # Create thread and persist any seed messages
    return await ThreadService.create_thread(postgres_pool = postgres_pool, payload = payload)

@thread_router.post("/threads/runs",
                    summary = "[Thread] Create thread and run")
async def create_thread_and_run(request: CreateThreadRunRequest,
                                postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                                llm = Depends(get_model),
                                api_key: str = Depends(verify_api_key)):
    """
    ## Create a thread and run it with an assistant.

    Reference: [OpenAI Create Thread and Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create_and_run)

    ### Args
        - `request` (CreateThreadRunRequest): The thread and run creation request containing assistant ID, optional thread configuration, and run parameters.
    """
    # Check assistant_id
    if not request.assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input=request.assistant_id,
                                       params="assistant_id",
                                       prefix="asst")

    # Create the thread, persisting any seed metadata/tool_resources/messages from the request
    thread = await ThreadService.create_thread(postgres_pool = postgres_pool,
                                               payload = request.thread or CreateThreadRequest())

    # Generate IDs, resolve run params, and enqueue background generation or stream
    return await RunDispatchService.create_and_dispatch_run(postgres_pool = postgres_pool,
                                                             llm = llm,
                                                             request = request,
                                                             thread_id = thread.id,
                                                             endpoint_path = "/v1/threads/runs")

@thread_router.get("/threads/{thread_id}",
                   summary = "[Thread] Retrieve a thread",
                   response_model = ThreadObject)
async def retrieve_thread(thread_id: str,
                          postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                          api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a thread by its ID.

    Reference: [OpenAI Get Thread API](https://platform.openai.com/docs/api-reference/threads/getThread)

    ### Args
        - `thread_id` (str): The ID of the thread to retrieve.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id,
                                       params = "thread_id")
    # Get information from thread
    return await ThreadService.retrieve_thread(postgres_pool = postgres_pool, thread_id = thread_id)

@thread_router.delete("/threads/{thread_id}",
                      summary = "[Thread] Delete a thread",
                      response_model = DeletedThreadResponse)
async def delete_thread(thread_id: str,
                        postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                        api_key: str = Depends(verify_api_key)):
    """
    ## Delete a thread by its ID.

    Reference: [OpenAI Delete Thread API](https://platform.openai.com/docs/api-reference/threads/deleteThread)

    ### Args
        - `thread_id` (str): The ID of the thread to delete.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Try delete
    return await ThreadService.delete_thread(postgres_pool = postgres_pool, thread_id = thread_id)