# Typing
from pydantic import BaseModel
from typing import Optional, Dict, List, Any, Union
# Type
from .tools import Tool, ToolResource, ResponseFormat
# Inheritance
from ..common.base import BaseListObject

class AssistantObject(BaseModel):
    id: str
    object: str = "assistant"
    created_at: int
    name: Union[str,None] = None
    description: Union[str,None] = None
    model: str
    instructions: Union[str,None] = None
    tools: List[Tool] = []
    tool_resources: Optional[Union[ToolResource, dict]] = None
    metadata: Dict[str, Any] = {}
    top_p: float
    temperature: float
    response_format: Optional[ResponseFormat] = "auto"

class AssistantListObject(BaseListObject):
    data :List[AssistantObject]