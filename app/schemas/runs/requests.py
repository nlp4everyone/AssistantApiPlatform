from pydantic import Field, BaseModel
from typing import Optional, Any, Dict, List, Union, Literal
from app.schemas.common.message import ChatMessage
from app.schemas.runs.tools import ToolChoice
from app.schemas.runs.models import TruncationStrategy
from app.schemas.runs.models import ResponseFormat, JsonObjectResponseFormat
from app.schemas.threads.requests import CreateThreadRequest

class CreateRunRequest(BaseModel):
    assistant_id: str = Field(..., description="The ID of the assistant to use for this run.")
    additional_instructions: Optional[str] = Field(default = None,
                                                   description = "Extra natural language instructions to override or augment the assistant's default behavior.")
    additional_messages: Optional[List[ChatMessage]] = Field(default = None,
                                                             description="Additional messages to include in the thread context for this run.")
    instructions: Optional[str] = Field(default = None,
                                        description = "Instructions given directly to the model. Overrides assistant-level instructions if provided.")
    max_completion_tokens: Optional[int] = Field(default = None,
                                                 description = "Maximum number of tokens allowed in the run’s response.")
    max_prompt_tokens: Optional[int] = Field(default = None,
                                             description = "Maximum number of tokens allowed in the input prompt.")
    metadata: Optional[Dict[str, str]] = Field(default = None,
                                               description = "Custom metadata you can attach to this run (stored as key-value pairs).")
    model: Optional[str] = Field(default = None,
                                 description = "Override the assistant’s default model for this run.")
    parallel_tool_calls: Optional[bool] = Field(default = True,
                                                description = "Whether to allow multiple tool calls to run in parallel.")
    reasoning_effort: Optional[str] = Field(default = None,
                                            description = "Controls reasoning depth/effort (e.g., 'low', 'medium', 'high').")
    response_format: Optional[Union[Literal["auto"], ResponseFormat, JsonObjectResponseFormat]] = Field(default = None,
                                                                                                        description = "Specify the response format (e.g., 'text', 'json', or custom schema).")
    stream: Optional[bool] = Field(default = None,
                                   description = "Whether to stream partial results back as they are generated.")
    temperature: Optional[float] = Field(default = None,
                                         description = "Sampling temperature; higher values make output more random.")
    tool_choice: Optional[Union[str, ToolChoice]] = Field(default = "auto",
                                                          description = "Specify which tool to call (or let the assistant decide).")
    tools: Optional[List[Dict[str, Any]]] = Field(default = None,
                                                  description = "List of tools available for this run (each tool defined by schema).")
    top_p: Optional[float] = Field(default = None,
                                   description = "Nucleus sampling parameter; considers tokens with top cumulative probability.")
    truncation_strategy: Optional[TruncationStrategy] = Field(default = None,
                                                              description = "Controls how to truncate input if it exceeds max token limits.")


class CreateThreadRunRequest(BaseModel):
    # Required
    assistant_id: str = Field(default = None,
                              description="The ID of the assistant to use to execute this run.")

    # Optional fields
    instructions: Optional[str] = Field(default = None,
                                        description="Override the default system message of the assistant.")
    max_completion_tokens: Optional[int] = None
    max_prompt_tokens: Optional[int] = None
    metadata: Optional[Dict[str, str]] = None
    model: Optional[str] = None
    parallel_tool_calls: Optional[bool] = True
    response_format: Optional[Union[str, ResponseFormat]] = None
    stream: Optional[bool] = None
    temperature: Optional[float] = None
    thread: Optional[CreateThreadRequest] = None
    tool_choice: Optional[Union[str, ToolChoice]] = None
    tool_resources: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    top_p: Optional[float] = None
    truncation_strategy: Optional[TruncationStrategy] = None