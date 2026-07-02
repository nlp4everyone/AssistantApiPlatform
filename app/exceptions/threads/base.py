from ..base_exception import AppException, BaseResponse
from typing import Any
from fastapi import status

class ThreadNotFoundException(AppException):
    def __init__(self,
                 thread_id: str,
                 type: str = "invalid_request_error",
                 params: Any = None,
                 code: Any = None):
        super().__init__(status_code = status.HTTP_404_NOT_FOUND,
                         response = BaseResponse(message = f"No thread found with id '{thread_id}'",
                                                 type = type,
                                                 params = params,
                                                 code = code))