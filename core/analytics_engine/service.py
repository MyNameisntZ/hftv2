from __future__ import annotations

from sqlalchemy import func, select

from database.models import AnalyticsSnapshot, OrderState, PositionState, TradeIntent
from database.session import SessionLocal
from utils.schemas import EventMessage

from core.service_base import EngineService


class AnalyticsEngineService(EngineService):
    service_name = "analytics_engine"
    subscriptions = ("ORDER_UPDATE", "POSITION_UPDATE", "FILL_UPDATE")

    async def handle_event(self, event: EventMessage) -> None:
        with SessionLocal() as db:
            snapshot = {
                "orders": db.scalar(select(func.count()).select_from(OrderState)) or 0,
                "positions": db.scalar(select(func.count()).select_from(PositionState)) or 0,
                "trade_intents": db.scalar(select(func.count()).select_from(TradeIntent)) or 0,
            }
            db.add(AnalyticsSnapshot(snapshot_type="system_metrics", payload=snapshot))
            db.commit()

        self._metrics.update(snapshot)
        self._message = f"analytics updated from {event.event_type}"

