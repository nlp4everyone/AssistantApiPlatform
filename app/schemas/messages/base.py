from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.schemas.common import BaseListObject
from .models import ContentItem

class MessageObject(BaseModel):
    id: str
    object: str = "thread.message"
    created_at: int
    thread_id: str
    role: str
    content: List[ContentItem]
    assistant_id: Optional[str] = None
    run_id: Optional[str] = None
    attachments: List[Any] = []
    metadata: Dict[str, Any] = {}
    completed_at: Optional[int] = None
    incomplete_at: Optional[int] = None
    incomplete_details: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class MessageListObject(BaseListObject):
    data :List[MessageObject]