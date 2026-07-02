from typing import List, Literal
from pydantic import BaseModel

class Annotation(BaseModel):
    # Adjust if OpenAI adds more fields
    # For now it's just an empty list
    pass

class TextDelta(BaseModel):
    value: str
    annotations: List[Annotation] = []

class TextDeltaBlock(BaseModel):
    index: int
    type: str = "text"  # can extend later if more types appear
    text: TextDelta

class MessageDelta(BaseModel):
    content: List[TextDeltaBlock]

class MessageDeltaEvent(BaseModel):
    id: str
    object: Literal["thread.message.delta"] = "thread.message.delta"
    delta: MessageDelta