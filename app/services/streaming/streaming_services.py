# Define schema
from app.schemas.common import ChatMessage
from app.schemas.runs import *
from app.schemas.runs.models import TokenUsage
# Postgres DB
from app.db.postgres import PostgresRunStore, PostgresMessageStore
# Utils
from app.utils.events import EventManager
from app.utils.messaging import (_convert_to_message_objects,
                                 _convert_to_langchain_messages,
                                 convert_langchain_to_chat_messages)
# Langchain imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
# Token counter
from app.utils.token_counter import approximate_count_tokens
# Typing
from typing import AsyncIterable
# Logger
from loggers import SystemLogger
# Common
from app.services.common import prepare_generation_context
# Import dependencies
import asyncpg, mlflow
from mlflow.entities import SpanType
# Enable logging
mlflow.config.enable_async_logging()

async def handle_streaming_response(postgres_pool: asyncpg.Pool,
                                    llm: ChatOpenAI,
                                    request: dict,
                                    thread_id: str,
                                    run_id: str,
                                    step_id: str,
                                    message_id: str,
                                    assistant_id: str,
                                    instructions: str,
                                    temperature: float = None,
                                    top_p: float = None) -> AsyncIterable:
    """
    Handle streaming response using ChatOpenAI directly instead of LangGraph.
    
    Args:
        postgres_pool: Database connection pool
        llm: ChatOpenAI instance for generation
        request: Request dictionary
        thread_id: Thread identifier
        run_id: Run identifier  
        step_id: Step identifier
        message_id: Message identifier
        assistant_id: Assistant identifier
        instructions: System instructions
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        
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
        top_p=top_p):
        yield event


async def stream_response_from_messages(postgres_pool: asyncpg.Pool,
                                        llm: ChatOpenAI,
                                        context_data: dict,
                                        thread_id: str,
                                        run_id: str,
                                        step_id: str,
                                        message_id: str,
                                        assistant_id: str,
                                        temperature: float = None,
                                        top_p: float = None) -> AsyncIterable:
    """
    Stream response from prepared messages using ChatOpenAI.
    
    Args:
        postgres_pool: Database connection pool
        llm: ChatOpenAI instance for generation
        context_data: Context data from prepare_generation_context
        thread_id: Thread identifier
        run_id: Run identifier
        step_id: Step identifier
        message_id: Message identifier
        assistant_id: Assistant identifier
        temperature: Optional temperature for generation randomness
        top_p: Optional top_p for nucleus sampling
        
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
        # Convert to LangChain format
        langchain_messages = _convert_to_langchain_messages(messages)
        if final_instructions:
            langchain_messages.insert(0, SystemMessage(content=final_instructions))
        
        # Set LLM parameters - use passed parameters, falling back to request values
        final_temperature = temperature if temperature is not None else validated_request.temperature
        final_top_p = top_p if top_p is not None else validated_request.top_p
        max_completion_tokens = validated_request.max_completion_tokens
        
        llm.temperature = final_temperature
        llm.top_p = final_top_p  
        llm.max_tokens = max_completion_tokens
        
        # Update status to running
        await PostgresRunStore.update_run_status(
            pool=postgres_pool,
            run_id=run_id,
            status=RunStatus.RUNNING
        )

        # Tracking with span
        with mlflow.start_span(span_type=SpanType.CHAT_MODEL) as span:
            # Set input
            span.set_inputs(convert_langchain_to_chat_messages(langchain_messages))

            # Stream response using ChatOpenAI
            response_chunks = []
            async for chunk in llm.astream(langchain_messages):
                if chunk.content:
                    response_chunks.append(chunk.content)

                    # Emit delta event using event manager
                    yield event_manager.get_delta_event(chunk.content)

            # Combine all chunks
            final_response = "".join(response_chunks)
            # Set output
            span.set_outputs([{"role": "assistant", "content": final_response}])

        # Define response
        response_message = ChatMessage(role="assistant", content=final_response).model_dump()

        # Store the complete response
        await PostgresMessageStore.insert_messages(
            pool=postgres_pool,
            thread_id=thread_id,
            data={
                "data": _convert_to_message_objects(messages=[response_message], thread_id=thread_id, message_id=message_id),
                "assistant_id": assistant_id,
                "run_id": run_id
            }
        )
        
        # Count tokens
        prompt_tokens = approximate_count_tokens(messages)
        completion_tokens = approximate_count_tokens(response_message)

        # Update run usage
        await PostgresRunStore.update_run_usage(
            pool=postgres_pool,
            run_id=run_id,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            ).model_dump()
        )
        
        # Update final status
        await PostgresRunStore.update_run_status(
            pool=postgres_pool,
            run_id=run_id,
            status=RunStatus.COMPLETED
        )

        # Update state
        mlflow.flush_async_logging()

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
        SystemLogger.error(f"Streaming generation failed for run {run_id}: {e}")
        await PostgresRunStore.update_run_status(
            pool=postgres_pool,
            run_id=run_id,
            status=RunStatus.FAILED
        )



