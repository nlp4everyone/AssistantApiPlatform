# Typing
from typing import Optional
# Schema
from app.schemas.common import ChatMessage
from app.schemas.messages import MessageObject, MessageListObject, DeletedMessageResponse
# Postgres DB
from app.db.postgres import PostgresMessageStore
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging import update_messages_response, build_content_items
# Other components
import asyncpg, time


class MessageService:
    @staticmethod
    async def create_message(postgres_pool: asyncpg.Pool,
                             thread_id: str,
                             message: ChatMessage) -> MessageObject:
        """Create a message in a thread and return the persisted message object."""
        content = build_content_items(message.content)

        message_object = MessageObject(id = generate_assistant_object(object = "message"),
                                       created_at = int(time.time()),
                                       thread_id = thread_id,
                                       role = message.role,
                                       content = content,
                                       attachments = message.attachments or [],
                                       metadata = message.metadata or {}).model_dump()

        await PostgresMessageStore.insert_messages(pool = postgres_pool,
                                                   thread_id = thread_id,
                                                   data = {"data": [message_object]})
        return message_object

    @staticmethod
    async def list_messages(postgres_pool: asyncpg.Pool,
                            thread_id: str,
                            limit: int,
                            after: Optional[str],
                            before: Optional[str],
                            run_id: Optional[str] = None) -> MessageListObject:
        """List messages in a thread with keyset pagination, optionally filtered by run."""
        messages = await PostgresMessageStore.get_thread_messages(pool = postgres_pool,
                                                                  thread_id = thread_id,
                                                                  limit = limit,
                                                                  after = after,
                                                                  before = before,
                                                                  run_id = run_id)
        if len(messages) == 0:
            return MessageListObject(data = [])

        messages_object = update_messages_response(messages)
        return MessageListObject(data = messages_object,
                                 first_id = messages_object[0].id,
                                 last_id = messages_object[-1].id)

    @staticmethod
    async def retrieve_message(postgres_pool: asyncpg.Pool,
                               thread_id: str,
                               message_id: str) -> MessageObject:
        """Retrieve a single message by ID."""
        result = await PostgresMessageStore.get_message_by_id(pool = postgres_pool,
                                                              message_id = message_id,
                                                              thread_id = thread_id)
        return MessageObject(**result)

    @staticmethod
    async def delete_message(postgres_pool: asyncpg.Pool,
                             thread_id: str,
                             message_id: str) -> DeletedMessageResponse:
        """Delete a message by ID and return the deletion confirmation."""
        await PostgresMessageStore.delete_message(pool = postgres_pool,
                                                  thread_id = thread_id,
                                                  message_id = message_id)
        return DeletedMessageResponse(id = message_id)
