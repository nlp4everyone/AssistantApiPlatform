# FastAPI components
from fastapi import APIRouter, Depends
# Schema
from app.schemas.assistants import (AssistantObject,
                                    CreateAssistantRequest,
                                    AssistantListObject)
from app.schemas.common import PaginationQueryParams
# ID validation
from app.utils.id_generation import validate_id_prefix, AssistantIdPath
# Postgres
from app.startup import get_postgres_pool
# Assistant service
from app.services.assistants import AssistantService
# Security
from app.security.auth import verify_api_key
# Other components
import asyncpg

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
    return await AssistantService.create_assistant(postgres_pool = postgres_pool, request = request)

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
    # Check input assistant format (Before/After)
    if request.before:
        validate_id_prefix(request.before, "before", "assistant")
    if request.after:
        validate_id_prefix(request.after, "after", "assistant")

    return await AssistantService.list_assistants(postgres_pool = postgres_pool,
                                                   order = request.order,
                                                   limit = request.limit,
                                                   after = request.after,
                                                   before = request.before)

@assistant_router.get("/assistants/{assistant_id}",
                      summary = "[Assistant] Retrieve an assistant",
                      response_model = AssistantObject)
async def retrieve_assistant(assistant_id: AssistantIdPath,
                             postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                             api_key: str = Depends(verify_api_key)):
    """
    ## Retrieves an assistant.

    Reference: [OpenAI Get Assistant API](https://platform.openai.com/docs/api-reference/assistants/getAssistant)

    ### Args
        - `assistant_id` (str): The ID of the assistant to retrieve.
    """
    return await AssistantService.retrieve_assistant(postgres_pool = postgres_pool, assistant_id = assistant_id)

@assistant_router.delete("/assistants/{assistant_id}",
                         summary = "[Assistant] Delete an assistant")
async def delete_assistant(assistant_id: AssistantIdPath,
                           postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                           api_key: str = Depends(verify_api_key)):
    """
    ## Delete an assistant.

    Reference: [OpenAI Delete Assistant API](https://platform.openai.com/docs/api-reference/assistants/deleteAssistant)

    ### Args
        - `assistant_id` (str): The ID of the assistant to delete.
    """
    # Delete assistant
    return await AssistantService.delete_assistant(postgres_pool = postgres_pool, assistant_id = assistant_id)