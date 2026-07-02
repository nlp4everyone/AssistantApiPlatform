# FastAPI components
from fastapi import APIRouter, Depends
# Schema
from app.schemas.assistants import (AssistantObject,
                                    CreateAssistantRequest,
                                    AssistantListObject,
                                    DeletedAssistantResponse)
from app.schemas.common import PaginationQueryParams
# Exceptions
from app.exceptions import InvalidIdFormatException
from app.exceptions.postgres import PostgresConnectionException
# Postgres
from app.db.postgres import PostgresAssistantStore
from app.startup import get_postgres_pool
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging.formatters import _update_assistant_response
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# Other components
import time, asyncpg, socket

assistant_router = APIRouter()

@assistant_router.post("/assistants",
                       summary = "[Assistant] Create an assistant",
                       response_model = AssistantObject)
async def create_assistant(request: CreateAssistantRequest,
                           api_key: str = Depends(verify_api_key)):
    """
    ## Create an assistant with a model and instructions.
    
    Reference: [OpenAI Create Assistant API](https://platform.openai.com/docs/api-reference/assistants/createAssistant)
    """
    # Pool
    postgres_pool = get_postgres_pool()
    # Define assistant id
    assistant_id = generate_assistant_object("assistant")

    try:
        # Insert new assistant to Postgres
        await PostgresAssistantStore.create_assistant(pool = postgres_pool,
                                              assistant_id = assistant_id,
                                              request = request)
        # ***Check if specify vector store ids existed ( In tool resource)***
        # ***Check only use for normal case ( Not RAG) and supported type in Assistant***

        # Return response
        return AssistantObject(id = assistant_id,
                               name = request.name,
                               created_at = int(time.time()),
                               description = request.description,
                               instructions = request.instructions,
                               model = request.model,
                               tools = request.tools,
                               top_p = request.top_p,
                               temperature = request.temperature)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to create assistant: {e}")
        raise PostgresConnectionException()

@assistant_router.get("/assistants",
                      summary = "[Assistant] List all assistants",
                      response_model = AssistantListObject)
async def list_assistants(request :PaginationQueryParams = Depends(),
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
    # Pool
    postgres_pool = get_postgres_pool()
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
        # Make the response
        selected_assistant_objects = await PostgresAssistantStore.list_assistants(pool = postgres_pool,
                                                                          order = request.order,
                                                                          limit = request.limit,
                                                                          after = request.after,
                                                                          before = request.before)
        # Total assistant counts
        total_number_assistant = await PostgresAssistantStore.count_assistants(pool = postgres_pool)

        # Empty object
        assistant_objects = []
        # Empty assistant, return
        if len(selected_assistant_objects) == 0: return AssistantListObject(data = assistant_objects)

        # Update value to correct format
        assistant_objects = _update_assistant_response([dict(assistant_object) for assistant_object in selected_assistant_objects])
        return AssistantListObject(data = assistant_objects,
                                   first_id = assistant_objects[0].id,
                                   last_id = assistant_objects[-1].id,
                                   has_more = True if len(selected_assistant_objects) < total_number_assistant else False)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to list assistants: {e}")
        raise PostgresConnectionException()

@assistant_router.get("/assistants/{assistant_id}",
                      summary = "[Assistant] Retrieve an assistant",
                      response_model = AssistantObject)
async def retrieve_assistant(assistant_id: str,
                             api_key: str = Depends(verify_api_key)):
    """
    ## Retrieves an assistant.
    
    Reference: [OpenAI Get Assistant API](https://platform.openai.com/docs/api-reference/assistants/getAssistant)
    
    ### Args
        - `assistant_id` (str): The ID of the assistant to retrieve.
    """
    # Pool
    postgres_pool = get_postgres_pool()
    # Check assistant_id
    if not assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input = assistant_id,
                                       params = "assistant_id",
                                       prefix = "asst")
    try:
        res = await PostgresAssistantStore.get_assistant(pool = postgres_pool,
                                                 assistant_id = assistant_id)
        # *** Need to add try/catch***
        assistant_objects = _update_assistant_response([res])
        # Return information
        return assistant_objects[0]
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to retrieve assistant {assistant_id}: {e}")
        raise PostgresConnectionException()

@assistant_router.delete("/assistants/{assistant_id}",
                         summary = "[Assistant] Delete an assistant")
async def delete_assistant(assistant_id: str,
                           api_key: str = Depends(verify_api_key)):
    """
    ## Delete an assistant.
    
    Reference: [OpenAI Delete Assistant API](https://platform.openai.com/docs/api-reference/assistants/deleteAssistant)
    
    ### Args
        - `assistant_id` (str): The ID of the assistant to delete.
    """
    # Pool
    postgres_pool = get_postgres_pool()
    # Check assistant_id
    if not assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input = assistant_id,
                                       params = "assistant_id",
                                       prefix = "asst")

    try:
        # Delete assistant
        await PostgresAssistantStore.delete_assistant(pool = postgres_pool,
                                              assistant_id = assistant_id)
        # Return
        return DeletedAssistantResponse(id = assistant_id)
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[ASSISTANT_ROUTER] Failed to delete assistant {assistant_id}: {e}")
        raise PostgresConnectionException()