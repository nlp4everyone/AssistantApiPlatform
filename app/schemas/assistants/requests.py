from pydantic import BaseModel, Field, constr, confloat
from typing import Optional, Dict, List, Literal
from .tools import Tool, ToolResource, ResponseFormat
# Config
from app.core.config.prompts import DEFAULT_ASSISTANT_PROMPT
from app.core.config.models import LLM_MODEL_NAME

class CreateAssistantRequest(BaseModel):
    model: constr(strip_whitespace = True, min_length = 1) = Field(
        default = LLM_MODEL_NAME,
        description=(
            "ID of the model to use.\n\n"
            "Example: `Qwen3-8B` or another available model ID."
        ),
    )
    description: Optional[constr(max_length = 256)] = Field(
        default = None,
        description="A short description of the assistant (max 256 characters).",
        examples = None
    )
    instructions: Optional[constr(max_length = 256000)] = Field(
        default = DEFAULT_ASSISTANT_PROMPT,
        description = "System instructions that guide the assistant's behavior (max 256,000 characters).",
    )
    metadata: Optional[Dict[constr(max_length = 64), constr(max_length=512)]] = Field(
        default = None,
        description="Custom metadata as key-value pairs (key max 64 chars, value max 512 chars).",
        examples = None,
    )
    name: Optional[constr(max_length=256)] = Field(
        default = "Helper Assistant",
        description = "The display name of the assistant (max 256 characters).",
    )
    reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = Field(
        default = "medium",
        description="The level of reasoning effort to allocate (minimal, low, medium, high).",
    )
    response_format: Optional[ResponseFormat] = Field(
        default = "auto",
        description="Specifies the desired response format (e.g., JSON, text).",
    )
    temperature: Optional[confloat(ge=0, le=2)] = Field(
        default=1,
        description="Sampling temperature; higher values (closer to 2) make output more random, "
                    "lower values (closer to 0) make it more deterministic."
    )
    tool_resources: Optional[ToolResource] = Field(
        default = None,
        description = "Resources available for tools, such as file references or APIs.",
        examples = None,
    )
    tools: Optional[List[Tool]] = Field(
        default_factory=list,
        max_items=128,
        description="A list of tools the assistant can use (up to 128)."
    )
    top_p: Optional[confloat(ge=0, le=1)] = Field(
        default=1,
        description="Controls nucleus sampling; model considers tokens with top_p probability mass. "
                    "0.9 means only top 90% probability tokens are used."
    )
