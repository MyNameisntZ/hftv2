from __future__ import annotations

from sqlalchemy import select

from core.strategy_engine.catalog import get_strategy_catalog
from database.models import StrategyConfiguration, TradeIntent
from database.session import SessionLocal
from utils.schemas import EventMessage

from core.service_base import EngineService


class StrategyEngineService(EngineService):
    service_name = "strategy_engine"
    subscriptions = ("SYMBOL_UNIVERSE_UPDATE",)

    async def handle_event(self, event: EventMessage) -> None:
        price = float(event.payload.get("price", 0))
        if not event.symbol:
            return

        intents_to_publish: list[dict] = []
        with SessionLocal() as db:
            configurations = {
                row.strategy_id: row
                for row in db.scalars(select(StrategyConfiguration)).all()
            }
            enabled_count = sum(1 for row in configurations.values() if row.enabled)

            intents_emitted = 0
            for definition in get_strategy_catalog():
                configuration = configurations.get(definition["strategy_id"])
                if configuration is None or not configuration.enabled:
                    continue

                params = configuration.parameters_json
                min_price = float(params.get("min_price", 0))
                max_price = float(params.get("max_price", 1_000_000))
                if not (min_price <= price <= max_price):
                    continue

                confidence_threshold = float(params.get("confidence_threshold", 0.6))
                volume_floor = float(params.get("min_volume", params.get("min_relative_volume", 0)))
                base_confidence = 0.58 + min(max((price - min_price) / max(max_price - min_price, 1), 0), 0.18)
                volume_bonus = 0.05 if volume_floor else 0.0
                confidence = round(min(0.95, base_confidence + volume_bonus), 2)
                if confidence < confidence_threshold:
                    continue

                stop_loss_pct = float(params.get("stop_loss_pct", 3.0)) / 100
                take_profit_pct = float(params.get("take_profit_pct", 5.0)) / 100
                intent_payload = {
                    "strategy_id": configuration.strategy_id,
                    "strategy_name": configuration.display_name,
                    "side": "BUY",
                    "entry_price": price,
                    "stop": round(price * (1 - stop_loss_pct), 2),
                    "target": round(price * (1 + take_profit_pct), 2),
                    "confidence": confidence,
                    "risk_tolerance": configuration.risk_tolerance,
                    "timeframe": configuration.timeframe,
                    "parameters": params,
                }

                db.add(
                    TradeIntent(
                        strategy_id=intent_payload["strategy_id"],
                        symbol=event.symbol,
                        side=intent_payload["side"],
                        entry_price=intent_payload["entry_price"],
                        stop_price=intent_payload["stop"],
                        target_price=intent_payload["target"],
                        confidence=confidence,
                        status="pending_risk_review",
                        metadata_json={
                            "source_event_id": event.event_id,
                            "parameters": params,
                            "strategy_name": configuration.display_name,
                            "timeframe": configuration.timeframe,
                            "risk_tolerance": configuration.risk_tolerance,
                        },
                    )
                )
                intents_to_publish.append(intent_payload)

            db.commit()

        for intent_payload in intents_to_publish:
            await self.publish("TRADE_INTENT", intent_payload, symbol=event.symbol)
            intents_emitted += 1

        self._metrics["intents_emitted"] = self._metrics.get("intents_emitted", 0) + intents_emitted
        self._metrics["active_strategies"] = enabled_count
        self._message = (
            f"generated {intents_emitted} intents for {event.symbol}"
            if intents_emitted
            else f"no strategy qualified for {event.symbol}"
        )

