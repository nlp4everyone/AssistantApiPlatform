from typing import Literal, List, Union, Dict, Any, Optional
from pydantic import BaseModel

ChatRole = Literal["user", "assistant","system"]

class TextContent(BaseModel):
    type: str = "text"
    text: str

class ImageFileContent(BaseModel):
    type: str = "image_file"
    file_id: str

class ImageUrlContent(BaseModel):
    type: str = "image_url"
    image_url: Dict[str, str]

ContentBlock = Union[TextContent, ImageFileContent, ImageUrlContent]

class Attachment(BaseModel):
    file_id: str
    tools: List[Dict[str, Any]] = []

class ChatMessage(BaseModel):
    role: ChatRole = "user"
    content: Union[str, List[ContentBlock]]
    attachments: Optional[List[Attachment]] = None
    metadata: Optional[Dict[str, str]] = None
