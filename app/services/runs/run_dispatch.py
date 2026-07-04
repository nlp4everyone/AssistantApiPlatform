# Typing
from typing import Optional, Tuple
# FastAPI components
from fastapi.responses import StreamingResponse
# Schema
from app.schemas.runs import RunObject
from app.schemas.runs.requests import CreateRunRequest, CreateThreadRunRequest
# Postgres DB
from app.db.postgres import PostgresAssistantStore
# Utils
from app.utils.messaging import update_assistant_response
# Streaming
from app.services.streaming import handle_streaming_response
# TaskIQ worker
from taskiq_worker import run_background_llm
# Config
from app.core.config.prompts import DEFAULT_ASSISTANT_PROMPT
# Other dependencies
from openai import AsyncOpenAI
import asyncpg, time


async def resolve_run_params(postgres_pool: asyncpg.Pool,
                             assistant_id: str,
                             request_instructions: Optional[str],
                             request_temperature: Optional[float],
                             request_top_p: Optional[float]) -> Tuple[str, Optional[float], Optional[float]]:
    """
    Resolve instructions/temperature/top_p for a run, falling back to the assistant's
    own configuration (and the default prompt) when the request does not set them.
    """
    assistant_info = await PostgresAssistantStore.get_assistant(pool=postgres_pool, assistant_id=assistant_id)
    assistant_info = update_assistant_response([assistant_info])[0]

    instructions = request_instructions if request_instructions else assistant_info.instructions or DEFAULT_ASSISTANT_PROMPT
    temperature = request_temperature if isinstance(request_temperature, float) else assistant_info.temperature
    top_p = request_top_p if isinstance(request_top_p, float) else assistant_info.top_p

    return instructions, temperature, top_p


async def dispatch_run(*,
                       postgres_pool: asyncpg.Pool,
                       llm: AsyncOpenAI,
                       request: "CreateRunRequest | CreateThreadRunRequest",
                       thread_id: str,
                       run_id: str,
                       step_id: str,
                       message_id: str,
                       instructions: str,
                       temperature: Optional[float],
                       top_p: Optional[float],
                       endpoint_path: str):
    """
    Start a run: enqueue a background generation job for non-streaming requests,
    or return a StreamingResponse of SSE events for streaming requests.
    """
    if not request.stream:
        await run_background_llm.kiq(thread_id,
                                     run_id,
                                     request,
                                     request.assistant_id,
                                     instructions,
                                     message_id,
                                     temperature,
                                     top_p,
                                     endpoint_path)
        return RunObject(id=run_id,
                         created_at=int(time.time()),
                         assistant_id=request.assistant_id,
                         thread_id=thread_id,
                         status="queued",
                         model=request.model,
                         completed_at=int(time.time()),
                         temperature=temperature,
                         top_p=top_p,
                         max_prompt_tokens=request.max_prompt_tokens,
                         max_completion_tokens=request.max_completion_tokens)

    return StreamingResponse(handle_streaming_response(llm=llm,
                                                        postgres_pool=postgres_pool,
                                                        request=request.model_dump(),
                                                        run_id=run_id,
                                                        thread_id=thread_id,
                                                        message_id=message_id,
                                                        step_id=step_id,
                                                        assistant_id=request.assistant_id,
                                                        instructions=instructions,
                                                        temperature=temperature,
                                                        top_p=top_p,
                                                        endpoint_path=endpoint_path),
                             media_type="text/event-stream")