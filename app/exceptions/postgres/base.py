from ..base_exception import AppException, BaseResponse
from typing import Any
from fastapi import status

class PostgresConnectionException(AppException):
    def __init__(self,
                 type: str = "connection_error",
                 params: Any = None,
                 code: Any = None):
        super().__init__(status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
                         response = BaseResponse(message = "Could not connect to Postgres database",
                                                 type = type,
                                                 params = params,
                                                 code = code))