from typing import Dict, Any, Union
from pydantic import BaseModel
from app.schemas.assistants.tools import ToolResource

class ThreadObject(BaseModel):
    id: str
    object: str = "thread"
    created_at: int
    metadata: Dict[str, Any] = {}
    tool_resources: Union[ToolResource, dict] = {}