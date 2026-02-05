from app.schemas.common import BaseDeletedResponse

class DeletedThreadResponse(BaseDeletedResponse):
    object: str = "assistant.deleted"
