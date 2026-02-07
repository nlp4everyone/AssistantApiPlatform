from typing import Any
from fastapi import status
from app.exceptions.base_exception import BaseException, BaseResponse

class InvalidIdFormatException(BaseException):
    def __init__(self,
                 input :str,
                 type: str = "invalid_request_error",
                 params: str = None,
                 prefix :str = None,
                 code: Any = "invalid_value"):
        # Split input type
        prefix = params.split("_")[0] if prefix is None else prefix
        # Inherit
        super().__init__(status_code = status.HTTP_400_BAD_REQUEST,
                         response = BaseResponse(message = f"Invalid '{params}': '{input}'. Expected an ID that begins with '{prefix}'.",
                                                 type = type,
                                                 params = params,
                                                 code = code))
