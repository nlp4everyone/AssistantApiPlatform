from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel

class ThreadMessage(BaseModel):
    id: str
    object: Literal["thread.message"] = "thread.message"
    created_at: int
    assistant_id: Optional[str] = None
    thread_id: str
    run_id: Optional[str] = None
    status: Literal["in_progress", "completed", "failed", "cancelled", "queued"] = "in_progress"
    incomplete_details: Optional[Dict[str, Any]] = None
    incomplete_at: Optional[int] = None
    completed_at: Optional[int] = None
    role: Literal["user", "assistant", "system"] = "assistant"
    content: List[Any] = []        # refine if you have schema for content
    attachments: List[Any] = []    # refine if you have schema for attachments
    metadata: Dict[str, Any] = {}

