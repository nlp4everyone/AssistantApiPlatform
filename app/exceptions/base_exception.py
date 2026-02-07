from typing import Any
from pydantic import BaseModel

class BaseResponse(BaseModel):
    message :str
    type :str
    params :Any = None
    code :Any = None

class BaseException(Exception):
    def __init__(self, status_code: int, response: BaseResponse):
        self.status_code = status_code
        self.response = response