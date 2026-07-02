# FastAPI components
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
# Schema
from app.schemas.threads import (ThreadObject,
                                 CreateThreadRequest,
                                 DeletedThreadResponse)
from app.schemas.messages import (MessageTextContent,
                                  ContentItem,
                                  MessageObject)
from app.schemas.runs.requests import CreateThreadRunRequest
from app.schemas.runs import RunObject
# Exception
from app.exceptions.postgres import PostgresConnectionException
from app.exceptions import InvalidIdFormatException

# Postgres Components
from app.startup import get_postgres_pool, get_model
from app.db.postgres import PostgresThreadStore, PostgresMessageStore
from app.db.postgres import PostgresAssistantStore
# Utils
from app.utils.id_generation import generate_assistant_object
from app.services.streaming import handle_streaming_response
from app.utils.messaging import _update_assistant_response
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# TaskIQ worker
from taskiq_worker import run_background_llm
# Prompt
from app.core.config.prompts import DEFAULT_ASSISTANT_PROMPT
# Other components
import time, asyncpg, socket

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
    # Generate new thread
    thread_id = generate_assistant_object()
    # Postgres Service
    postgres_pool = get_postgres_pool()

    # Time in second
    created_at_seconds = int(time.time())

    # Define data
    data = ThreadObject(id = thread_id,
                        created_at = created_at_seconds,
                        metadata = payload.metadata or {},
                        tool_resources = payload.tool_resources or {}).model_dump()

    # Not message in input
    output_messages = []

    # When payload is not None
    if payload.messages is not None:
        for input_message in payload.messages:
            # Define value
            msg_id = generate_assistant_object(object = "message")
            # Text content
            text_content = MessageTextContent(value = input_message.content)
            content = [ContentItem(text = text_content)]
            # Append
            output_messages.append(MessageObject(id = msg_id,
                                                 created_at = created_at_seconds,
                                                 thread_id = thread_id,
                                                 role = input_message.role,
                                                 content = content).model_dump())
    # Update to data
    data.update({"data": output_messages})

    try:
        # Create new thread
        await PostgresThreadStore.insert_thread(pool = postgres_pool,
                                                thread_id = thread_id,
                                                metadata = payload.metadata,
                                                tool_resources = payload.tool_resources.model_dump())

        # Add message if has message
        if len(output_messages) > 0:
            await PostgresMessageStore.insert_messages(pool = postgres_pool,
                                                       data = data,
                                                       thread_id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        SystemLogger.error(f"[THREAD_ROUTER] Failed to create thread {thread_id}: {e}")
        raise PostgresConnectionException()
    except Exception as e:
        SystemLogger.error(f"[THREAD_ROUTER] Unexpected error creating thread {thread_id}: {e}")

    # Return
    return ThreadObject(id = thread_id,
                        created_at = created_at_seconds,
                        metadata = payload.metadata or {},
                        tool_resources = payload.tool_resources or {})

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
        # Get assistant info
        assistant_info = await PostgresAssistantStore.get_assistant(pool = postgres_pool,
                                                            assistant_id = request.assistant_id)
        # Normalize ssistant info
        assistant_objects = _update_assistant_response([assistant_info])
        assistant_info = assistant_objects[0]
        instructions = request.instructions if request.instructions else assistant_info.instructions or DEFAULT_ASSISTANT_PROMPT
        # Get output params for both streaming and non-streaming modes
        temperature = request.temperature if isinstance(request.temperature, float) else assistant_info.temperature
        top_p = request.top_p if isinstance(request.top_p, float) else assistant_info.top_p
        
        if not request.stream:
            # Run in background
            await run_background_llm.kiq(thread_id,
                                        run_id,
                                        request,
                                        request.assistant_id,
                                        instructions,
                                        message_id,
                                        temperature,
                                        top_p,
                                        "/v1/threads/runs")
            # Not in stream mode
            return RunObject(id = run_id,
                             created_at = int(time.time()),
                             assistant_id = request.assistant_id,
                             thread_id = thread_id,
                             status = "queued",
                             model = request.model,
                             completed_at = int(time.time()),
                             temperature = temperature,
                             top_p = top_p,
                             max_prompt_tokens = request.max_prompt_tokens,
                             max_completion_tokens = request.max_completion_tokens)

        # Streaming
        return StreamingResponse(handle_streaming_response(llm = llm,
                                                           postgres_pool=postgres_pool,
                                                           run_id=run_id,
                                                           thread_id=thread_id,
                                                           message_id=message_id,
                                                           step_id=step_id,
                                                           assistant_id =  request.assistant_id,
                                                           request = request.model_dump(),
                                                           instructions = instructions,
                                                           temperature = temperature,
                                                           top_p = top_p,
                                                           endpoint_path = "/v1/threads/runs"),
                                 media_type="text/event-stream")
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
        thread_info = await PostgresThreadStore.get_thread(pool = postgres_pool,
                                                           thread_id = thread_id)
        # Return
        return ThreadObject(id = thread_info.get("id"),
                            created_at = int(thread_info.get("created_at").timestamp()),
                            metadata = thread_info.get("metadata", {}),
                            tool_resources = thread_info.get("tool_resources", {}))

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
        await PostgresThreadStore.delete_thread(pool = postgres_pool, thread_id = thread_id)
        # Return
        return DeletedThreadResponse(id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[THREAD_ROUTER] Failed to delete thread {thread_id}: {e}")
        raise PostgresConnectionException()