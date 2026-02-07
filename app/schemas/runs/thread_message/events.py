from app.schemas.runs.thread_message.deltas import MessageDelta
from typing import Literal
from pydantic import BaseModel

class MessageDeltaEvent(BaseModel):
    id: str
    object: Literal["thread.message.delta"] = "thread.message.delta"
    delta: MessageDelta