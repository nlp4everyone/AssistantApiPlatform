from typing import Literal
import uuid

PREFIX_MAP = {
    "thread": "thread",
    "message": "msg",
    "assistant": "asst",
    "step": "step",
    "run": "run",
}

def generate_assistant_object(object :Literal["assistant","thread","message","run","step"] = "thread"):
    """
    Generate a unique ID for assistant objects.

    Creates a unique identifier by combining a type-specific prefix with a UUID.
    The generated ID follows the format: {prefix}_{uuid_suffix}

    Args:
        object: The type of object to generate an ID for. Must be one of:
            - "assistant": For assistant objects (prefix: "asst")
            - "thread": For thread objects (prefix: "thread") 
            - "message": For message objects (prefix: "msg")
            - "run": For run objects (prefix: "run")
            - "step": For step objects (prefix: "step")
            Defaults to "thread".

    Returns:
        str: A unique identifier string in the format "{prefix}_{uuid_suffix}".
             The UUID suffix is 24 characters long.

    Raises:
        KeyError: If the object type is not found in PREFIX_MAP.

    Examples:
        >>> generate_assistant_object("thread")
        'thread_a1b2c3d4e5f6g7h8i9j0k1l2'
        >>> generate_assistant_object("assistant") 
        'asst_f3e4d5c6b7a8f9e0d1c2b3a4'
    """
    prefix = PREFIX_MAP[object]
    return f"{prefix}_{uuid.uuid4().hex[:24]}"