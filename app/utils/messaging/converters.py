# Typing
from typing import List, Dict, Union
# Schemas
from app.schemas.messages import MessageTextContent, ContentItem, MessageObject
from app.schemas.common.message import ContentBlock
# Utils
from app.utils.id_generation import generate_assistant_object
# Other components
import time

def _build_content_items(content: Union[str, List[ContentBlock]]) -> List[ContentItem]:
    """Convert a ChatMessage content field (string or content blocks) into ContentItem list."""
    if isinstance(content, str):
        return [ContentItem(text=MessageTextContent(value=content))]

    items = []
    for block in content:
        if block.type == "text":
            items.append(ContentItem(text=MessageTextContent(value=block.text)))
        elif block.type == "image_file":
            items.append(ContentItem(text=MessageTextContent(value=f"[Image file: {block.file_id}]")))
        elif block.type == "image_url":
            items.append(ContentItem(text=MessageTextContent(value=f"[Image URL: {block.image_url.get('url', '')}]")))
    return items


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


def _to_openai_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Normalize message dictionaries into OpenAI chat completion message format."""
    output = []
    for message in messages:
        role = message.get("role")
        # Any role other than "system"/"user" is treated as an assistant turn
        role = role if role in ("system", "user") else "assistant"
        output.append({"role": role, "content": message.get("content")})

    return output