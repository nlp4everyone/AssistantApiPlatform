from pydantic import BaseModel

class BaseDeletedResponse(BaseModel):
    id: str
    object: str
    deleted: bool = True