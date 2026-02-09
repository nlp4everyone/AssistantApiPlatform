# FastAPI components
from fastapi import APIRouter, Depends, Body
# Schema
from app.schemas.threads import (ThreadObject,
                                 CreateThreadRequest,
                                 DeletedThreadResponse)
from app.schemas.messages import (MessageTextContent,
                                  ContentItem,
                                  MessageObject)
# Exception
from app.exceptions.postgres import PostgresConnectionException
from app.exceptions import InvalidIdFormatException

# Postgres Components
from app.startup import get_postgres_pool
from app.db.postgres import PostgresThreadStore, PostgresMessageStore

# Utils
from app.utils.id_generation import generate_assistant_object
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# Other components
import time, asyncpg, socket

# Define router
thread_router = APIRouter()

@thread_router.post("/threads", response_model = ThreadObject)
async def create_thread(payload: CreateThreadRequest = Body(default = CreateThreadRequest()),
                        api_key: str = Depends(verify_api_key)):
    """
    ## Create a thread with optional messages and metadata.

    Reference: [OpenAI Create Thread API](https://platform.openai.com/docs/api-reference/threads/createThread)
    
    ### Args
        - `payload` (CreateThreadRequest): The thread creation request containing optional messages, metadata, and tool resources.
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
                                                tool_resources = payload.tool_resources if isinstance(payload.tool_resources,dict) else payload.tool_resources.model_dump())

        # Add message if has message
        if len(output_messages) > 0:
            await PostgresMessageStore.insert_message(pool = postgres_pool,
                                                      data = data,
                                                      thread_id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        SystemLogger.error(e)
        raise PostgresConnectionException()

    # Return
    return ThreadObject(id = thread_id,
                        created_at = created_at_seconds,
                        metadata = payload.metadata or {},
                        tool_resources = payload.tool_resources or {})

@thread_router.get("/threads/{thread_id}", response_model = ThreadObject)
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
        SystemLogger.error(e)
        raise PostgresConnectionException()

@thread_router.delete("/threads/{thread_id}", response_model = DeletedThreadResponse)
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
        raise InvalidIdFormatException(input = thread_id,
                                       params = "thread_id")
    try:
        # Try delete
        await PostgresThreadStore.delete_thread(pool = postgres_pool,
                                                thread_id = thread_id)
        # Return
        return DeletedThreadResponse(id = thread_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(e)
        raise PostgresConnectionException()