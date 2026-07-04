# Typing
from typing import Optional, Tuple, List, Dict
# Object Schema
from app.schemas.runs import RunStatus, TokenUsage
# Postgres DB
from app.db.postgres import PostgresRunStore, PostgresMessageStore
# Utils
from app.utils.messaging import _convert_to_message_objects, _to_openai_messages
# Config
from app.core.config import LLM_MODEL_NAME, LLM_EXTRA_BODY
# Logger
from loggers import SystemLogger
# External dependencies
import asyncpg, mlflow


def _build_chat_request(messages: list,
                        instructions: Optional[str],
                        max_completion_tokens: int,
                        temperature: Optional[float],
                        top_p: Optional[float]) -> Tuple[List[Dict[str, str]], dict]:
    """
    Convert prepared messages into OpenAI chat format and build the request kwargs.

    Returns:
        tuple: (chat_messages, request_kwargs)
    """
    chat_messages = _to_openai_messages(messages)
    if instructions:
        chat_messages.insert(0, {"role": "system", "content": instructions})

    request_kwargs = {"model": LLM_MODEL_NAME, "max_tokens": max_completion_tokens, "extra_body": LLM_EXTRA_BODY}
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    if top_p is not None:
        request_kwargs["top_p"] = top_p

    return chat_messages, request_kwargs


def _tag_span(span,
              chat_messages: list,
              thread_id: str,
              run_id: str,
              message_id: str,
              assistant_id: str) -> None:
    """Set span inputs and trace tags for a generation call."""
    span.set_inputs(chat_messages)
    mlflow.update_current_trace(tags={"thread_id": thread_id,
                                      "run_id": run_id,
                                      "message_id": message_id,
                                      "assistant_id": assistant_id})


def _record_span_metrics(span,
                         *,
                         temperature: Optional[float],
                         top_p: Optional[float],
                         max_completion_tokens: int,
                         stream: bool,
                         prompt_tokens: int,
                         completion_tokens: int,
                         generation_time: float,
                         response_content: str) -> None:
    """Attach config/usage/performance attributes and the output to a generation span."""
    throughput = completion_tokens / generation_time if generation_time > 0 else 0
    span.set_attributes({"model_config": {"model_name": LLM_MODEL_NAME,
                                          "temperature": temperature,
                                          "top_p": top_p,
                                          "max_tokens": max_completion_tokens,
                                          "stream": stream},
                         "model_usage": {"prompt_tokens": prompt_tokens,
                                         "completion_tokens": completion_tokens,
                                         "total_tokens": prompt_tokens + completion_tokens},
                         "model_performance": {"latency": round(generation_time, 2),
                                               "throughput_tokens_per_second": round(throughput, 1)}})
    span.set_outputs([{"role": "assistant", "content": response_content}])


async def _persist_and_complete(postgres_pool: asyncpg.Pool,
                                *,
                                thread_id: str,
                                run_id: str,
                                assistant_id: str,
                                message_id: str,
                                response_message: dict,
                                prompt_tokens: int,
                                completion_tokens: int) -> None:
    """Persist the assistant reply, record token usage and mark the run completed."""
    await PostgresMessageStore.insert_messages(
        pool=postgres_pool,
        thread_id=thread_id,
        data={
            "data": _convert_to_message_objects(messages=[response_message], thread_id=thread_id, message_id=message_id),
            "assistant_id": assistant_id,
            "run_id": run_id
        }
    )

    await PostgresRunStore.update_run_usage(
        pool=postgres_pool,
        run_id=run_id,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        ).model_dump()
    )

    await PostgresRunStore.update_run_status(
        pool=postgres_pool,
        run_id=run_id,
        status=RunStatus.COMPLETED
    )

    mlflow.flush_async_logging()


async def _fail_run(postgres_pool: asyncpg.Pool, run_id: str, error: Exception, log_tag: str) -> None:
    """Log the failure and mark the run as failed."""
    SystemLogger.error(f"[{log_tag}] Run {run_id} failed: {error}")
    await PostgresRunStore.update_run_status(
        pool=postgres_pool,
        run_id=run_id,
        status=RunStatus.FAILED
    )