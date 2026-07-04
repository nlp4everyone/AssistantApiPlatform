import json
from typing import List, Dict, Any
from app.schemas.messages import MessageObject
from app.schemas.assistants.base import AssistantObject

def update_assistant_response(res: List[Dict[str, Any]]) -> List[AssistantObject]:
    """
    Update assistant response data with correct format types.

    Processes a list of raw assistant data from the database and converts each
    to a validated AssistantObject with proper field formatting.

    Args:
        res: List of dictionaries containing raw assistant response data from the database.
              Each dictionary should include:
              - assistant_id: The assistant ID to use as the response ID
              - tools: JSON string of tool definitions (optional)
              - metadata: JSON string of metadata (optional)
              - tool_resources: JSON string of tool resources (optional)
              - created_at: DateTime object for creation timestamp

    Returns:
        List[AssistantObject]: List of validated AssistantObject instances with:
                              - id: Set to assistant_id value
                              - tools: Parsed list of tool definitions (empty list if None)
                              - metadata: Parsed metadata dict (empty dict if None)
                              - tool_resources: Parsed tool resources dict (empty dict if None)
                              - created_at: Unix timestamp as integer
    """
    assistant_objects = []
    for assistant_data in res:
        # Update id to assistant id
        assistant_data.update({"id": assistant_data.get("assistant_id")})
        
        # Normalize format:
        # Tools
        tools = assistant_data.get("tools")
        assistant_data.update({"tools": json.loads(tools) if tools else []})
        
        # Metadata
        metadata = assistant_data.get("metadata")
        assistant_data.update({"metadata": json.loads(metadata) if metadata else {}})
        
        # Tool resources
        tool_resources = assistant_data.get("tool_resources")
        assistant_data.update({"tool_resources": json.loads(tool_resources) if tool_resources else {}})
        
        # Created at
        assistant_data.update({"created_at": int(assistant_data.get("created_at").timestamp())})
        
        # Validate and append AssistantObject
        assistant_objects.append(AssistantObject.model_validate(assistant_data))
    
    return assistant_objects

def update_messages_response(messages: List[Dict[str, Any]]) -> List[MessageObject]:
    """
    Update and validate messages response data with correct format types.

    Processes a list of raw message data from the database and converts each
    message into a validated MessageObject with proper field formatting.

    Args:
        messages: List of dictionaries containing raw message data from the database.
                 Each message should include:
                 - created_at: DateTime object for creation timestamp
                 - content: JSON string of message content
                 - attachments: JSON string of attachments
                 - metadata: JSON string of message metadata

    Returns:
        List[MessageObject]: List of validated MessageObject instances with:
                           - created_at: Unix timestamp as integer
                           - content: Parsed list of content objects
                           - attachments: Parsed attachments list
                           - metadata: Parsed metadata dict
    """
    messages_object = []
    for message in messages:
        # Update with new value
        message.update({"created_at": int(message.get("created_at").timestamp())})
        message.update({"content": [json.loads(message.get("content"))]})
        message.update({"attachments": json.loads(message.get("attachments"))})
        message.update({"metadata": json.loads(message.get("metadata"))})
        
        # Parse
        messages_object.append(MessageObject.model_validate(message))
    
    return messages_object
