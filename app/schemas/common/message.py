from typing import Literal
from pydantic import BaseModel

ChatRole = Literal["system", "user", "assistant"]
class ChatMessage(BaseModel):
    role: ChatRole = "user"
    content: str