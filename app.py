from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from sqlalchemy import desc, select

from adapters.brokers.alpaca.client import AlpacaBrokerAdapter
from adapters.data_providers.polygon_massive.client import PolygonMassiveAdapter
from config.logging import configure_logging
from config.settings import settings
from core.orchestrator import PlatformOrchestrator
from core.backtest_engine.simulator import run_accelerated_backtest
from database.init_db import init_db
from database.models import (
    AnalyticsSnapshot,
    BacktestRun,
    OrderState,
    PositionState,
    ServiceHeartbeat,
    SystemEvent,
    TradeIntent,
    UserPreference,
)
from database.session import SessionLocal
from utils.preferences import (
    SCANNER_SETTINGS_KEY,
    get_api_credentials,
    get_connection_status_summary,
    get_runtime_risk_limits,
    get_runtime_operations,
    get_scanner_settings,
    get_strategy_control_center,
    get_workspace_preferences,
    update_api_credentials,
    update_runtime_operations,
    update_scanner_settings,
    update_strategy_configuration,
    update_workspace_preferences,
)
from utils.schemas import (
    ApiCredentialSettingsPayload,
    BacktestRunPayload,
    RuntimeOperationsPayload,
    ScannerSettingsPayload,
    StrategyConfigurationPayload,
    WorkspacePreferencePayload,
)
from utils.runtime_version import get_runtime_version
from utils.system_monitor import build_system_overview


orchestrator = PlatformOrchestrator()
HEALTH_DASHBOARD_PATH = Path(__file__).resolve().parent / "gui" / "system_health_dashboard.html"


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    await orchestrator.start()
    try:
        yield
    finally:
        await orchestrator.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
polygon_adapter = PolygonMassiveAdapter()
alpaca_adapter = AlpacaBrokerAdapter()


def _tail_lines(file_path: Path, limit: int = 200) -> list[str]:
    if not file_path.exists():
        return []
    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]


@app.get("/", include_in_schema=False)
async def root_dashboard() -> FileResponse:
    return FileResponse(HEALTH_DASHBOARD_PATH)


@app.get("/dashboard/health", include_in_schema=False)
async def health_dashboard() -> FileResponse:
    return FileResponse(HEALTH_DASHBOARD_PATH)


@app.get("/health")
async def health() -> dict:
    statuses = orchestrator.statuses()
    return {
        "status": "ok" if all(status.healthy for status in statuses) else "degraded",
        "environment": settings.app_env,
        "engines": [status.model_dump() for status in statuses],
    }


@app.get("/system/runtime-version")
async def runtime_version() -> dict:
    return get_runtime_version()


@app.get("/system/overview")
async def system_overview() -> dict:
    return build_system_overview(orchestrator)


@app.get("/system/status")
async def system_status() -> dict:
    with SessionLocal() as db:
        heartbeats = db.scalars(select(ServiceHeartbeat).order_by(ServiceHeartbeat.service_name)).all()
    return {
        "app_name": settings.app_name,
        "event_bus_backend": orchestrator.event_bus.__class__.__name__,
        "services": [
            {
                "service_name": item.service_name,
                "status": item.status,
                "message": item.message,
                "last_seen": item.last_seen,
            }
            for item in heartbeats
        ],
    }


@app.get("/system/engines")
async def list_engines() -> dict:
    return {"engines": [status.model_dump(mode="json") for status in orchestrator.statuses()]}


@app.post("/system/engines/{engine_name}/start")
async def start_engine(engine_name: str) -> dict:
    try:
        await orchestrator.start_engines([engine_name])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "engine": engine_name,
        "action": "start",
        "status": orchestrator.get_engine(engine_name).status().model_dump(mode="json"),
    }


@app.post("/system/engines/{engine_name}/stop")
async def stop_engine(engine_name: str) -> dict:
    try:
        await orchestrator.stop_engines([engine_name])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "engine": engine_name,
        "action": "stop",
        "status": orchestrator.get_engine(engine_name).status().model_dump(mode="json"),
    }


@app.post("/system/engines/{engine_name}/restart")
async def restart_engine(engine_name: str) -> dict:
    try:
        await orchestrator.restart_engine(engine_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "engine": engine_name,
        "action": "restart",
        "status": orchestrator.get_engine(engine_name).status().model_dump(mode="json"),
    }


@app.get("/system/events/recent")
async def recent_events(limit: int = 50) -> dict:
    with SessionLocal() as db:
        events = db.scalars(select(SystemEvent).order_by(desc(SystemEvent.id)).limit(limit)).all()
    return {
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "source": event.source,
                "symbol": event.symbol,
                "payload": event.payload,
                "created_at": event.created_at,
            }
            for event in events
        ]
    }


