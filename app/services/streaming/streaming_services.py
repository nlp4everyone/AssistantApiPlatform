# Define schema
from app.schemas.common import ChatMessage
from app.schemas.runs import RunStatus
# Postgres DB
from app.db.postgres import PostgresRunStore
# Utils
from app.utils.events import EventManager
# OpenAI client
from openai import AsyncOpenAI
# Token counter
from app.utils.token_counter import approximate_count_tokens
# Typing
from typing import AsyncIterable
# Common
from app.services.common import (prepare_generation_context,
                                 build_chat_request,
                                 tag_span,
                                 record_span_metrics,
                                 persist_and_complete,
                                 fail_run)
# Import dependencies
import asyncpg, mlflow, time
from mlflow.entities import SpanType
# Enable logging
mlflow.config.enable_async_logging()

async def handle_streaming_response(postgres_pool: asyncpg.Pool,
                                    llm: AsyncOpenAI,
                                    request: dict,
                                    thread_id: str,
                                    run_id: str,
                                    step_id: str,
                                    message_id: str,
                                    assistant_id: str,
                                    instructions: str,
                                    temperature: float = None,
                                    top_p: float = None,
                                    endpoint_path :str = None) -> AsyncIterable:
    """
    Handle streaming response using the OpenAI-compatible client directly.

    Args:
        postgres_pool: Database connection pool
        llm: AsyncOpenAI instance for generation
        request: Request dictionary
        thread_id: Thread identifier
        run_id: Run identifier  
        step_id: Step identifier
        message_id: Message identifier
        assistant_id: Assistant identifier
        instructions: System instructions
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        endpoint_path: Optional endpoint path for span naming
    Yields:
        Server-sent events for streaming response
    """
    # Step 1: Prepare generation context
    context_data = await prepare_generation_context(
        postgres_pool=postgres_pool,
        request=request,
        thread_id=thread_id,
        run_id=run_id,
        assistant_id=assistant_id,
        instructions=instructions
    )
    
    # Step 2: Stream response from messages
    async for event in stream_response_from_messages(
        postgres_pool=postgres_pool,
        llm=llm,
        context_data=context_data,
        thread_id=thread_id,
        run_id=run_id,
        step_id=step_id,
        message_id=message_id,
        assistant_id=assistant_id,
        temperature=temperature,
        top_p=top_p,
        endpoint_path = endpoint_path):
        yield event


async def stream_response_from_messages(postgres_pool: asyncpg.Pool,
                                        llm: AsyncOpenAI,
                                        context_data: dict,
                                        thread_id: str,
                                        run_id: str,
                                        step_id: str,
                                        message_id: str,
                                        assistant_id: str,
                                        temperature: float = None,
                                        top_p: float = None,
                                        endpoint_path :str = None) -> AsyncIterable:
    """
    Stream response from prepared messages using the OpenAI-compatible client.

    Args:
        postgres_pool: Database connection pool
        llm: AsyncOpenAI instance for generation
        context_data: Context data from prepare_generation_context
        thread_id: Thread identifier
        run_id: Run identifier
        step_id: Step identifier
        message_id: Message identifier
        assistant_id: Assistant identifier
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        endpoint_path: Optional endpoint path for span naming
    Yields:
        Server-sent events for streaming response
    """
    validated_request = context_data["validated_request"]
    messages = context_data["messages"]
    final_instructions = context_data["final_instructions"]
    
    # Initialize event manager
    event_manager = EventManager(thread_id=thread_id,
                                 run_id=run_id,
                                 assistant_id=assistant_id,
                                 message_id=message_id,
                                 step_id=step_id,
                                 model=validated_request.model)
    
    # Emit all lifecycle events
    for event in event_manager.generate_all_lifecycle_events():
        yield event
    
    try:
        # Set LLM parameters - use passed parameters, falling back to request values
        final_temperature = temperature if temperature is not None else validated_request.temperature
        final_top_p = top_p if top_p is not None else validated_request.top_p
        max_completion_tokens = validated_request.max_completion_tokens

        chat_messages, request_kwargs = build_chat_request(messages, final_instructions, max_completion_tokens, final_temperature, final_top_p)

        # Update status to running
        await PostgresRunStore.update_run_status(
            pool=postgres_pool,
            run_id=run_id,
            status=RunStatus.IN_PROGRESS
        )

        # Tracking with span
        with mlflow.start_span(name = endpoint_path, span_type=SpanType.CHAT_MODEL) as span:
            tag_span(span, chat_messages, thread_id, run_id, message_id, assistant_id)

            # Stream response using the OpenAI-compatible client
            response_chunks = []
            generation_start_time = time.perf_counter()
            stream = await llm.chat.completions.create(messages=chat_messages, stream=True, **request_kwargs)
            async for chunk in stream:
                delta_content = chunk.choices[0].delta.content if chunk.choices else None
                if delta_content:
                    response_chunks.append(delta_content)

                    # Emit delta event using event manager
                    yield event_manager.get_delta_event(delta_content)
            generation_time = time.perf_counter() - generation_start_time
            # Combine all chunks
            final_response = "".join(response_chunks)

            # Define response
            response_message = ChatMessage(role="assistant", content=final_response).model_dump()
            # Count tokens
            prompt_tokens = approximate_count_tokens(messages)
            completion_tokens = approximate_count_tokens(response_message)

            record_span_metrics(span,
                                 temperature=final_temperature,
                                 top_p=final_top_p,
                                 max_completion_tokens=max_completion_tokens,
                                 stream=True,
                                 prompt_tokens=prompt_tokens,
                                 completion_tokens=completion_tokens,
                                 generation_time=generation_time,
                                 response_content=final_response)

        await persist_and_complete(postgres_pool,
                                    thread_id=thread_id,
                                    run_id=run_id,
                                    assistant_id=assistant_id,
                                    message_id=message_id,
                                    response_message=response_message,
                                    prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens)

        # Emit message completed event using event manager
        yield event_manager.get_message_completed_event(final_response)

        # Emit step completed event using event manager
        yield event_manager.get_step_completed_event(prompt_tokens, completion_tokens)

        # Emit run completed event using event manager
        yield event_manager.get_run_completed_event(
            instructions=final_instructions,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Signal completion using event manager
        yield event_manager.get_done_event()

    except Exception as e:
        await fail_run(postgres_pool, run_id, e, "STREAMING_SERVICE")



