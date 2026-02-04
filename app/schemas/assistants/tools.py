from pydantic import BaseModel
from typing import Optional, List, Literal

ResponseFormat = Literal["auto","json_schema","json_object"]

class Tool(BaseModel):
    type: Literal["code_interpreter", "file_search", "function"] = "file_search"

class FileSearch(BaseModel):
    vector_store_ids: List[str]

class CodeInterpreter(BaseModel):
    file_ids: List[str]

class ToolResource(BaseModel):
    # Extend according to tool type needs
    code_interpreter: Optional[CodeInterpreter] = None
    file_search: Optional[FileSearch] = None
