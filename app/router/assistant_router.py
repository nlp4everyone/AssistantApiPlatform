# FastAPI components
from fastapi import APIRouter, Depends
# Schema
from app.schemas.assistants import (AssistantObject,
                                    CreateAssistantRequest,
                                    AssistantListObject)
from app.schemas.common import PaginationQueryParams
# Exceptions
from app.exceptions import InvalidIdFormatException
from app.exceptions.postgres import PostgresConnectionException
# Postgres
from app.startup import get_postgres_pool
# Assistant service
from app.services.assistants import AssistantService
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# Other components
import asyncpg, socket

assistant_router = APIRouter()

@assistant_router.post("/assistants",
                       summary = "[Assistant] Create an assistant",
                       response_model = AssistantObject)
async def create_assistant(request: CreateAssistantRequest,
                           postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                           api_key: str = Depends(verify_api_key)):
    """
    ## Create an assistant with a model and instructions.

    Reference: [OpenAI Create Assistant API](https://platform.openai.com/docs/api-reference/assistants/createAssistant)
    """
    try:
        return await AssistantService.create_assistant(postgres_pool = postgres_pool, request = request)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to create assistant: {e}")
        raise PostgresConnectionException()

@assistant_router.get("/assistants",
                      summary = "[Assistant] List all assistants",
                      response_model = AssistantListObject)
async def list_assistants(request :PaginationQueryParams = Depends(),
                          postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                          api_key: str = Depends(verify_api_key)):
    """
    ## Returns a list of assistants.

    Reference: [OpenAI List Assistants API](https://platform.openai.com/docs/api-reference/assistants/listAssistants)

    ### Args
        - `limit` (int, optional): A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.
        - `order` (str, optional): Sort order by the `created_at` timestamp of the objects. `asc` for ascending order and `desc` for descending order.
        - `after` (str, optional): A cursor for use in pagination. `after` is an object ID that defines your place in the list.
        - `before` (str, optional): A cursor for use in pagination. `before` is an object ID that defines your place in the list.
    """
    # Check input assistant format (Before)
    if request.before and not request.before.startswith("asst"):
        raise InvalidIdFormatException(input = request.before,
                                       params = "before",
                                       prefix = "asst")
    # Check input assistant format (After)
    if request.after and not request.after.startswith("asst"):
        raise InvalidIdFormatException(input = request.after,
                                       params = "after",
                                       prefix = "asst")

    try:
        return await AssistantService.list_assistants(postgres_pool = postgres_pool,
                                                       order = request.order,
                                                       limit = request.limit,
                                                       after = request.after,
                                                       before = request.before)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to list assistants: {e}")
        raise PostgresConnectionException()

@assistant_router.get("/assistants/{assistant_id}",
                      summary = "[Assistant] Retrieve an assistant",
                      response_model = AssistantObject)
async def retrieve_assistant(assistant_id: str,
                             postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                             api_key: str = Depends(verify_api_key)):
    """
    ## Retrieves an assistant.

    Reference: [OpenAI Get Assistant API](https://platform.openai.com/docs/api-reference/assistants/getAssistant)

    ### Args
        - `assistant_id` (str): The ID of the assistant to retrieve.
    """
    # Check assistant_id
    if not assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input = assistant_id,
                                       params = "assistant_id",
                                       prefix = "asst")
    try:
        return await AssistantService.retrieve_assistant(postgres_pool = postgres_pool, assistant_id = assistant_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to retrieve assistant {assistant_id}: {e}")
        raise PostgresConnectionException()

@assistant_router.delete("/assistants/{assistant_id}",
                         summary = "[Assistant] Delete an assistant")
async def delete_assistant(assistant_id: str,
                           postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                           api_key: str = Depends(verify_api_key)):
    """
    ## Delete an assistant.

    Reference: [OpenAI Delete Assistant API](https://platform.openai.com/docs/api-reference/assistants/deleteAssistant)

    ### Args
        - `assistant_id` (str): The ID of the assistant to delete.
    """
    # Check assistant_id
    if not assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input = assistant_id,
                                       params = "assistant_id",
                                       prefix = "asst")

    try:
        # Delete assistant
        return await AssistantService.delete_assistant(postgres_pool = postgres_pool, assistant_id = assistant_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to delete assistant {assistant_id}: {e}")
        raise PostgresConnectionException()