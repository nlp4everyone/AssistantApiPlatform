from typing import Optional, Any, Dict, List, Literal
from pydantic import BaseModel
from app.schemas.common import BaseListObject
from app.schemas.common.message import ChatMessage
from .models import TokenUsage
from .steps import StepDetails
from .tools import ToolSchema
from .models import TruncationStrategy

class ThreadObject(BaseModel):
    messages: Optional[List[ChatMessage]] = None
    metadata: Optional[Dict[str, str]] = None
    tool_resources: Optional[Dict[str, Any]] = None

class RunStepObject(BaseModel):
    id: str
    object: Literal["thread.run.step"] = "thread.run.step"
    created_at: int
    run_id: str
    assistant_id: str
    thread_id: str
    type: Literal["message_creation", "tool_call"] = "message_creation"
    status: Literal["queued", "in_progress", "completed", "failed", "cancelled", "expired"] = "queued"
    cancelled_at: Optional[int] = None
    completed_at: Optional[int] = None
    expired_at: Optional[int] = None
    failed_at: Optional[int] = None
    last_error: Optional[Dict[str, Any]] = None
    step_details: StepDetails
    usage: Optional[TokenUsage] = None


class RunObject(BaseModel):
    id: str
    object: Literal["thread.run"] = "thread.run"
    created_at: int
    assistant_id: str
    thread_id: str
    status: Literal["queued", "in_progress", "completed", "failed", "cancelled", "expired"]
    started_at: Optional[int] = None
    expires_at: Optional[int] = None
    cancelled_at: Optional[int] = None
    failed_at: Optional[int] = None
    completed_at: Optional[int] = None
    last_error: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    instructions: Optional[str] = None
    tools: List[ToolSchema] = []
    metadata: Dict[str, Any] = {}
    incomplete_details: Optional[Dict[str, Any]] = None
    usage: Optional[TokenUsage] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_prompt_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    truncation_strategy: Optional[TruncationStrategy] = None
    response_format: Optional[Literal["auto", "json_schema", "json_object"]] = "auto"
    tool_choice: Optional[Literal["auto", "required"]] = "auto"
    parallel_tool_calls: Optional[bool] = True


class RunListObject(BaseListObject):
    data: List[RunObject]