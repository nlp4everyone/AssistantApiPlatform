# FastAPI Components
from fastapi import APIRouter, Path, Depends
from fastapi.responses import StreamingResponse
# Schema
from app.schemas.common import PaginationQueryParams
from app.schemas.runs import RunObject, RunListObject
from app.schemas.runs.requests import CreateRunRequest
# Exceptions
from app.exceptions import InvalidIdFormatException
from app.exceptions.postgres import PostgresConnectionException
from app.exceptions.threads import ThreadNotFoundException
# DB
from app.db.postgres import PostgresAssistantStore, PostgresThreadStore, PostgresRunStore
from app.startup import get_postgres_pool, get_model
# Utils
from app.utils.id_generation import generate_assistant_object
from app.utils.messaging import _update_assistant_response
# Streaming
from app.services.streaming import handle_streaming_response
# Other
import asyncpg, socket, time, json
# Security
from app.security.auth import verify_api_key
# Logger
from loggers import SystemLogger
# Runner
from taskiq_worker import run_background_llm
# Config
from app.core.config.prompts import DEFAULT_ASSISTANT_PROMPT

# Router
run_router = APIRouter()

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
        await PostgresThreadStore._is_thread_exists(pool = postgres_pool,
                                                    thread_id = thread_id)

        # Get assistant info
        assistant_info = await PostgresAssistantStore.get_assistant(pool = postgres_pool,
                                                            assistant_id = request.assistant_id)

        # Normalize ssistant info
        assistant_objects = _update_assistant_response([assistant_info])
        assistant_info = assistant_objects[0]
        instructions = request.instructions if request.instructions else assistant_info.instructions or DEFAULT_ASSISTANT_PROMPT
        # Get output params for both streaming and non-streaming modes
        temperature = request.temperature if isinstance(request.temperature, float) else assistant_info.temperature
        top_p = request.top_p if isinstance(request.top_p, float) else assistant_info.top_p

        if not request.stream:
            # Run in background
            await run_background_llm.kiq(thread_id,
                                         run_id,
                                         request,
                                         request.assistant_id,
                                         instructions,
                                         message_id,
                                         temperature,
                                         top_p,
                                         "/v1/threads/{thread_id}/runs")
            # Not in stream mode
            return RunObject(id = run_id,
                             created_at = int(time.time()),
                             assistant_id = request.assistant_id,
                             thread_id = thread_id,
                             status = "queued",
                             model = request.model,
                             completed_at = int(time.time()),
                             temperature = temperature,
                             top_p = top_p,
                             max_prompt_tokens = request.max_prompt_tokens,
                             max_completion_tokens = request.max_completion_tokens)

        # Streaming
        return StreamingResponse(handle_streaming_response(llm = llm,
                                                           postgres_pool = postgres_pool,
                                                           request = request.model_dump(),
                                                           run_id = run_id,
                                                           thread_id = thread_id,
                                                           message_id = message_id,
                                                           step_id = step_id,
                                                           assistant_id = request.assistant_id,
                                                           instructions = instructions,
                                                           temperature = temperature,
                                                           top_p = top_p,
                                                           endpoint_path = "/v1/threads/{thread_id}/runs"),
                                 media_type = "text/event-stream")
    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[RUN_ROUTER] Failed to create run for thread {thread_id}: {e}")
        raise PostgresConnectionException()
    except ThreadNotFoundException as e:
        SystemLogger.error(f"[RUN_ROUTER] Thread not found for run creation: {e}")
        raise ThreadNotFoundException(thread_id = thread_id)

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
            if isinstance(obj.get("usage"), str):
                try:
                    usage_data = json.loads(obj["usage"])
                    # Check if usage data has all required fields
                    if (isinstance(usage_data, dict) and 
                        usage_data.get("prompt_tokens") is not None and
                        usage_data.get("completion_tokens") is not None and
                        usage_data.get("total_tokens") is not None):
                        obj["usage"] = usage_data
                    else:
                        obj["usage"] = None
                except (json.JSONDecodeError, TypeError):
                    obj["usage"] = None
            elif isinstance(obj.get("usage"), dict):
                # Check if usage dict has all required fields
                if (obj["usage"].get("prompt_tokens") is not None and
                    obj["usage"].get("completion_tokens") is not None and
                    obj["usage"].get("total_tokens") is not None):
                    pass  # Keep the usage as is
                else:
                    obj["usage"] = None

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
        if isinstance(run_object.get("usage"), str):
            try:
                usage_data = json.loads(run_object["usage"])
                # Check if usage data has all required fields
                if (isinstance(usage_data, dict) and 
                    usage_data.get("prompt_tokens") is not None and
                    usage_data.get("completion_tokens") is not None and
                    usage_data.get("total_tokens") is not None):
                    run_object["usage"] = usage_data
                else:
                    run_object["usage"] = None
            except (json.JSONDecodeError, TypeError):
                run_object["usage"] = None
        elif isinstance(run_object.get("usage"), dict):
            # Check if usage dict has all required fields
            if (run_object["usage"].get("prompt_tokens") is not None and
                run_object["usage"].get("completion_tokens") is not None and
                run_object["usage"].get("total_tokens") is not None):
                pass  # Keep the usage as is
            else:
                run_object["usage"] = None

        # Return run object
        return RunObject.model_validate(run_object)

    except (asyncpg.PostgresError, socket.gaierror) as e:
        # Postgres connection error
        SystemLogger.error(f"[RUN_ROUTER] Failed to retrieve run {run_id} from thread {thread_id}: {e}")
        raise PostgresConnectionException()
