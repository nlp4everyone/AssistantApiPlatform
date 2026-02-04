from ..common.responses import BaseDeletedResponse

class DeletedAssistantResponse(BaseDeletedResponse):
    object: str = "assistant.deleted"
