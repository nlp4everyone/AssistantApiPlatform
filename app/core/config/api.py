from app.utils.config_loader import get_toml_config
import os
# Load API keys from TOML
toml_config = get_toml_config()
api_config = toml_config.get_section("api")

# API keys from TOML
FASTAPI_API_KEY = api_config.get("FASTAPI_API_KEY")

# LLM serving connection (external OpenAI-compatible server, e.g. vLLM/SGLang)
SERVING_API_KEY = os.getenv("SERVING_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
