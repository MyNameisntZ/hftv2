from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, func, select

from core.orchestrator import PlatformOrchestrator
from database.models import (
    AnalyticsSnapshot,
    OrderState,
    PositionState,
    ServiceHeartbeat,
    SystemEvent,
    SystemSnapshot,
    TickData,
    TradeIntent,
)
from database.session import SessionLocal


def build_system_overview(orchestrator: PlatformOrchestrator) -> dict:
    statuses = orchestrator.statuses()

    with SessionLocal() as db:
        latest_event = db.scalar(select(SystemEvent).order_by(desc(SystemEvent.id)))
        latest_analytics = db.scalar(
            select(AnalyticsSnapshot).where(AnalyticsSnapshot.snapshot_type == "system_metrics").order_by(
                desc(AnalyticsSnapshot.id)
            )
        )
        heartbeats = db.scalars(select(ServiceHeartbeat).order_by(ServiceHeartbeat.service_name)).all()

        overview = {
            "status": "ok" if all(status.healthy for status in statuses) else "degraded",
            "event_bus_backend": orchestrator.event_bus.__class__.__name__,
            "engine_count": len(statuses),
            "healthy_engines": sum(1 for status in statuses if status.healthy),
            "database": {
                "ticks": db.scalar(select(func.count()).select_from(TickData)) or 0,
                "trade_intents": db.scalar(select(func.count()).select_from(TradeIntent)) or 0,
                "orders": db.scalar(select(func.count()).select_from(OrderState)) or 0,
                "positions": db.scalar(select(func.count()).select_from(PositionState)) or 0,
                "events": db.scalar(select(func.count()).select_from(SystemEvent)) or 0,
            },
            "latest_event": None
            if latest_event is None
            else {
                "event_type": latest_event.event_type,
                "source": latest_event.source,
                "symbol": latest_event.symbol,
                "created_at": latest_event.created_at,
            },
            "analytics": latest_analytics.payload if latest_analytics else {},
            "heartbeats": [
                {
                    "service_name": item.service_name,
                    "status": item.status,
                    "message": item.message,
                    "last_seen": item.last_seen,
                }
                for item in heartbeats
            ],
            "engines": [status.model_dump(mode="json") for status in statuses],
        }
        overview = jsonable_encoder(overview)

        db.add(SystemSnapshot(snapshot_type="overview", status=overview["status"], payload=overview))
        db.commit()

    return overview

