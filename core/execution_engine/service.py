from __future__ import annotations

from database.models import OrderState, PositionState
from database.session import SessionLocal
from utils.schemas import EventMessage

from core.service_base import EngineService


class ExecutionEngineService(EngineService):
    service_name = "execution_engine"
    subscriptions = ("TRADE_APPROVED",)

    async def handle_event(self, event: EventMessage) -> None:
        if not event.symbol:
            return

        quantity = 100
        price = float(event.payload["entry_price"])

        with SessionLocal() as db:
            db.add(
                OrderState(
                    broker_order_id=f"paper-{event.event_id[:8]}",
                    symbol=event.symbol,
                    side=event.payload["side"],
                    quantity=quantity,
                    order_type="market",
                    status="filled",
                    price=price,
                    strategy_id=event.payload["strategy_id"],
                )
            )

            position = db.query(PositionState).filter(PositionState.symbol == event.symbol).one_or_none()
            if position is None:
                position = PositionState(
                    symbol=event.symbol,
                    quantity=quantity,
                    average_price=price,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                )
                db.add(position)
            else:
                position.quantity += quantity
                position.average_price = price
            db.commit()

        await self.publish(
            "ORDER_UPDATE",
            {"status": "filled", "quantity": quantity, "price": price},
            symbol=event.symbol,
        )
        await self.publish(
            "POSITION_UPDATE",
            {"quantity": quantity, "average_price": price},
            symbol=event.symbol,
        )
        await self.publish(
            "FILL_UPDATE",
            {"fill_price": price, "fill_quantity": quantity},
            symbol=event.symbol,
        )
        self._metrics["orders_sent"] = self._metrics.get("orders_sent", 0) + 1
        self._message = f"filled paper order for {event.symbol}"

