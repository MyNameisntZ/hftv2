from __future__ import annotations

from copy import deepcopy


STRATEGY_CATALOG = [
    {
        "strategy_id": "vwap_strategy",
        "name": "VWAP Strategy",
        "description": "Intraday VWAP continuation setup with momentum confirmation.",
        "default_timeframe": "1m",
        "default_allocation_pct": 25.0,
        "parameter_schema": [
            {
                "key": "min_price",
                "label": "Min Price",
                "type": "number",
                "min": 1,
                "max": 100,
                "step": 0.1,
                "group": "filters",
                "description": "Only evaluate symbols above this price.",
            },
            {
                "key": "max_price",
                "label": "Max Price",
                "type": "number",
                "min": 1,
                "max": 100,
                "step": 0.1,
                "group": "filters",
                "description": "Only evaluate symbols below this price.",
            },
            {
                "key": "min_volume",
                "label": "Min Volume",
                "type": "number",
                "min": 10000,
                "max": 5000000,
                "step": 10000,
                "group": "filters",
                "description": "Minimum intraday volume needed before entry.",
            },
            {
                "key": "vwap_deviation_bps",
                "label": "VWAP Deviation Bps",
                "type": "number",
                "min": 1,
                "max": 150,
                "step": 1,
                "group": "signal",
                "description": "How far price can stretch from VWAP before qualifying.",
            },
            {
                "key": "confidence_threshold",
                "label": "Confidence Threshold",
                "type": "number",
                "min": 0.3,
                "max": 0.95,
                "step": 0.01,
                "group": "signal",
                "description": "Minimum score required to emit a trade intent.",
            },
            {
                "key": "stop_loss_pct",
                "label": "Stop Loss %",
                "type": "number",
                "min": 0.2,
                "max": 10,
                "step": 0.1,
                "group": "risk",
                "description": "Percent stop distance from entry.",
            },
            {
                "key": "take_profit_pct",
                "label": "Take Profit %",
                "type": "number",
                "min": 0.5,
                "max": 20,
                "step": 0.1,
                "group": "risk",
                "description": "Percent target distance from entry.",
            },
        ],
        "default_parameters": {
            "min_price": 2.0,
            "max_price": 20.0,
            "min_volume": 300000,
            "vwap_deviation_bps": 18,
            "confidence_threshold": 0.64,
            "stop_loss_pct": 3.0,
            "take_profit_pct": 5.0,
        },
    },
    {
        "strategy_id": "rsi_strategy",
        "name": "RSI Strategy",
        "description": "Short-term RSI mean reversion with liquidity and confirmation filters.",
        "default_timeframe": "5m",
        "default_allocation_pct": 15.0,
        "parameter_schema": [
            {
                "key": "lookback_period",
                "label": "RSI Lookback",
                "type": "number",
                "min": 2,
                "max": 50,
                "step": 1,
                "group": "signal",
                "description": "Number of bars used to calculate RSI.",
            },
            {
                "key": "oversold",
                "label": "Oversold",
                "type": "number",
                "min": 5,
                "max": 50,
                "step": 1,
                "group": "signal",
                "description": "RSI level that triggers long bias.",
            },
            {
                "key": "overbought",
                "label": "Overbought",
                "type": "number",
                "min": 50,
                "max": 95,
                "step": 1,
                "group": "signal",
                "description": "RSI level that triggers short bias.",
            },
            {
                "key": "min_relative_volume",
                "label": "Min Relative Volume",
                "type": "number",
                "min": 0.5,
                "max": 10,
                "step": 0.1,
                "group": "filters",
                "description": "Relative volume requirement before entry.",
            },
            {
                "key": "confidence_threshold",
                "label": "Confidence Threshold",
                "type": "number",
                "min": 0.3,
                "max": 0.95,
                "step": 0.01,
                "group": "signal",
                "description": "Minimum confidence required for signal publication.",
            },
            {
                "key": "stop_loss_pct",
                "label": "Stop Loss %",
                "type": "number",
                "min": 0.2,
                "max": 10,
                "step": 0.1,
                "group": "risk",
                "description": "Percent stop distance from entry.",
            },
            {
                "key": "take_profit_pct",
                "label": "Take Profit %",
                "type": "number",
                "min": 0.5,
                "max": 20,
                "step": 0.1,
                "group": "risk",
                "description": "Percent target distance from entry.",
            },
        ],
        "default_parameters": {
            "lookback_period": 14,
            "oversold": 28,
            "overbought": 72,
            "min_relative_volume": 1.5,
            "confidence_threshold": 0.61,
            "stop_loss_pct": 2.4,
            "take_profit_pct": 4.2,
        },
    },
    {
        "strategy_id": "bull_flag_breakout",
        "name": "Bull Flag Breakout",
        "description": "Momentum breakout setup focused on high-quality intraday flag patterns.",
        "default_timeframe": "1m",
        "default_allocation_pct": 20.0,
        "parameter_schema": [
            {
                "key": "flagpole_min_pct",
                "label": "Flagpole Min %",
                "type": "number",
                "min": 1,
                "max": 30,
                "step": 0.1,
                "group": "signal",
                "description": "Minimum initial impulse before flag formation.",
            },
            {
                "key": "pullback_max_pct",
                "label": "Pullback Max %",
                "type": "number",
                "min": 0.5,
                "max": 15,
                "step": 0.1,
                "group": "signal",
                "description": "Largest acceptable retracement during consolidation.",
            },
            {
                "key": "breakout_buffer_pct",
                "label": "Breakout Buffer %",
                "type": "number",
                "min": 0.05,
                "max": 5,
                "step": 0.05,
                "group": "signal",
                "description": "Extra clearance above the flag high before triggering entry.",
            },
            {
                "key": "volume_spike_ratio",
                "label": "Volume Spike Ratio",
                "type": "number",
                "min": 1,
                "max": 10,
                "step": 0.1,
                "group": "filters",
                "description": "Required surge vs baseline volume on breakout.",
            },
            {
                "key": "confidence_threshold",
                "label": "Confidence Threshold",
                "type": "number",
                "min": 0.3,
                "max": 0.95,
                "step": 0.01,
                "group": "signal",
                "description": "Minimum score required to emit a trade intent.",
            },
            {
                "key": "stop_loss_pct",
                "label": "Stop Loss %",
                "type": "number",
                "min": 0.2,
                "max": 10,
                "step": 0.1,
                "group": "risk",
                "description": "Percent stop distance from entry.",
            },
            {
                "key": "take_profit_pct",
                "label": "Take Profit %",
                "type": "number",
                "min": 0.5,
                "max": 20,
                "step": 0.1,
                "group": "risk",
                "description": "Percent target distance from entry.",
            },
        ],
        "default_parameters": {
            "flagpole_min_pct": 6.0,
            "pullback_max_pct": 2.2,
            "breakout_buffer_pct": 0.35,
            "volume_spike_ratio": 2.0,
            "confidence_threshold": 0.67,
            "stop_loss_pct": 2.7,
            "take_profit_pct": 6.5,
        },
    },
]


