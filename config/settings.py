import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent


def _default_local_state_dir() -> Path:
    if os.name == "nt":
        base_dir = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base_dir = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base_dir / "HFT-Bot-2.0"


DEFAULT_LOCAL_STATE_DIR = _default_local_state_dir()
DEFAULT_LOCAL_DATABASE_PATH = DEFAULT_LOCAL_STATE_DIR / "hft_platform.db"
LEGACY_DATABASE_PATH = ROOT_DIR / "database" / "hft_platform.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_LOCAL_DATABASE_PATH.resolve().as_posix()}"
DEFAULT_LOGS_DIR = DEFAULT_LOCAL_STATE_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Local Automated Trading Platform"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    local_state_dir: Path = DEFAULT_LOCAL_STATE_DIR
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = "redis://localhost:6379/0"
    event_bus_backend: str = "auto"
    timescaledb_enabled: bool = True

    log_level: str = "INFO"
    logs_dir: Path = DEFAULT_LOGS_DIR

    heartbeat_interval_seconds: float = 5.0
    service_loop_interval_seconds: float = 1.0
    simulate_market_data: bool = True

    max_capital_per_trade: float = 5000.0
    max_open_positions: int = 5
    max_daily_loss: float = 1000.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

