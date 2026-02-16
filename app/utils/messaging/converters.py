# Typing
from typing import List, Dict
# Schemas
from app.schemas.messages import MessageTextContent, ContentItem, MessageObject
from app.schemas.common import ChatMessage
# Utils
from app.utils.id_generation import generate_assistant_object
# Langchain Message
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
# Other components
import time

def _convert_to_message_objects(messages: List[Dict[str, str]],
                                thread_id: str,
                                message_id: str = None) -> List[Dict]:
    """Convert message dictionaries to MessageObject format."""
    final_data = []
    for message in messages:
        # Text content
        text_content = MessageTextContent(value=message.get("content"))
        content = [ContentItem(text=text_content)]

        # Message Object - use provided message_id or generate new one
        msg_id = message_id if message_id else generate_assistant_object(object="message")
        message_object = MessageObject(
            id=msg_id,
            created_at=int(time.time()),
            thread_id=thread_id,
            role=message.get("role"),
            content=content
        ).model_dump()
        
        final_data.append(message_object)
    
    return final_data


def _convert_to_langchain_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert message dictionaries to LangChain message format."""
    output = []
    for message in messages:
        # Human message
        if message.get("role") == "system":
            output.append(SystemMessage(content=message.get("content")))
        elif message.get("role") == "user":
            output.append(HumanMessage(content=message.get("content")))
        else:
            output.append(AIMessage(content=message.get("content")))
    
    return output


def convert_langchain_to_chat_messages(langchain_messages: List[BaseMessage]) -> List[ChatMessage]:
    """
    Convert a list of LangChain BaseMessage objects to ChatMessage objects.

    Args:
        langchain_messages: List of LangChain BaseMessage objects (HumanMessage, AIMessage, SystemMessage)

    Returns:
        List[ChatMessage]: List of converted ChatMessage objects

    Raises:
        ValueError: If an unsupported message type is encountered
    """
    chat_messages = []

    for message in langchain_messages:
        # Handle different LangChain message types
        if isinstance(message, HumanMessage):
            chat_message = ChatMessage(
                role="user",
                content=message.content
            ).model_dump(exclude={"attachments", "metadata"})
        elif isinstance(message, AIMessage):
            chat_message = ChatMessage(
                role="assistant",
                content=message.content
            ).model_dump(exclude={"attachments", "metadata"})
        elif isinstance(message, SystemMessage):
            # System messages are typically handled as user messages with special context
            # or could be filtered out depending on use case
            chat_message = ChatMessage(
                role="system",
                content=message.content
            ).model_dump(exclude={"attachments", "metadata"})
        else:
            # Handle other BaseMessage subclasses or raise error
            raise ValueError(f"Unsupported message type: {type(message).__name__}")

        chat_messages.append(chat_message)

    return chat_messages