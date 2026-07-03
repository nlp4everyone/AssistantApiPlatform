import os
from app.utils.config_loader import get_toml_config

# Model configuration
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")

# Qwen3 is a hybrid thinking/non-thinking model; disable the <think> reasoning trace.
LLM_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

# Load interaction settings from TOML
toml_config = get_toml_config()
interaction_config = toml_config.get_section("interaction")

# Interaction parameters
NUMS_OF_PREVIOUS_INTERACTION = interaction_config.get("NUMS_OF_PREVIOUS_INTERACTION")
