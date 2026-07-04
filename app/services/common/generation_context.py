# Object Schema
from app.schemas.runs.requests import CreateRunRequest, CreateThreadRunRequest
# Postgres DB
from app.db.postgres import PostgresRunStore, PostgresMessageStore
# Utils
from app.utils.messaging import prepare_messages, convert_to_message_objects
# Dependencies
import asyncpg

async def prepare_generation_context(postgres_pool: asyncpg.Pool,
                                     request: dict,
                                     thread_id: str,
                                     run_id: str,
                                     assistant_id: str,
                                     instructions: str) -> dict:
    """
    Prepare messages and context for generation.
    
    Args:
        postgres_pool: Database connection pool
        request: Request dictionary
        thread_id: Thread identifier
        run_id: Run identifier
        assistant_id: Assistant identifier
        instructions: System instructions
        
    Returns:
        dict: Context data containing validated_request, messages, external_messages, final_instructions
    """
    # Validate request
    validated_request = (CreateRunRequest.model_validate(request) 
                        if request.get("thread") is None 
                        else CreateThreadRunRequest.model_validate(request))
    
    # Create run
    await PostgresRunStore.create_run(
        pool=postgres_pool,
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=assistant_id,
        max_prompt_tokens=validated_request.max_prompt_tokens,
        max_completion_tokens=validated_request.max_completion_tokens
    )
    
    # Prepare messages and context
    messages, external_messages, final_instructions = await prepare_messages(
        request=validated_request,
        thread_id=thread_id,
        postgres_pool=postgres_pool,
        instructions=instructions
    )
    
    # Store external messages if any
    if external_messages:
        await PostgresMessageStore.insert_messages(
            pool=postgres_pool,
            thread_id=thread_id,
            data={
                "data": convert_to_message_objects(messages=external_messages, thread_id=thread_id),
                "assistant_id": assistant_id,
                "run_id": run_id
            }
        )
    
    return {
        "validated_request": validated_request,
        "messages": messages,
        "external_messages": external_messages,
        "final_instructions": final_instructions
    }
