from pydantic import BaseModel, Field
from typing import Optional, Literal

class BaseListObject(BaseModel):
    object :str = "list"
    first_id :str = ""
    last_id :str = ""
    has_more :bool = False

class PaginationQueryParams(BaseModel):
    limit: int = Field(default = 20,
                       ge = 1,
                       le = 100,
                       description = "Number of object to return (max 100).")
    order: Literal["asc", "desc"] = Field(default = "desc",
                                          description = "Sort order of results by created_at (asc or desc).")
    after: Optional[str] = Field(default = None,
                                 description = "Return rows after this object id (for forward pagination).")
    before: Optional[str] = Field(default=None,
                                  description="Return rows before this object id (for backward pagination).")