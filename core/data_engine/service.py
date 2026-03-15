from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from database.models import TickData, TickerMetadata
from database.session import SessionLocal
from utils.preferences import get_connection_status_summary
from utils.schemas import EventMessage

from core.service_base import EngineService


class DataEngineService(EngineService):
    service_name = "data_engine"

    def __init__(self, event_bus) -> None:
        super().__init__(event_bus)
        self._tick_counter = 0
        self._symbols = ["AAPL", "NVDA", "AMD", "PLTR"]
        self._symbol_metadata = {
            "AAPL": {
                "company_name": "Apple Inc.",
                "exchange": "NASDAQ",
                "float_shares": 15_500_000_000,
                "market_cap": 3_300_000_000_000,
                "avg_volume": 55_000_000,
                "is_halted": False,
            },
            "NVDA": {
                "company_name": "NVIDIA Corp.",
                "exchange": "NASDAQ",
                "float_shares": 24_000_000_000,
                "market_cap": 2_200_000_000_000,
                "avg_volume": 45_000_000,
                "is_halted": False,
            },
            "AMD": {
                "company_name": "Advanced Micro Devices",
                "exchange": "NASDAQ",
                "float_shares": 1_600_000_000,
                "market_cap": 280_000_000_000,
                "avg_volume": 48_000_000,
                "is_halted": False,
            },
            "PLTR": {
                "company_name": "Palantir Technologies",
                "exchange": "NASDAQ",
                "float_shares": 2_200_000_000,
                "market_cap": 65_000_000_000,
                "avg_volume": 75_000_000,
                "is_halted": False,
            },
        }

    async def on_start(self) -> None:
        await super().on_start()
        self._seed_metadata()

    async def run_cycle(self) -> None:
        connection_status = get_connection_status_summary()
        runtime_operations = connection_status["runtime_operations"]
        configured_providers = int(connection_status["polygon"]["configured"])

        self._metrics["connected_feeds"] = configured_providers
        self._metrics["cache_backend"] = "redis_or_memory"
        self._metrics["simulation_mode"] = (
            "synthetic_live"
            if runtime_operations.get("use_simulated_live_market_data")
            else "external_only"
        )

        if not self._tick_counter and not self._metrics.get("bootstrapped"):
            self._metrics["bootstrapped"] = True

        if not runtime_operations.get("use_simulated_live_market_data", False):
            self._message = (
                "waiting for external market data API"
                if runtime_operations.get("external_market_data_enabled")
                else "live simulation disabled"
            )
            return

        if self._tick_counter >= len(self._symbols):
            self._tick_counter = 0

        symbol = self._symbols[self._tick_counter]
        price = round(10 + self._tick_counter + (datetime.utcnow().second / 100), 2)
        size = 100 + self._tick_counter * 10
        event_time = datetime.utcnow()

        with SessionLocal() as db:
            db.add(TickData(symbol=symbol, price=price, size=size, event_time=event_time))
            db.commit()

        await self.publish(
            "MARKET_TICK",
            {
                "price": price,
                "size": size,
                "event_time": event_time.isoformat(),
            },
            symbol=symbol,
        )
        self._metrics["ticks_published"] = self._metrics.get("ticks_published", 0) + 1
        self._message = f"streaming {symbol}"
        self._tick_counter += 1

    async def handle_event(self, event: EventMessage) -> None:
        return None

    def _seed_metadata(self) -> None:
        with SessionLocal() as db:
            for symbol, payload in self._symbol_metadata.items():
                existing = db.scalar(select(TickerMetadata).where(TickerMetadata.symbol == symbol))
                if existing is None:
                    db.add(TickerMetadata(symbol=symbol, **payload))
            db.commit()

