from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventMessage(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    source: str
    symbol: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EngineStatus(BaseModel):
    name: str
    healthy: bool
    status: str
    last_heartbeat: datetime | None = None
    message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class StrategyConfigurationPayload(BaseModel):
    display_name: str
    enabled: bool
    experience_mode: str = "guided"
    timeframe: str
    capital_allocation_pct: float
    risk_tolerance: int = 50
    parameters_json: dict[str, Any] = Field(default_factory=dict)


class WorkspacePreferencePayload(BaseModel):
    experience_mode: str = "guided"
    risk_tolerance: int = 50
    selected_profile: str | None = None
    auto_apply_to_strategies: bool = True
    kill_switch: bool = False
    require_confirmation: bool = True


class ApiCredentialSettingsPayload(BaseModel):
    polygon_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    webull_username: str = ""
    webull_password: str = ""
    polygon_enabled: bool = False
    alpaca_enabled: bool = False
    webull_enabled: bool = False


class RuntimeOperationsPayload(BaseModel):
    use_simulated_live_market_data: bool = False
    external_market_data_enabled: bool = False
    historical_replay_enabled: bool = True


class ScannerSettingsPayload(BaseModel):
    min_price: float = 2.0
    max_price: float = 20.0
    max_float_millions: float = 20.0
    min_avg_volume: int = 0
    max_market_cap_millions: float = 1000.0
    exclude_halted: bool = True


class BacktestRunPayload(BaseModel):
    strategy_name: str
    data_source: str = "Alpaca Historical Data"
    mode: str = "Simple Replay"
    anchor_days_old: int = 4
    simulation_days: int = 30
    starting_capital: float = 5000.0
    settlement_days: int = 1
    account_type: str = "Cash Account"
    replay_speed: str = "Instant"

