import os
from app.utils.config_loader import get_toml_config

# Model configuration
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME")

# Load interaction settings from TOML
toml_config = get_toml_config()
interaction_config = toml_config.get_section("interaction")

# Interaction parameters
NUMS_OF_PREVIOUS_INTERACTION = interaction_config.get("NUMS_OF_PREVIOUS_INTERACTION")
