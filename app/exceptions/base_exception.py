from typing import Any
from pydantic import BaseModel
from fastapi import status

class BaseResponse(BaseModel):
    message :str
    type :str
    params :Any = None
    code :Any = None

class AppException(Exception):
    def __init__(self, status_code: int, response: BaseResponse):
        super().__init__(response.message)
        self.status_code = status_code
        self.response = response

class ResourceNotFoundException(AppException):
    resource: str = "resource"

    def __init__(self, id: str, type: str = "invalid_request_error", params: Any = None, code: Any = None):
        super().__init__(status_code = status.HTTP_404_NOT_FOUND,
                         response = BaseResponse(message = f"No {self.resource} found with id '{id}'",
                                                 type = type,
                                                 params = params,
                                                 code = code))