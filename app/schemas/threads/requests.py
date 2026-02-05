from typing import List, Optional
from pydantic import BaseModel
from app.schemas.common import ChatMessage

class CreateThreadRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = None