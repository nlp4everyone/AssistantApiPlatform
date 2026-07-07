# FastAPI components
from fastapi import APIRouter, Depends
# Schema
from app.schemas.common import (ChatMessage,
                                PaginationQueryParams)
from app.schemas.messages import (MessageObject,
                                  MessageListObject,
                                  DeletedMessageResponse)
# Exceptions
from app.exceptions import InvalidIdFormatException
# Get Postgres pool
from app.startup import get_postgres_pool
# Message service
from app.services.messages import MessageService
import asyncpg
# Security
from app.security.auth import verify_api_key
# Typing
from typing import Optional

# Define message router
message_router = APIRouter()

@message_router.post("/{thread_id}/messages",
                     summary = "[Message] Create a message",
                     response_model = MessageObject)
async def create_message(thread_id: str,
                         message: ChatMessage,
                         postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                         api_key: str = Depends(verify_api_key)):
    """
    ## Create a message in a thread.

    Reference: [OpenAI Create Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/create)

    ### Args
        - `thread_id` (str): The ID of the thread to create the message in.
        - `role` (str): The role of the entity that is creating the message ("user", "assistant", or "system"). Default: "user"
        - `content` (str): The message content, either as a string or list of content blocks
        - `attachments` (List[Attachment]): A list of files attached to the message, and the tools they should be added to.
        - `metadata` (Dict[str, str]): Set of 16 key-value pairs that can be attached to an object.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id,
                                       params ="thread_id")
    return await MessageService.create_message(postgres_pool = postgres_pool,
                                               thread_id = thread_id,
                                               message = message)

@message_router.get("/{thread_id}/messages",
                    summary = "[Message] List thread messages",
                    response_model = MessageListObject)
async def list_messages(thread_id :str,
                        run_id: Optional[str] = None,
                        query_object :PaginationQueryParams = Depends(),
                        postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                        api_key: str = Depends(verify_api_key)):
    """
    ## List messages in a thread.

    Reference: [OpenAI List Messages API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/list)

    ### Args
        - `thread_id` (str): The ID of the thread to list messages from.
        - `run_id` (Optional[str]): Filter messages by the run ID that generated them.
        - `limit` (int): A limit on the number of objects to be returned (max 100). Default: 20
        - `order` (Literal["asc", "desc"]): Sort order by the created_at timestamp of the objects. asc for ascending order and desc for descending order. Default: "desc"
        - `after` (Optional[str]): A cursor for use in pagination. `after` is an object ID that defines your place in the list. Default: None
        - `before` (Optional[str]): A cursor for use in pagination. `before` is an object ID that defines your place in the list. Default: None
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")

    return await MessageService.list_messages(postgres_pool = postgres_pool,
                                              thread_id = thread_id,
                                              limit = query_object.limit,
                                              after = query_object.after,
                                              before = query_object.before,
                                              order = query_object.order,
                                              run_id = run_id)


@message_router.get("/{thread_id}/messages/{message_id}",
                    summary = "[Message] Retrieve a message",
                    response_model = MessageObject)
async def retrieve_message(thread_id: str,
                           message_id: str,
                           postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                           api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a message by its ID.

    Reference: [OpenAI Retrieve Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/retrieve)

    ### Args
        - `thread_id` (str): The ID of the thread that contains the message.
        - `message_id` (str): The ID of the message to retrieve.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of message id
    if not message_id.startswith("msg"):
        raise InvalidIdFormatException(input = message_id, params = "message_id")
    # Get exact message
    return await MessageService.retrieve_message(postgres_pool = postgres_pool,
                                                 thread_id = thread_id,
                                                 message_id = message_id)

@message_router.delete("/{thread_id}/messages/{message_id}",
                       summary = "[Message] Delete a message",
                       response_model = DeletedMessageResponse)
async def delete_message(thread_id: str,
                         message_id: str,
                         postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                         api_key: str = Depends(verify_api_key)):
    """
    ## Delete a message by its ID.

    Reference: [OpenAI Delete Message API](https://developers.openai.com/api/reference/python/resources/beta/subresources/threads/subresources/messages/methods/delete)

    ### Args
        - `thread_id` (str): The ID of the thread that contains the message.
        - `message_id` (str): The ID of the message to delete.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of message id
    if not message_id.startswith("msg"):
        raise InvalidIdFormatException(input = message_id, params = "message_id")

    return await MessageService.delete_message(postgres_pool = postgres_pool,
                                               thread_id = thread_id,
                                               message_id = message_id)
