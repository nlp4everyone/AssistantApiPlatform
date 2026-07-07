from typing import Annotated, Literal
from fastapi import Path, Depends
from app.exceptions import InvalidIdFormatException
from app.utils.id_generation.generators import PREFIX_MAP

ObjectType = Literal["assistant", "thread", "message", "step", "run"]

def validate_id_prefix(value: str, param_name: str, object_type: ObjectType) -> str:
    """
    Validate that `value` begins with the prefix registered for `object_type` in PREFIX_MAP.

    Use directly for IDs that arrive outside a path parameter (request body fields,
    query params). For path parameters, prefer the ready-made `*IdPath` dependencies below.
    """
    prefix = PREFIX_MAP[object_type]
    if not value.startswith(prefix):
        raise InvalidIdFormatException(input = value, params = param_name, prefix = prefix)
    return value

def require_id_prefix(object_type: ObjectType, param_name: str):
    def _dependency(value: str = Path(alias = param_name)) -> str:
        return validate_id_prefix(value, param_name, object_type)
    return _dependency

ThreadIdPath = Annotated[str, Depends(require_id_prefix("thread", "thread_id"))]
AssistantIdPath = Annotated[str, Depends(require_id_prefix("assistant", "assistant_id"))]
MessageIdPath = Annotated[str, Depends(require_id_prefix("message", "message_id"))]
RunIdPath = Annotated[str, Depends(require_id_prefix("run", "run_id"))]