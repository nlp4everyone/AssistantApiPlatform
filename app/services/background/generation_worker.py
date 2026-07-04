# Typing
from typing import List, Dict
# Object Schema
from app.schemas.common import ChatMessage
from app.schemas.runs import RunStatus
# Postgres DB
from app.db.postgres import PostgresRunStore
# Utils
from app.utils.token_counter import approximate_count_tokens
# Common services
from app.services.common import (prepare_generation_context,
                                 build_chat_request,
                                 tag_span,
                                 record_span_metrics,
                                 persist_and_complete,
                                 fail_run)
# OpenAI client
from openai import AsyncOpenAI
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
    chat_messages, request_kwargs = build_chat_request(messages, instructions, max_completion_tokens, temperature, top_p)

    # Update run status to indicate generation is in progress
    await PostgresRunStore.update_run_status(
        pool=postgres_pool,
        run_id=run_id,
        status=RunStatus.RUNNING
    )

    # Tracking with span
    with mlflow.start_span(name = endpoint_path, span_type = SpanType.CHAT_MODEL) as span:
        tag_span(span, chat_messages, thread_id, run_id, message_id, assistant_id)

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

        record_span_metrics(span,
                             temperature=temperature,
                             top_p=top_p,
                             max_completion_tokens=max_completion_tokens,
                             stream=False,
                             prompt_tokens=prompt_tokens,
                             completion_tokens=completion_tokens,
                             generation_time=generation_time,
                             response_content=response_content)

    await persist_and_complete(postgres_pool,
                                thread_id=thread_id,
                                run_id=run_id,
                                assistant_id=assistant_id,
                                message_id=message_id,
                                response_message=response_message,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens)

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
        await fail_run(postgres_pool, run_id, e, "GENERATION_WORKER")




