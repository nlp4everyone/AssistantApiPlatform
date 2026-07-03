# Typing
from typing import List, Dict
# Object Schema
from app.schemas.common import ChatMessage
from app.schemas.runs import RunStatus, TokenUsage
# Postgres DB
from app.db.postgres import PostgresRunStore
from app.db.postgres import PostgresMessageStore
# Utils
from app.utils.token_counter import approximate_count_tokens
from app.utils.messaging import _convert_to_message_objects, _to_openai_messages
# Common services
from app.services.common import prepare_generation_context
# Config
from app.core.config import LLM_MODEL_NAME, LLM_EXTRA_BODY
# OpenAI client
from openai import AsyncOpenAI
# Logger
from loggers import SystemLogger
# External dependencies
import asyncpg, mlflow, time
from mlflow.entities import SpanType

# Enable logging
mlflow.config.enable_async_logging()

async def generate_response_from_messages(postgres_pool: asyncpg.Pool,
                                          llm: AsyncOpenAI,
                                          messages: list,
                                          instructions: str,
                                          max_completion_tokens: int,
                                          thread_id: str,
                                          run_id: str,
                                          assistant_id: str,
                                          message_id: str = None,
                                          temperature: float = None,
                                          top_p: float = None,
                                          endpoint_path: str = None) -> List[Dict[str,str]]:
    """
    Generate AI response from prepared messages using the specified LLM.
    
    Args:
        postgres_pool: Database connection pool
        llm: Language model instance for generation
        messages: List of chat messages to generate response from
        instructions: System instructions to prepend to messages
        max_completion_tokens: Maximum tokens for the completion
        thread_id: Thread identifier for message storage
        run_id: Run identifier for status tracking
        assistant_id: Assistant identifier for message storage
        message_id: Optional message identifier for response
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        endpoint_path: Optional endpoint path for span naming
    
    Returns:
        list: Response messages
    """
    # Build the request payload for generation
    request_kwargs = {"model": LLM_MODEL_NAME, "max_tokens": max_completion_tokens, "extra_body": LLM_EXTRA_BODY}
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    if top_p is not None:
        request_kwargs["top_p"] = top_p

    # Convert messages to OpenAI chat format
    chat_messages = _to_openai_messages(messages)
    # Add system instructions at the beginning if provided
    if instructions:
        chat_messages.insert(0, {"role": "system", "content": instructions})

    # Update run status to indicate generation is in progress
    await PostgresRunStore.update_run_status(
        pool=postgres_pool,
        run_id=run_id,
        status=RunStatus.RUNNING
    )

    # Tracking with span
    with mlflow.start_span(name = endpoint_path, span_type = SpanType.CHAT_MODEL) as span:
        # Set input
        span.set_inputs(chat_messages)

        # Set tags on span
        mlflow.update_current_trace(tags = {"thread_id": thread_id,
                                            "run_id": run_id,
                                            "message_id": message_id,
                                            "assistant_id": assistant_id})

        # Generate response using the language model
        generation_start_time = time.perf_counter()
        response = await llm.chat.completions.create(messages=chat_messages, **request_kwargs)
        generation_time = time.perf_counter() - generation_start_time
        response_content = response.choices[0].message.content

        # Convert response to ChatMessage format
        response_message = ChatMessage(role="assistant", content=response_content).model_dump()

        # Count tokens
        prompt_tokens = approximate_count_tokens(messages)
        completion_tokens = approximate_count_tokens(response_message)

        # Add attribute ( Config, Usage, Performance)
        throughput = completion_tokens / generation_time if generation_time > 0 else 0
        span.set_attributes({"model_config": {"model_name": LLM_MODEL_NAME,
                                              "temperature": temperature,
                                              "top_p": top_p,
                                              "max_tokens": max_completion_tokens,
                                              "stream": False},
                             "model_usage": {"prompt_tokens": prompt_tokens,
                                             "completion_tokens": completion_tokens,
                                             "total_tokens": prompt_tokens + completion_tokens},
                             "model_performance": {"latency": round(generation_time,2),
                                                   "throughput_tokens_per_second": round(throughput,1)}})

        # Set output
        span.set_outputs([{"role":"assistant","content": response_content}])

    # Store the generated response in the database
    await PostgresMessageStore.insert_messages(
        pool=postgres_pool,
        thread_id=thread_id,
        data={
            "data": _convert_to_message_objects(messages=[response_message], thread_id=thread_id, message_id=message_id),
            "assistant_id": assistant_id,
            "run_id": run_id
        }
    )

    # Update run with token usage statistics
    await PostgresRunStore.update_run_usage(
        pool=postgres_pool,
        run_id=run_id,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        ).model_dump()
    )

    # Mark run as completed successfully
    await PostgresRunStore.update_run_status(
        pool=postgres_pool,
        run_id=run_id,
        status=RunStatus.COMPLETED
    )
    # Update state
    mlflow.flush_async_logging()

    return [response_message]

async def handle_generation_response(postgres_pool: asyncpg.Pool,
                                     llm: AsyncOpenAI,
                                     request: dict,
                                     thread_id: str,
                                     run_id: str,
                                     assistant_id: str,
                                     instructions: str,
                                     message_id: str = None,
                                     temperature: float = None,
                                     top_p: float = None,
                                     endpoint_path: str = None):
    """
    Main orchestrator for the AI response generation process.
    
    This function coordinates the complete generation workflow:
    1. Prepares messages and context using the common service
    2. Generates AI response from the prepared messages
    3. Handles error cases and updates run status accordingly
    
    Args:
        postgres_pool: Database connection pool
        llm: Language model instance for generation
        request: Generation request parameters
        thread_id: Thread identifier for message storage
        run_id: Run identifier for status tracking
        assistant_id: Assistant identifier for message storage
        instructions: System instructions for the AI
        message_id: Optional message identifier for response
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        endpoint_path: Optional endpoint path for span naming
    
    Returns:
        list: Generated response messages
    
    Raises:
        Exception: Propagates any errors during generation after updating run status
    """
    try:
        # Phase 1: Prepare generation context including message history and instructions
        context_data = await prepare_generation_context(
            postgres_pool=postgres_pool,
            request=request,
            thread_id=thread_id,
            run_id=run_id,
            assistant_id=assistant_id,
            instructions=instructions
        )
        
        # Extract prepared data from context
        validated_request = context_data["validated_request"]
        messages = context_data["messages"]
        final_instructions = context_data["final_instructions"]
        max_completion_tokens = validated_request.max_completion_tokens
        
        # Use passed temperature and top_p, falling back to request values if not provided
        final_temperature = temperature if temperature is not None else validated_request.temperature
        final_top_p = top_p if top_p is not None else validated_request.top_p

        # Phase 2: Generate AI response from the prepared messages
        return await generate_response_from_messages(
            postgres_pool=postgres_pool,
            llm=llm,
            messages=messages,
            instructions=final_instructions,
            max_completion_tokens=max_completion_tokens,
            thread_id=thread_id,
            run_id=run_id,
            assistant_id=assistant_id,
            message_id=message_id,
            temperature=final_temperature,
            top_p=final_top_p,
            endpoint_path=endpoint_path
        )

    except Exception as e:
        # Log the error for debugging purposes
        SystemLogger.error(f"[GENERATION_WORKER] Background generation failed for run {run_id}: {e}")
        # Update run status to failed to indicate the error
        await PostgresRunStore.update_run_status(
            pool=postgres_pool,
            run_id=run_id,
            status=RunStatus.FAILED)




