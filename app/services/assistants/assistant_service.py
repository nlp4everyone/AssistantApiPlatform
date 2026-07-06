# Typing
from typing import Optional
# Schema
from app.schemas.assistants import (AssistantObject,
                                    CreateAssistantRequest,
                                    AssistantListObject,
                                    DeletedAssistantResponse)
# Postgres DB
from app.db.postgres import PostgresAssistantStore
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging.formatters import update_assistant_response
# Other components
import asyncpg, time


class AssistantService:
    @staticmethod
    async def create_assistant(postgres_pool: asyncpg.Pool,
                               request: CreateAssistantRequest) -> AssistantObject:
        """Create an assistant and return the created assistant object."""
        assistant_id = generate_assistant_object("assistant")

        await PostgresAssistantStore.create_assistant(pool = postgres_pool,
                                              assistant_id = assistant_id,
                                              request = request)

        return AssistantObject(id = assistant_id,
                               name = request.name,
                               created_at = int(time.time()),
                               description = request.description,
                               instructions = request.instructions,
                               model = request.model,
                               tools = request.tools,
                               top_p = request.top_p,
                               temperature = request.temperature)

    @staticmethod
    async def list_assistants(postgres_pool: asyncpg.Pool,
                              order: str,
                              limit: int,
                              after: Optional[str],
                              before: Optional[str]) -> AssistantListObject:
        """List assistants with keyset pagination."""
        selected_assistant_objects = await PostgresAssistantStore.list_assistants(pool = postgres_pool,
                                                                          order = order,
                                                                          limit = limit,
                                                                          after = after,
                                                                          before = before)
        total_number_assistant = await PostgresAssistantStore.count_assistants(pool = postgres_pool)

        if len(selected_assistant_objects) == 0:
            return AssistantListObject(data = [])

        assistant_objects = update_assistant_response([dict(assistant_object) for assistant_object in selected_assistant_objects])
        return AssistantListObject(data = assistant_objects,
                                   first_id = assistant_objects[0].id,
                                   last_id = assistant_objects[-1].id,
                                   has_more = len(selected_assistant_objects) < total_number_assistant)

    @staticmethod
    async def retrieve_assistant(postgres_pool: asyncpg.Pool,
                                 assistant_id: str) -> AssistantObject:
        """Retrieve a single assistant by ID."""
        res = await PostgresAssistantStore.get_assistant(pool = postgres_pool,
                                                 assistant_id = assistant_id)
        return update_assistant_response([res])[0]

    @staticmethod
    async def delete_assistant(postgres_pool: asyncpg.Pool,
                               assistant_id: str) -> DeletedAssistantResponse:
        """Delete an assistant by ID and return the deletion confirmation."""
        await PostgresAssistantStore.delete_assistant(pool = postgres_pool,
                                              assistant_id = assistant_id)
        return DeletedAssistantResponse(id = assistant_id)
