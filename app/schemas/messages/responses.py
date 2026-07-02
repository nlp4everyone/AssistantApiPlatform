
from app.schemas.common import BaseDeletedResponse

class DeletedMessageResponse(BaseDeletedResponse):
    object: str = "thread.message.deleted"

