from __future__ import annotations

from sqlalchemy import select

from database.models import TickerMetadata
from database.session import SessionLocal
from utils.preferences import get_scanner_settings
from utils.schemas import EventMessage

from core.service_base import EngineService


class ScannerEngineService(EngineService):
    service_name = "scanner_engine"
    subscriptions = ("MARKET_TICK",)

    async def handle_event(self, event: EventMessage) -> None:
        price = float(event.payload.get("price", 0))
        if not event.symbol:
            return

        scanner_settings = get_scanner_settings()
        min_price = float(scanner_settings.get("min_price", 2.0))
        max_price = float(scanner_settings.get("max_price", 20.0))
        max_float_shares = float(scanner_settings.get("max_float_millions", 20.0)) * 1_000_000
        min_avg_volume = int(scanner_settings.get("min_avg_volume", 0))
        max_market_cap = float(scanner_settings.get("max_market_cap_millions", 1000.0)) * 1_000_000
        exclude_halted = bool(scanner_settings.get("exclude_halted", True))

        with SessionLocal() as db:
            metadata = db.scalar(
                select(TickerMetadata).where(TickerMetadata.symbol == event.symbol)
            )

        if metadata is None:
            self._message = f"missing metadata for {event.symbol}"
            return

        passes_price = min_price <= price <= max_price
        passes_float = metadata.float_shares is None or metadata.float_shares <= max_float_shares
        passes_volume = metadata.avg_volume is None or metadata.avg_volume >= min_avg_volume
        passes_market_cap = metadata.market_cap is None or metadata.market_cap <= max_market_cap
        passes_halt = not (exclude_halted and metadata.is_halted)

        if passes_price and passes_float and passes_volume and passes_market_cap and passes_halt:
            await self.publish(
                "SYMBOL_UNIVERSE_UPDATE",
                {
                    "scanner_mode": "FILTERED_UNIVERSE",
                    "reason": "scanner_filter_match",
                    "price": price,
                    "float_millions": None if metadata.float_shares is None else round(metadata.float_shares / 1_000_000, 2),
                    "avg_volume": metadata.avg_volume,
                    "market_cap_millions": None if metadata.market_cap is None else round(metadata.market_cap / 1_000_000, 2),
                    "is_halted": metadata.is_halted,
                },
                symbol=event.symbol,
            )
            self._metrics["symbols_published"] = self._metrics.get("symbols_published", 0) + 1
            self._message = f"tracking {event.symbol}"
        else:
            self._message = f"{event.symbol} filtered out"

