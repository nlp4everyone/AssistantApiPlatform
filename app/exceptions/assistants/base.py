from ..base_exception import ResourceNotFoundException

class AssistantNotFoundException(ResourceNotFoundException):
    resource = "assistant"
