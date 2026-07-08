# Typing
from typing import List, Dict, Union
# Schemas
from app.schemas.messages import MessageTextContent, ContentItem, MessageObject
from app.schemas.common.message import ContentBlock
# Utils
from app.utils.id_generation import generate_assistant_object
# Other components
import time

def build_content_items(content: Union[str, List[ContentBlock]]) -> List[ContentItem]:
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


def convert_to_message_objects(messages: List[Dict[str, str]],
                                thread_id: str,
                                message_id: str = None,
                                id_prefix: str = None) -> List[Dict]:
    """Convert message dictionaries to MessageObject format.

    id_prefix derives a deterministic id per message (msg_{id_prefix}_ext{i})
    instead of a fresh random one, so a redelivered background task re-emits
    the same ids and duplicate inserts are absorbed by ON CONFLICT DO NOTHING.

    message_id pins a single fixed id and is only valid for a single message —
    reusing it across multiple messages would silently collide on insert.
    """
    if message_id and len(messages) > 1:
        raise ValueError("message_id can only be used with a single message; pass id_prefix for multiple messages")

    final_data = []
    for i, message in enumerate(messages):
        # Text content
        text_content = MessageTextContent(value=message.get("content"))
        content = [ContentItem(text=text_content)]

        # Message Object - use provided/derived message_id or generate new one
        if message_id:
            msg_id = message_id
        elif id_prefix:
            msg_id = f"msg_{id_prefix}_ext{i}"
        else:
            msg_id = generate_assistant_object(object="message")
        message_object = MessageObject(
            id=msg_id,
            created_at=int(time.time()),
            thread_id=thread_id,
            role=message.get("role"),
            content=content
        ).model_dump()

        final_data.append(message_object)

    return final_data


def to_openai_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Normalize message dictionaries into OpenAI chat completion message format."""
    output = []
    for message in messages:
        role = message.get("role")
        # Any role other than "system"/"user" is treated as an assistant turn
        role = role if role in ("system", "user") else "assistant"
        output.append({"role": role, "content": message.get("content")})

    return output