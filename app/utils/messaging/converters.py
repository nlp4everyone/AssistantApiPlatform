# Typing
from typing import List, Dict
# Schemas
from app.schemas.messages import MessageTextContent, ContentItem, MessageObject
# Utils
from app.utils.id_generation import generate_assistant_object
# Langchain Message
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
# Other components
import time

def _convert_to_message_objects(messages: List[Dict[str, str]],
                                thread_id: str) -> List[Dict]:
    """Convert message dictionaries to MessageObject format."""
    final_data = []
    for message in messages:
        # Text content
        text_content = MessageTextContent(value=message.get("content"))
        content = [ContentItem(text=text_content)]

        # Message Object
        message_object = MessageObject(
            id=generate_assistant_object(object="message"),
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
