# FastAPI Components
from fastapi import APIRouter, Depends
# Schema
from app.schemas.common import PaginationQueryParams
from app.schemas.runs import RunObject, RunListObject
from app.schemas.runs.requests import CreateRunRequest
# ID validation
from app.utils.id_generation import validate_id_prefix, ThreadIdPath, RunIdPath
# DB
from app.db.postgres import PostgresThreadStore
from app.startup import get_postgres_pool, get_model
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
async def create_run(thread_id: ThreadIdPath,
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
    validate_id_prefix(request.assistant_id, "assistant_id", "assistant")

    # Check thread
    await PostgresThreadStore.is_thread_exists(pool = postgres_pool,
                                                thread_id = thread_id)

    # Generate IDs, resolve run params, and enqueue background generation or stream
    return await RunDispatchService.create_and_dispatch_run(postgres_pool = postgres_pool,
                                                             llm = llm,
                                                             request = request,
                                                             thread_id = thread_id,
                                                             endpoint_path = "/v1/threads/{thread_id}/runs")

@run_router.get("/{thread_id}/runs",
                summary = "[Run] List thread runs",
                response_model = RunListObject)
async def list_runs(thread_id: ThreadIdPath,
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
    return await RunService.list_runs(postgres_pool = postgres_pool,
                                      thread_id = thread_id,
                                      limit = query_object.limit,
                                      after = query_object.after,
                                      before = query_object.before,
                                      order = query_object.order)

@run_router.get("/{thread_id}/runs/{run_id}",
                summary = "[Run] Retrieve a run",
                response_model = RunObject)
async def retrieve_run(thread_id: ThreadIdPath,
                       run_id: RunIdPath,
                       postgres_pool: asyncpg.Pool = Depends(get_postgres_pool),
                       api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a run by its ID.

    Reference: [OpenAI Retrieve Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/retrieve)

    ### Args
        - `thread_id` (str): The ID of the thread that the run belongs to.
        - `run_id` (str): The ID of the run to retrieve.
    """
    return await RunService.retrieve_run(postgres_pool = postgres_pool,
                                         thread_id = thread_id,
                                         run_id = run_id)
