from typing import Optional
from pydantic import BaseModel

class ToolChoiceFunction(BaseModel):
    name: str

class ToolChoice(BaseModel):
    type: str = "auto"
    function: Optional[ToolChoiceFunction] = None

class ToolSchema(BaseModel):
    type: str = "file_search"
