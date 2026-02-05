from typing import List, Any
from pydantic import BaseModel

class MessageTextContent(BaseModel):
    value: str
    annotations: List[Any] = []

class ContentItem(BaseModel):
    type: str = "text"
    text: MessageTextContent