@app.get("/system/logs")
async def system_logs(limit: int = 200) -> dict:
    log_file = settings.logs_dir / "platform.log"
    return {
        "path": str(log_file),
        "lines": _tail_lines(log_file, limit=max(1, min(limit, 500))),
    }


@app.get("/runtime/config")
async def runtime_config() -> dict:
    workspace_preferences = get_workspace_preferences()
    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "event_bus_backend": settings.event_bus_backend,
        "simulate_market_data": settings.simulate_market_data,
        "risk_limits": get_runtime_risk_limits(),
        "workspace_preferences": workspace_preferences,
        "runtime_operations": get_runtime_operations(),
        "connection_status": get_connection_status_summary(),
    }


@app.get("/strategies/control-center")
async def strategies_control_center() -> dict:
    return get_strategy_control_center()


@app.put("/strategies/configurations/{strategy_id}")
async def save_strategy_configuration(
    strategy_id: str, payload: StrategyConfigurationPayload
) -> dict:
    try:
        configuration = update_strategy_configuration(strategy_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"configuration": configuration}


@app.put("/strategies/workspace-preferences")
async def save_workspace_preferences(payload: WorkspacePreferencePayload) -> dict:
    preferences = update_workspace_preferences(payload.model_dump())
    return {"workspace_preferences": preferences}


@app.get("/connections/api-settings")
async def connection_api_settings() -> dict:
    return {
        "credentials": get_api_credentials(),
        "status": get_connection_status_summary(),
    }


@app.put("/connections/api-settings")
async def save_connection_api_settings(payload: ApiCredentialSettingsPayload) -> dict:
    credentials = update_api_credentials(payload.model_dump())
    return {
        "credentials": credentials,
        "status": get_connection_status_summary(),
    }


@app.post("/connections/test/polygon")
async def test_polygon_connection() -> dict:
    credentials = get_api_credentials()
    result = await polygon_adapter.test_connection(credentials.get("polygon_api_key", ""))
    return {"result": result}


@app.post("/connections/test/alpaca")
async def test_alpaca_connection() -> dict:
    credentials = get_api_credentials()
    result = await alpaca_adapter.test_connection(
        credentials.get("alpaca_api_key", ""),
        credentials.get("alpaca_secret_key", ""),
        credentials.get("alpaca_base_url", ""),
    )
    return {"result": result}


@app.get("/runtime/operations")
async def runtime_operations() -> dict:
    return {"runtime_operations": get_runtime_operations()}


@app.put("/runtime/operations")
async def save_runtime_operations(payload: RuntimeOperationsPayload) -> dict:
    runtime_operations = update_runtime_operations(payload.model_dump())
    return {
        "runtime_operations": runtime_operations,
        "status": get_connection_status_summary(),
    }


@app.get("/scanner/universe")
async def scanner_universe(limit: int = 25) -> dict:
    with SessionLocal() as db:
        scanner_preference = db.scalar(
            select(UserPreference).where(UserPreference.preference_key == SCANNER_SETTINGS_KEY)
        )
        scanner_settings_updated_at = None if scanner_preference is None else scanner_preference.updated_at
        statement = (
            select(SystemEvent)
            .where(SystemEvent.event_type == "SYMBOL_UNIVERSE_UPDATE")
            .order_by(desc(SystemEvent.id))
        )
        if scanner_settings_updated_at is not None:
            statement = statement.where(SystemEvent.created_at >= scanner_settings_updated_at)
        events = db.scalars(statement).all()

    latest_by_symbol: dict[str, SystemEvent] = {}
    for event in events:
        if event.symbol and event.symbol not in latest_by_symbol:
            latest_by_symbol[event.symbol] = event

    filtered_events = list(latest_by_symbol.values())[:limit]
    return {
        "settings": get_scanner_settings(),
        "symbols": jsonable_encoder(
            [
                {
                    "symbol": event.symbol,
                    "scanner_mode": event.payload.get("scanner_mode"),
                    "reason": event.payload.get("reason"),
                    "price": event.payload.get("price"),
                    "float_millions": event.payload.get("float_millions"),
                    "avg_volume": event.payload.get("avg_volume"),
                    "market_cap_millions": event.payload.get("market_cap_millions"),
                    "is_halted": event.payload.get("is_halted"),
                    "created_at": event.created_at,
                }
                for event in filtered_events
            ]
        )
    }


@app.get("/scanner/settings")
async def scanner_settings() -> dict:
    return {"settings": get_scanner_settings()}


@app.put("/scanner/settings")
async def save_scanner_settings(payload: ScannerSettingsPayload) -> dict:
    return {"settings": update_scanner_settings(payload.model_dump())}


