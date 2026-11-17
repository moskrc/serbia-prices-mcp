from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERBIA_PRICES_MCP_", env_ignore_empty=True)

    data_dir: Path = Path.home() / ".cache" / "serbia-prices-mcp"
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
