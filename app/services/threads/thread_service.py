# Typing
from typing import List, Optional
# Schema
from app.schemas.threads import ThreadObject, CreateThreadRequest, DeletedThreadResponse
from app.schemas.messages import MessageObject
from app.schemas.common import ChatMessage
# Postgres DB
from app.db.postgres import PostgresThreadStore, PostgresMessageStore
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging import build_content_items
# Other components
import asyncpg, time


class ThreadService:
    @staticmethod
    def _build_seed_messages(messages: Optional[List[ChatMessage]],
                             thread_id: str,
                             created_at: int) -> List[dict]:
        """Build message payload dicts for messages supplied at thread-creation time."""
        output_messages = []
        for input_message in messages or []:
            msg_id = generate_assistant_object(object = "message")
            content = build_content_items(input_message.content)
            output_messages.append(MessageObject(id = msg_id,
                                                 created_at = created_at,
                                                 thread_id = thread_id,
                                                 role = input_message.role,
                                                 content = content).model_dump())
        return output_messages

    @staticmethod
    async def create_thread(postgres_pool: asyncpg.Pool,
                            payload: CreateThreadRequest) -> ThreadObject:
        """
        Create a thread, persist any seed messages supplied in the payload, and
        return the created thread object.
        """
        thread_id = generate_assistant_object()
        created_at_seconds = int(time.time())

        seed_messages = ThreadService._build_seed_messages(payload.messages, thread_id, created_at_seconds)

        await PostgresThreadStore.insert_thread(pool = postgres_pool,
                                                thread_id = thread_id,
                                                metadata = payload.metadata,
                                                tool_resources = payload.tool_resources.model_dump())

        if seed_messages:
            await PostgresMessageStore.insert_messages(pool = postgres_pool,
                                                       data = {"data": seed_messages, "metadata": payload.metadata or {}},
                                                       thread_id = thread_id)

        return ThreadObject(id = thread_id,
                            created_at = created_at_seconds,
                            metadata = payload.metadata or {},
                            tool_resources = payload.tool_resources or {})

    @staticmethod
    async def retrieve_thread(postgres_pool: asyncpg.Pool,
                              thread_id: str) -> ThreadObject:
        """Fetch a thread by ID and map it to the public ThreadObject schema."""
        thread_info = await PostgresThreadStore.get_thread(pool = postgres_pool, thread_id = thread_id)
        return ThreadObject(id = thread_info.get("id"),
                            created_at = int(thread_info.get("created_at").timestamp()),
                            metadata = thread_info.get("metadata", {}),
                            tool_resources = thread_info.get("tool_resources", {}))

    @staticmethod
    async def delete_thread(postgres_pool: asyncpg.Pool,
                            thread_id: str) -> DeletedThreadResponse:
        """Delete a thread by ID and return the deletion confirmation."""
        await PostgresThreadStore.delete_thread(pool = postgres_pool, thread_id = thread_id)
        return DeletedThreadResponse(id = thread_id)