@app.get("/trading/intents")
async def trading_intents(limit: int = 50) -> dict:
    with SessionLocal() as db:
        intents = db.scalars(select(TradeIntent).order_by(desc(TradeIntent.id)).limit(limit)).all()
    return {
        "intents": jsonable_encoder(
            [
                {
                    "id": intent.id,
                    "strategy_id": intent.strategy_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "entry_price": intent.entry_price,
                    "stop_price": intent.stop_price,
                    "target_price": intent.target_price,
                    "confidence": intent.confidence,
                    "status": intent.status,
                    "created_at": intent.created_at,
                }
                for intent in intents
            ]
        )
    }


@app.get("/trading/orders")
async def trading_orders(limit: int = 50) -> dict:
    with SessionLocal() as db:
        orders = db.scalars(select(OrderState).order_by(desc(OrderState.id)).limit(limit)).all()
    return {
        "orders": jsonable_encoder(
            [
                {
                    "id": order.id,
                    "broker_order_id": order.broker_order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                    "order_type": order.order_type,
                    "status": order.status,
                    "price": order.price,
                    "strategy_id": order.strategy_id,
                    "updated_at": order.updated_at,
                }
                for order in orders
            ]
        )
    }


@app.get("/trading/positions")
async def trading_positions() -> dict:
    with SessionLocal() as db:
        positions = db.scalars(select(PositionState).order_by(PositionState.symbol)).all()
    return {
        "positions": jsonable_encoder(
            [
                {
                    "id": position.id,
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                    "updated_at": position.updated_at,
                }
                for position in positions
            ]
        )
    }


@app.get("/backtests/runs")
async def backtest_runs(limit: int = 25) -> dict:
    with SessionLocal() as db:
        runs = db.scalars(select(BacktestRun).order_by(desc(BacktestRun.id)).limit(limit)).all()
    return {
        "runs": jsonable_encoder(
            [
                {
                    "id": run.id,
                    "name": run.name,
                    "strategy_id": run.strategy_id,
                    "parameters": run.parameters,
                    "status": run.status,
                    "result_summary": run.result_summary,
                    "created_at": run.created_at,
                }
                for run in runs
            ]
        )
    }


@app.post("/backtests/run")
async def run_backtest(payload: BacktestRunPayload) -> dict:
    control_center = get_strategy_control_center()
    strategy_lookup = {
        strategy["name"]: strategy for strategy in control_center["strategies"]
    }
    strategy = strategy_lookup.get(payload.strategy_name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Unknown strategy '{payload.strategy_name}'")

    strategy_id = strategy["strategy_id"]
    strategy_config = strategy["configuration"]
    scanner_settings = get_scanner_settings()

    result_summary = run_accelerated_backtest(
        strategy_id=strategy_id,
        strategy_name=payload.strategy_name,
        base_parameters=strategy_config["parameters_json"],
        scanner_settings=scanner_settings,
        mode=payload.mode,
        anchor_days_old=payload.anchor_days_old,
        simulation_days=payload.simulation_days,
        starting_capital=payload.starting_capital,
        settlement_days=payload.settlement_days,
        account_type=payload.account_type,
        replay_speed=payload.replay_speed,
        data_source=payload.data_source,
    )

    with SessionLocal() as db:
        run = BacktestRun(
            name=f"{payload.strategy_name.lower().replace(' ', '_')}_{payload.simulation_days}d",
            strategy_id=strategy_id,
            parameters=payload.model_dump(),
            status="completed",
            result_summary=result_summary,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

    return {
        "run": jsonable_encoder(
            {
                "id": run.id,
                "name": run.name,
                "strategy_id": run.strategy_id,
                "parameters": run.parameters,
                "status": run.status,
                "result_summary": run.result_summary,
                "created_at": run.created_at,
            }
        )
    }


@app.get("/analytics/summary")
async def analytics_summary() -> dict:
    with SessionLocal() as db:
        snapshot = db.scalar(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.snapshot_type == "system_metrics")
            .order_by(desc(AnalyticsSnapshot.id))
        )
    return {
        "summary": jsonable_encoder(snapshot.payload if snapshot else {}),
        "updated_at": None if snapshot is None else snapshot.created_at,
    }


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()

    async def forward_event(event):
        await queue.put(event.model_dump(mode="json"))

    unsubscribe = orchestrator.event_bus.subscribe("*", forward_event)
    try:
        for event in orchestrator.event_bus.recent_events()[-20:]:
            await websocket.send_json(event.model_dump(mode="json"))

        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        return
    finally:
        unsubscribe()

