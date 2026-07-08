# Object Schema
from app.schemas.common import ChatMessage
# Postgres Message database
from app.db.postgres import PostgresMessageStore
# Config
from app.core.config import NUMS_OF_PREVIOUS_INTERACTION
# Schema
from app.schemas.runs.requests import CreateRunRequest, CreateThreadRunRequest
# Typing
from typing import Union, Tuple, List, Dict
# Utilities
from app.utils.messaging import update_messages_response
# Other components
import asyncpg

def convert_to_chat_message(message) -> Dict[str, str]:
    """Helper to convert different message types to ChatMessage dict."""
    if hasattr(message, 'role') and hasattr(message, 'content'):
        if hasattr(message.content, '__iter__') and not isinstance(message.content, str):
            # Database message with nested content structure
            return ChatMessage(role=message.role, content=message.content[0].text.value).model_dump()
        else:
            # Message with direct content
            return ChatMessage(role=message.role, content=message.content).model_dump()
    return dict(message)

async def prepare_messages(request: Union[CreateRunRequest, CreateThreadRunRequest],
                            postgres_pool: asyncpg.Pool,
                            thread_id: str,
                            instructions: str) -> Tuple[List[dict], List[dict], str]:
    """
    Prepare messages for AI processing by fetching thread messages and combining with additional data.
    
    Args:
        request: Either CreateRunRequest or CreateThreadRunRequest containing message data
        postgres_pool: Database connection pool for fetching thread messages
        thread_id: ID of the thread to fetch messages from
        instructions: Base instructions to be used for AI processing
        
    Returns:
        Tuple containing:
        - messages: Complete list of messages for AI processing
        - external_messages: Messages that still need to be persisted (additional_messages on an
          existing thread); empty for create-and-run, since the thread's seed messages are already
          persisted by ThreadService.create_thread
        - instructions: Updated instructions string with any additional instructions appended
    """
    
    if isinstance(request, CreateRunRequest):
        # Fetch and convert existing thread messages
        db_messages = await PostgresMessageStore.get_thread_messages(
            pool=postgres_pool,
            thread_id=thread_id,
            limit=NUMS_OF_PREVIOUS_INTERACTION,
            order="asc"
        )

        messages = [convert_to_chat_message(msg) for msg in update_messages_response(db_messages)]
        
        # Include additional messages from request if provided
        if request.additional_messages:
            additional_messages = [convert_to_chat_message(msg) for msg in request.additional_messages]
            messages.extend(additional_messages)
            external_messages = additional_messages
        else:
            external_messages = []
        
        # Append additional instructions to base instructions if provided
        if request.additional_instructions:
            instructions += request.additional_instructions
            
    else:  # CreateThreadRunRequest - messages already persisted (tagged with
        # this run_id) by ThreadService.create_thread, so nothing new to insert
        thread_messages = request.thread.messages if request.thread else None
        messages = [dict(message) for message in thread_messages or []]
        external_messages = []
    
    return messages, external_messages, instructions
