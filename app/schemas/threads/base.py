from typing import Dict, Any
from pydantic import BaseModel, Field
from app.schemas.assistants.tools import ToolResource

class ThreadObject(BaseModel):
    id: str
    object: str = "thread"
    created_at: int
    metadata: Dict[str, Any] = {}
    tool_resources: ToolResource = Field(default_factory=ToolResource)