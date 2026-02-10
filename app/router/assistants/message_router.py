# FastAPI components
from fastapi import APIRouter, Depends
# Object Schema
from app.schemas.common import (ChatMessage,
                                PaginationQueryParams)
from app.schemas.messages import (MessageObject,
                                  MessageListObject,
                                  ContentItem,
                                  DeletedMessageResponse,
                                  MessageTextContent)
# Exceptions
from app.exceptions.postgres import PostgresConnectionException
from app.exceptions import InvalidIdFormatException
# Get Postgres pool
from app.startup import get_postgres_pool
# Postgres Message Store
from app.db.postgres import PostgresMessageStore
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging import _update_messages_response
import time, asyncpg, socket
# Security
from app.security.auth import verify_api_key
# logger
from loggers import SystemLogger
# Typing
from typing import Optional

# Define message router
message_router = APIRouter()

@message_router.post("/{thread_id}/messages", response_model = MessageObject)
async def create_message(thread_id: str,
                         message: ChatMessage,
                         api_key: str = Depends(verify_api_key)):
    """
    ## Create a message in a thread.

    Reference: [OpenAI Create Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/create)

    ### Args
        - `thread_id` (str): The ID of the thread to create the message in.
        - `message` (ChatMessage): The message object containing role, content, attachments, and metadata.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id,
                                       params ="thread_id")
    # Time in second
    created_at_seconds = int(time.time())

    # Process content based on type
    if isinstance(message.content, str):
        # Simple string content
        text_content = MessageTextContent(value = message.content)
        content = [ContentItem(text = text_content)]
    else:
        # Array of content blocks
        content = []
        for block in message.content:
            if block.type == "text":
                text_content = MessageTextContent(value = block.text)
                content.append(ContentItem(text = text_content))
            elif block.type == "image_file":
                # Handle image file content - convert to text content for now
                text_content = MessageTextContent(value = f"[Image file: {block.file_id}]")
                content.append(ContentItem(text = text_content))
            elif block.type == "image_url":
                # Handle image URL content - convert to text content for now
                text_content = MessageTextContent(value = f"[Image URL: {block.image_url.get('url', '')}]")
                content.append(ContentItem(text = text_content))

    # Handle attachments
    attachments = message.attachments if message.attachments else []
    
    # Handle metadata
    metadata = message.metadata if message.metadata else {}

    # Save to MongoDB
    message_object = MessageObject(id = generate_assistant_object(object = "message"),
                                   created_at = created_at_seconds,
                                   thread_id = thread_id,
                                   role = message.role,
                                   content = content,
                                   attachments = attachments,
                                   metadata = metadata).model_dump()

    # Update to data
    data = {"data": [message_object]}
    # No message
    try:
        await PostgresMessageStore.insert_messages(pool = postgres_pool,
                                                   thread_id = thread_id,
                                                   data = data)
        # Return
        return message_object
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(e)
        raise PostgresConnectionException()

@message_router.get("/{thread_id}/messages", response_model = MessageListObject)
async def list_messages(thread_id :str,
                        run_id: Optional[str] = None,
                        query_object :PaginationQueryParams = Depends(),
                        api_key: str = Depends(verify_api_key)):
    """
    ## List messages in a thread.

    Reference: [OpenAI List Messages API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/list)

    ### Args
        - `thread_id` (str): The ID of the thread to list messages from.
        - `run_id` (Optional[str]): Filter messages by the run ID that generated them.
        - `query_object` (PaginationQueryParams): Pagination parameters (limit, after, before).
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id,
                                   params = "thread_id")

    try:
        messages = await PostgresMessageStore.get_thread_messages(pool = postgres_pool,
                                                                  thread_id = thread_id,
                                                                  limit = query_object.limit,
                                                                  after = query_object.after,
                                                                  before = query_object.before,
                                                                  run_id = run_id)
        # No messages
        if len(messages) == 0: return MessageListObject(data = [])
        # Have messages
        messages_object = _update_messages_response(messages)
        # Return messages
        return MessageListObject(data = messages_object,
                                 first_id = messages_object[0].id,
                                 last_id = messages_object[-1].id)

    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(e)
        raise PostgresConnectionException()


@message_router.get("/{thread_id}/messages/{message_id}", response_model = MessageObject)
async def retrieve_message(thread_id: str,
                           message_id: str,
                           api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a message by its ID.

    Reference: [OpenAI Retrieve Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/retrieve)

    ### Args
        - `thread_id` (str): The ID of the thread that contains the message.
        - `message_id` (str): The ID of the message to retrieve.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of message id
    if not message_id.startswith("msg"):
        raise InvalidIdFormatException(input = message_id, params = "message_id")
    try:
        # Get exact message
        result = await PostgresMessageStore.get_message_by_id(pool=postgres_pool,
                                                              message_id=message_id,
                                                              thread_id=thread_id)
        return MessageObject(**result)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(e)
        raise PostgresConnectionException()

@message_router.delete("/{thread_id}/messages/{message_id}", response_model = DeletedMessageResponse)
async def delete_message(thread_id: str,
                         message_id: str,
                         api_key: str = Depends(verify_api_key)):
    """
    ## Delete a message by its ID.

    Reference: [OpenAI Delete Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/delete)

    ### Args
        - `thread_id` (str): The ID of the thread that contains the message.
        - `message_id` (str): The ID of the message to delete.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of message id
    if not message_id.startswith("msg"):
        raise InvalidIdFormatException(input = message_id, params = "message_id")

    try:
        await PostgresMessageStore.delete_message(pool = postgres_pool,
                                                  thread_id = thread_id,
                                                  message_id = message_id)
        return DeletedMessageResponse(id = message_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(e)
        raise PostgresConnectionException()