RISK_PROFILE_PRESETS = [
    {
        "profile_id": "conservative",
        "name": "Conservative",
        "risk_tolerance": 25,
        "description": "Smaller sizing, stricter confidence, tighter downside control.",
    },
    {
        "profile_id": "balanced",
        "name": "Balanced",
        "risk_tolerance": 50,
        "description": "Moderate position sizing with standard trade qualification.",
    },
    {
        "profile_id": "aggressive",
        "name": "Aggressive",
        "risk_tolerance": 80,
        "description": "Larger sizing and looser thresholds for more signal frequency.",
    },
]


def get_strategy_definition(strategy_id: str) -> dict:
    for strategy in STRATEGY_CATALOG:
        if strategy["strategy_id"] == strategy_id:
            return deepcopy(strategy)
    raise KeyError(f"Unknown strategy '{strategy_id}'")


def get_strategy_catalog() -> list[dict]:
    return [deepcopy(strategy) for strategy in STRATEGY_CATALOG]


def get_risk_profiles() -> list[dict]:
    return [deepcopy(profile) for profile in RISK_PROFILE_PRESETS]


def classify_risk_profile(risk_tolerance: int) -> str:
    if risk_tolerance <= 33:
        return "conservative"
    if risk_tolerance >= 67:
        return "aggressive"
    return "balanced"


def apply_risk_tolerance(default_parameters: dict, risk_tolerance: int) -> dict:
    profile_scale = 0.8 + (risk_tolerance / 100) * 0.6
    confidence_shift = (50 - risk_tolerance) / 250
    parameters = deepcopy(default_parameters)

    if "stop_loss_pct" in parameters:
        parameters["stop_loss_pct"] = round(parameters["stop_loss_pct"] * profile_scale, 2)
    if "take_profit_pct" in parameters:
        parameters["take_profit_pct"] = round(parameters["take_profit_pct"] * (0.9 + risk_tolerance / 100 * 0.7), 2)
    if "confidence_threshold" in parameters:
        adjusted = parameters["confidence_threshold"] + confidence_shift
        parameters["confidence_threshold"] = round(max(0.35, min(0.9, adjusted)), 2)
    return parameters


def build_default_workspace_preferences() -> dict:
    return {
        "experience_mode": "guided",
        "risk_tolerance": 50,
        "selected_profile": "balanced",
        "auto_apply_to_strategies": True,
        "kill_switch": False,
        "require_confirmation": True,
    }


def build_default_strategy_configuration(strategy_id: str, risk_tolerance: int = 50) -> dict:
    strategy = get_strategy_definition(strategy_id)
    return {
        "strategy_id": strategy["strategy_id"],
        "display_name": strategy["name"],
        "enabled": strategy["strategy_id"] != "rsi_strategy",
        "experience_mode": "guided",
        "timeframe": strategy["default_timeframe"],
        "capital_allocation_pct": strategy["default_allocation_pct"],
        "risk_tolerance": risk_tolerance,
        "parameters_json": apply_risk_tolerance(strategy["default_parameters"], risk_tolerance),
    }


def derive_runtime_risk_limits(base_limits: dict, risk_tolerance: int) -> dict:
    exposure_scale = 0.6 + (risk_tolerance / 100) * 0.8
    daily_scale = 0.65 + (risk_tolerance / 100) * 0.9
    return {
        "max_capital_per_trade": round(base_limits["max_capital_per_trade"] * exposure_scale, 2),
        "max_open_positions": max(1, int(round(base_limits["max_open_positions"] * exposure_scale))),
        "max_daily_loss": round(base_limits["max_daily_loss"] * daily_scale, 2),
        "risk_tolerance": risk_tolerance,
        "selected_profile": classify_risk_profile(risk_tolerance),
    }

