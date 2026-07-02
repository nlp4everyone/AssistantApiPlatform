from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.common import ChatMessage
from app.schemas.assistants.tools import ToolResource

class CreateThreadRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = None
    metadata: Optional[Dict[str, Any]] = {}
    tool_resources: ToolResource = Field(default_factory=ToolResource)