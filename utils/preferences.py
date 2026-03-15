from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from config.settings import settings
from core.strategy_engine.catalog import (
    apply_risk_tolerance,
    build_default_strategy_configuration,
    build_default_workspace_preferences,
    classify_risk_profile,
    derive_runtime_risk_limits,
    get_risk_profiles,
    get_strategy_catalog,
    get_strategy_definition,
)
from database.models import StrategyConfiguration, UserPreference
from database.session import SessionLocal


WORKSPACE_PREFERENCE_KEY = "workspace_preferences"
API_CREDENTIALS_KEY = "api_credentials"
RUNTIME_OPERATIONS_KEY = "runtime_operations"
SCANNER_SETTINGS_KEY = "scanner_settings"


def ensure_strategy_defaults() -> None:
    with SessionLocal() as db:
        workspace_preference = db.scalar(
            select(UserPreference).where(UserPreference.preference_key == WORKSPACE_PREFERENCE_KEY)
        )
        if workspace_preference is None:
            workspace_preference = UserPreference(
                preference_key=WORKSPACE_PREFERENCE_KEY,
                value_json=build_default_workspace_preferences(),
            )
            db.add(workspace_preference)
            db.flush()

        risk_tolerance = int(workspace_preference.value_json.get("risk_tolerance", 50))

        for strategy in get_strategy_catalog():
            existing = db.scalar(
                select(StrategyConfiguration).where(
                    StrategyConfiguration.strategy_id == strategy["strategy_id"]
                )
            )
            if existing is None:
                db.add(StrategyConfiguration(**build_default_strategy_configuration(strategy["strategy_id"], risk_tolerance)))

        db.commit()

        _ensure_preference(
            db,
            API_CREDENTIALS_KEY,
            build_default_api_credentials(),
        )
        _ensure_preference(
            db,
            RUNTIME_OPERATIONS_KEY,
            build_default_runtime_operations(),
        )
        _ensure_preference(
            db,
            SCANNER_SETTINGS_KEY,
            build_default_scanner_settings(),
        )
        db.commit()


def _ensure_preference(db, preference_key: str, default_value: dict) -> UserPreference:
    preference = db.scalar(select(UserPreference).where(UserPreference.preference_key == preference_key))
    if preference is None:
        preference = UserPreference(preference_key=preference_key, value_json=default_value)
        db.add(preference)
        db.flush()
    return preference


def build_default_api_credentials() -> dict:
    return {
        "polygon_api_key": "",
        "alpaca_api_key": "",
        "alpaca_secret_key": "",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
        "webull_username": "",
        "webull_password": "",
        "polygon_enabled": False,
        "alpaca_enabled": False,
        "webull_enabled": False,
    }


def build_default_runtime_operations() -> dict:
    return {
        "use_simulated_live_market_data": False,
        "external_market_data_enabled": False,
        "historical_replay_enabled": True,
    }


def build_default_scanner_settings() -> dict:
    return {
        "min_price": 2.0,
        "max_price": 20.0,
        "max_float_millions": 20.0,
        "min_avg_volume": 0,
        "max_market_cap_millions": 1000.0,
        "exclude_halted": True,
    }


def get_workspace_preferences() -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        workspace_preference = db.scalar(
            select(UserPreference).where(UserPreference.preference_key == WORKSPACE_PREFERENCE_KEY)
        )
        preferences = workspace_preference.value_json if workspace_preference else build_default_workspace_preferences()
    preferences = jsonable_encoder(preferences)
    preferences["selected_profile"] = classify_risk_profile(int(preferences.get("risk_tolerance", 50)))
    return preferences


def get_api_credentials() -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = db.scalar(select(UserPreference).where(UserPreference.preference_key == API_CREDENTIALS_KEY))
        credentials = preference.value_json if preference else build_default_api_credentials()
    return jsonable_encoder(credentials)


def get_runtime_operations() -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = db.scalar(select(UserPreference).where(UserPreference.preference_key == RUNTIME_OPERATIONS_KEY))
        runtime_operations = preference.value_json if preference else build_default_runtime_operations()
    return jsonable_encoder(runtime_operations)


def get_scanner_settings() -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = db.scalar(select(UserPreference).where(UserPreference.preference_key == SCANNER_SETTINGS_KEY))
        scanner_settings = preference.value_json if preference else build_default_scanner_settings()
    return jsonable_encoder(scanner_settings)


def get_strategy_control_center() -> dict:
    ensure_strategy_defaults()
    workspace_preferences = get_workspace_preferences()

    with SessionLocal() as db:
        rows = db.scalars(select(StrategyConfiguration).order_by(StrategyConfiguration.display_name)).all()

    configuration_map = {row.strategy_id: row for row in rows}
    strategies = []
    for definition in get_strategy_catalog():
        config = configuration_map.get(definition["strategy_id"])
        if config is None:
            continue
        strategies.append(
            {
                **definition,
                "configuration": jsonable_encoder(
                    {
                        "strategy_id": config.strategy_id,
                        "display_name": config.display_name,
                        "enabled": config.enabled,
                        "experience_mode": config.experience_mode,
                        "timeframe": config.timeframe,
                        "capital_allocation_pct": config.capital_allocation_pct,
                        "risk_tolerance": config.risk_tolerance,
                        "parameters_json": config.parameters_json,
                        "updated_at": config.updated_at,
                    }
                ),
            }
        )

    return {
        "workspace_preferences": workspace_preferences,
        "runtime_operations": get_runtime_operations(),
        "scanner_settings": get_scanner_settings(),
        "risk_profiles": get_risk_profiles(),
        "strategies": strategies,
    }


