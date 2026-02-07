from app.schemas.common import BaseDeletedResponse

class DeletedRunResponse(BaseDeletedResponse):
    object: str = "thread.run.deleted"

class DeletedRunStepResponse(BaseDeletedResponse):
    object: str = "thread.run.step.deleted"
