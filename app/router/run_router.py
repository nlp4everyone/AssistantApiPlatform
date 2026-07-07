# FastAPI Components
from fastapi import APIRouter, Path, Depends
# Schema
from app.schemas.common import PaginationQueryParams
from app.schemas.runs import RunObject, RunListObject
from app.schemas.runs.requests import CreateRunRequest
# Exceptions
from app.exceptions import InvalidIdFormatException
# DB
from app.db.postgres import PostgresThreadStore
from app.startup import get_postgres_pool, get_model
# Utils
from app.utils.id_generation import generate_assistant_object
# Run services
from app.services.runs import RunDispatchService, RunService
# Other
import asyncpg
# Security
from app.security.auth import verify_api_key

# Router
run_router = APIRouter()

@run_router.post("/{thread_id}/runs",
                 summary = "[Run] Create a run")
async def create_run(thread_id: str = Path(..., description="The ID of the thread"),
                     request: CreateRunRequest = None,
                     postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                     llm = Depends(get_model),
                     api_key: str = Depends(verify_api_key)):
    """
    ## Create a run for a thread.

    Reference: [OpenAI Create Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/create)

    ### Args
        - `thread_id` (str): The ID of the thread to create a run for.
        - `request` (CreateRunRequest): The run creation request containing parameters like assistant_id, model, instructions, etc.
    """
    # Check assistant_id
    if not request.assistant_id.startswith("asst"):
        raise InvalidIdFormatException(input = request.assistant_id,
                                       params = "assistant_id",
                                       prefix = "asst")
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")

    # Default value
    run_id = generate_assistant_object(object = "run")
    step_id = generate_assistant_object(object = "step")
    message_id = generate_assistant_object(object = "message")

    # Check thread
    await PostgresThreadStore.is_thread_exists(pool = postgres_pool,
                                                thread_id = thread_id)

    # Resolve instructions/temperature/top_p, falling back to the assistant's own config
    instructions, temperature, top_p = await RunDispatchService.resolve_run_params(
        postgres_pool, request.assistant_id, request.instructions, request.temperature, request.top_p)

    # Enqueue background generation or return a streaming response
    return await RunDispatchService.dispatch_run(postgres_pool = postgres_pool,
                                                  llm = llm,
                                                  request = request,
                                                  thread_id = thread_id,
                                                  run_id = run_id,
                                                  step_id = step_id,
                                                  message_id = message_id,
                                                  instructions = instructions,
                                                  temperature = temperature,
                                                  top_p = top_p,
                                                  endpoint_path = "/v1/threads/{thread_id}/runs")

@run_router.get("/{thread_id}/runs",
                summary = "[Run] List thread runs",
                response_model = RunListObject)
async def list_runs(thread_id :str,
                    query_object :PaginationQueryParams = Depends(),
                    postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                    api_key: str = Depends(verify_api_key)):
    """
    ## List runs for a thread.

    Reference: [OpenAI List Runs API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/list)

    ### Args
        - `thread_id` (str): The ID of the thread to list runs for.
        - `limit` (int): A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.
        - `order` (str): Sort order by the `created_at` timestamp of the objects. `asc` for ascending order and `desc` for descending order.
        - `after` (str, optional): A cursor for use in pagination. `after` is an object ID that defines your place in the list.
        - `before` (str, optional): A cursor for use in pagination. `before` is an object ID that defines your place in the list.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")

    return await RunService.list_runs(postgres_pool = postgres_pool,
                                      thread_id = thread_id,
                                      limit = query_object.limit,
                                      after = query_object.after,
                                      before = query_object.before,
                                      order = query_object.order)

@run_router.get("/{thread_id}/runs/{run_id}",
                summary = "[Run] Retrieve a run",
                response_model = RunObject)
async def retrieve_run(thread_id: str,
                       run_id: str,
                       postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                       api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a run by its ID.

    Reference: [OpenAI Retrieve Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/retrieve)

    ### Args
        - `thread_id` (str): The ID of the thread that the run belongs to.
        - `run_id` (str): The ID of the run to retrieve.
    """
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of thread id
    if not run_id.startswith("run"):
        raise InvalidIdFormatException(input = run_id, params = "run_id")

    return await RunService.retrieve_run(postgres_pool = postgres_pool,
                                         thread_id = thread_id,
                                         run_id = run_id)