def update_workspace_preferences(payload: dict) -> dict:
    ensure_strategy_defaults()

    with SessionLocal() as db:
        preference = db.scalar(
            select(UserPreference).where(UserPreference.preference_key == WORKSPACE_PREFERENCE_KEY)
        )
        if preference is None:
            preference = UserPreference(
                preference_key=WORKSPACE_PREFERENCE_KEY,
                value_json=build_default_workspace_preferences(),
            )
            db.add(preference)
            db.flush()

        next_value = {**build_default_workspace_preferences(), **preference.value_json, **payload}
        next_value["selected_profile"] = classify_risk_profile(int(next_value.get("risk_tolerance", 50)))
        preference.value_json = next_value

        if next_value.get("auto_apply_to_strategies", True):
            risk_tolerance = int(next_value.get("risk_tolerance", 50))
            experience_mode = next_value.get("experience_mode", "guided")
            for strategy in db.scalars(select(StrategyConfiguration)).all():
                definition = get_strategy_definition(strategy.strategy_id)
                strategy.risk_tolerance = risk_tolerance
                strategy.experience_mode = experience_mode
                strategy.parameters_json = apply_risk_tolerance(
                    definition["default_parameters"], risk_tolerance
                )
        db.commit()

    return get_workspace_preferences()


def update_api_credentials(payload: dict) -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = _ensure_preference(db, API_CREDENTIALS_KEY, build_default_api_credentials())
        preference.value_json = {**build_default_api_credentials(), **preference.value_json, **payload}
        db.commit()
    return get_api_credentials()


def update_runtime_operations(payload: dict) -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = _ensure_preference(db, RUNTIME_OPERATIONS_KEY, build_default_runtime_operations())
        preference.value_json = {**build_default_runtime_operations(), **preference.value_json, **payload}
        db.commit()
    return get_runtime_operations()


def update_scanner_settings(payload: dict) -> dict:
    ensure_strategy_defaults()
    with SessionLocal() as db:
        preference = _ensure_preference(db, SCANNER_SETTINGS_KEY, build_default_scanner_settings())
        preference.value_json = {**build_default_scanner_settings(), **preference.value_json, **payload}
        db.commit()
    return get_scanner_settings()


def update_strategy_configuration(strategy_id: str, payload: dict) -> dict:
    ensure_strategy_defaults()
    definition = get_strategy_definition(strategy_id)

    with SessionLocal() as db:
        config = db.scalar(
            select(StrategyConfiguration).where(StrategyConfiguration.strategy_id == strategy_id)
        )
        if config is None:
            config = StrategyConfiguration(**build_default_strategy_configuration(strategy_id))
            db.add(config)
            db.flush()

        config.display_name = payload.get("display_name", definition["name"])
        config.enabled = bool(payload.get("enabled", config.enabled))
        config.experience_mode = payload.get("experience_mode", config.experience_mode)
        config.timeframe = payload.get("timeframe", config.timeframe)
        config.capital_allocation_pct = float(
            payload.get("capital_allocation_pct", config.capital_allocation_pct)
        )
        config.risk_tolerance = int(payload.get("risk_tolerance", config.risk_tolerance))
        config.parameters_json = payload.get("parameters_json", config.parameters_json)
        db.commit()
        db.refresh(config)

        result = {
            "strategy_id": config.strategy_id,
            "display_name": config.display_name,
            "enabled": config.enabled,
            "experience_mode": config.experience_mode,
            "timeframe": config.timeframe,
            "capital_allocation_pct": config.capital_allocation_pct,
            "risk_tolerance": config.risk_tolerance,
            "parameters_json": config.parameters_json,
            "updated_at": config.updated_at,
        }

    return jsonable_encoder(result)


def get_runtime_risk_limits() -> dict:
    workspace_preferences = get_workspace_preferences()
    return derive_runtime_risk_limits(
        {
            "max_capital_per_trade": settings.max_capital_per_trade,
            "max_open_positions": settings.max_open_positions,
            "max_daily_loss": settings.max_daily_loss,
        },
        int(workspace_preferences.get("risk_tolerance", 50)),
    )


def get_connection_status_summary() -> dict:
    credentials = get_api_credentials()
    runtime_operations = get_runtime_operations()
    return {
        "polygon": {
            "enabled": credentials.get("polygon_enabled", False),
            "configured": bool(credentials.get("polygon_api_key")),
        },
        "alpaca": {
            "enabled": credentials.get("alpaca_enabled", False),
            "configured": bool(credentials.get("alpaca_api_key") and credentials.get("alpaca_secret_key")),
            "base_url": credentials.get("alpaca_base_url"),
        },
        "webull": {
            "enabled": credentials.get("webull_enabled", False),
            "configured": bool(credentials.get("webull_username") and credentials.get("webull_password")),
        },
        "runtime_operations": runtime_operations,
    }

