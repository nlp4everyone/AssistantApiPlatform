# FastAPI Components
from fastapi import APIRouter, Path, Depends
# Schema
from app.schemas.common import PaginationQueryParams
from app.schemas.runs import RunObject, RunListObject
from app.schemas.runs.requests import CreateRunRequest
# Exceptions
from app.exceptions import InvalidIdFormatException
from app.exceptions.postgres import PostgresConnectionException
# DB
from app.db.postgres import PostgresThreadStore, PostgresRunStore
from app.startup import get_postgres_pool, get_model
# Utils
from app.utils.id_generation import generate_assistant_object
# Run dispatch
from app.services.runs import resolve_run_params, dispatch_run
# Typing
from typing import Optional
# Other
import asyncpg, socket, json
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger

# Router
run_router = APIRouter()


def _normalize_usage(usage) -> Optional[dict]:
    """Coerce a raw `usage` DB value (JSON string, dict, or None) into a valid usage dict or None."""
    if isinstance(usage, str):
        try:
            usage = json.loads(usage)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(usage, dict):
        return None
    if (usage.get("prompt_tokens") is not None and
        usage.get("completion_tokens") is not None and
        usage.get("total_tokens") is not None):
        return usage
    return None

@run_router.post("/{thread_id}/runs",
                 summary = "[Run] Create a run")
async def create_run(thread_id: str = Path(..., description="The ID of the thread"),
                     request: CreateRunRequest = None,
                     api_key: str = Depends(verify_api_key)):
    """
    ## Create a run for a thread.

    Reference: [OpenAI Create Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/create)

    ### Args
        - `thread_id` (str): The ID of the thread to create a run for.
        - `request` (CreateRunRequest): The run creation request containing parameters like assistant_id, model, instructions, etc.
    """
    # Postgres Service
    postgres_pool = get_postgres_pool()
    llm = get_model()

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

    try:
        # Check thread
        await PostgresThreadStore.is_thread_exists(pool = postgres_pool,
                                                    thread_id = thread_id)

        # Resolve instructions/temperature/top_p, falling back to the assistant's own config
        instructions, temperature, top_p = await resolve_run_params(
            postgres_pool, request.assistant_id, request.instructions, request.temperature, request.top_p)

        # Enqueue background generation or return a streaming response
        return await dispatch_run(postgres_pool = postgres_pool,
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
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[RUN_ROUTER] Failed to create run for thread {thread_id}: {e}")
        raise PostgresConnectionException()

@run_router.get("/{thread_id}/runs",
                summary = "[Run] List thread runs",
                response_model = RunListObject)
async def list_runs(thread_id :str,
                    query_object :PaginationQueryParams = Depends(),
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

    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")

    try:
        # Get runs objects
        run_objects = await PostgresRunStore.get_runs(pool = postgres_pool,
                                                      thread_id = thread_id,
                                                      limit = query_object.limit,
                                                      after = query_object.after,
                                                      before = query_object.before,
                                                      order = query_object.order)
        # No objects
        if len(run_objects) == 0: return RunListObject(data = [])
        # Update usage first
        for obj in run_objects:
            obj["usage"] = _normalize_usage(obj.get("usage"))

        # Convert to BaseModel objects
        run_objects = [RunObject.model_validate(obj) for obj in run_objects]
        # Return list of run object
        return RunListObject(data = run_objects,
                             first_id = run_objects[0].id,
                             last_id = run_objects[-1].id)

    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[RUN_ROUTER] Failed to list runs for thread {thread_id}: {e}")
        raise PostgresConnectionException()

@run_router.get("/{thread_id}/runs/{run_id}",
                summary = "[Run] Retrieve a run",
                response_model = RunObject)
async def retrieve_run(thread_id: str,
                       run_id: str,
                       api_key: str = Depends(verify_api_key)):
    """
    ## Retrieve a run by its ID.

    Reference: [OpenAI Retrieve Run API](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs/methods/retrieve)

    ### Args
        - `thread_id` (str): The ID of the thread that the run belongs to.
        - `run_id` (str): The ID of the run to retrieve.
    """

    # Postgres Service
    postgres_pool = get_postgres_pool()
    # Check string format of thread id
    if not thread_id.startswith("thread"):
        raise InvalidIdFormatException(input = thread_id, params = "thread_id")
    # Check string format of thread id
    if not run_id.startswith("run"):
        raise InvalidIdFormatException(input = run_id, params = "run_id")

    try:
        # Get response
        run_object = await PostgresRunStore.get_run(pool = postgres_pool,
                                                    thread_id = thread_id,
                                                    run_id = run_id)

        # Update usage first
        run_object["usage"] = _normalize_usage(run_object.get("usage"))

        # Return run object
        return RunObject.model_validate(run_object)

    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[RUN_ROUTER] Failed to retrieve run {run_id} from thread {thread_id}: {e}")
        raise PostgresConnectionException()
