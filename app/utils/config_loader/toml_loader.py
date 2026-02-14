import os
import toml
from typing import Dict, Any


class TomlConfigLoader:
    """Handles loading and accessing TOML configuration files."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize the TOML config loader.
        
        Args:
            config_path: Path to the TOML config file. If None, uses default path.
        """
        if config_path is None:
            # Default path: project root/config/config.toml
            # Navigate from app/utils/config_loader/ to project root
            current_dir = os.path.dirname(__file__)
            project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
            config_path = os.path.join(project_root, "config", "config.toml")
        
        self.config_path = config_path
        self._config = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load the TOML configuration file."""
        try:
            self._config = toml.load(self.config_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"TOML config file not found at: {self.config_path}")
        except toml.TomlDecodeError as e:
            raise ValueError(f"Invalid TOML format in {self.config_path}: {e}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a value from the TOML config using dot notation.
        
        Args:
            key_path: Dot-separated path to the key (e.g., "api.SERVING_API_KEY")
            default: Default value if key is not found
            
        Returns:
            The configuration value or default
        """
        if self._config is None:
            return default
            
        keys = key_path.split(".")
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_section(self, section_name: str) -> Dict[str, Any]:
        """
        Get an entire section from the TOML config.
        
        Args:
            section_name: Name of the section
            
        Returns:
            Dictionary containing the section data
        """
        if self._config is None:
            return {}
        
        return self._config.get(section_name, {})
    
    def reload(self) -> None:
        """Reload the TOML configuration file."""
        self._load_config()


# Global instance for easy access
_toml_loader = TomlConfigLoader()


def get_toml_config() -> TomlConfigLoader:
    """Get the global TOML config loader instance."""
    return _toml_loader


def reload_toml_config() -> None:
    """Reload the global TOML configuration."""
    _toml_loader.reload()
