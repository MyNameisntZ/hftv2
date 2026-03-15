from __future__ import annotations

from sqlalchemy import func, select

from database.models import PositionState, TradeIntent
from database.session import SessionLocal
from utils.preferences import get_runtime_risk_limits
from utils.schemas import EventMessage

from core.service_base import EngineService


class RiskEngineService(EngineService):
    service_name = "risk_engine"
    subscriptions = ("TRADE_INTENT",)

    async def handle_event(self, event: EventMessage) -> None:
        if not event.symbol:
            return

        runtime_limits = get_runtime_risk_limits()

        with SessionLocal() as db:
            open_positions = db.scalar(select(func.count()).select_from(PositionState)) or 0
            latest_intent = db.scalar(
                select(TradeIntent).where(TradeIntent.symbol == event.symbol).order_by(TradeIntent.id.desc())
            )

            approved = open_positions < runtime_limits["max_open_positions"]
            reason = "approved" if approved else "max_open_positions_exceeded"

            if latest_intent:
                latest_intent.status = "approved" if approved else "rejected"
            db.commit()

        event_type = "TRADE_APPROVED" if approved else "TRADE_REJECTED"
        await self.publish(
            event_type,
            {
                **event.payload,
                "risk_reason": reason,
                "max_open_positions": runtime_limits["max_open_positions"],
                "max_capital_per_trade": runtime_limits["max_capital_per_trade"],
                "max_daily_loss": runtime_limits["max_daily_loss"],
                "risk_tolerance": runtime_limits["risk_tolerance"],
            },
            symbol=event.symbol,
        )
        self._metrics["approvals"] = self._metrics.get("approvals", 0) + int(approved)
        self._metrics["rejections"] = self._metrics.get("rejections", 0) + int(not approved)
        self._message = f"{event_type.lower()} for {event.symbol}"

