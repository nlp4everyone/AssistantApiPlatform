from typing import Optional, Any, Dict
from pydantic import BaseModel

class ResponseFormat(BaseModel):
    type: str = "auto"
    json_schema: Optional[Dict[str, Any]] = None

class JsonObjectResponseFormat(BaseModel):
    type: str = "json_object"

class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class TruncationStrategy(BaseModel):
    type: str = "auto"
    last_messages: Optional[int] = None