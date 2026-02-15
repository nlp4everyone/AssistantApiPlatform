import json

def sse_event(event: str, data) -> str:
    """Format a Server-Sent Event (SSE) message."""
    if isinstance(data, str) and data == "[DONE]":
        # Special marker, no JSON encoding
        return f"event: {event}\ndata: {data}\n\n"
    else:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"