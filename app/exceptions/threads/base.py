from ..base_exception import ResourceNotFoundException

class ThreadNotFoundException(ResourceNotFoundException):
    resource = "thread"