from ..base_exception import ResourceNotFoundException

class MessageNotFoundException(ResourceNotFoundException):
    resource = "message"