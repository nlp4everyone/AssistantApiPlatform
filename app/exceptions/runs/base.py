from ..base_exception import ResourceNotFoundException

class RunNotFoundException(ResourceNotFoundException):
    resource = "run"