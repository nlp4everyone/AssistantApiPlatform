from typing import Optional
from pydantic import BaseModel

class MessageCreation(BaseModel):
    message_id: str

class StepDetails(BaseModel):
    type: str = "message_creation"
    message_creation: Optional[MessageCreation] = None
