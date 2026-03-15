from __future__ import annotations

import logging
from collections.abc import Iterable

from core.analytics_engine.service import AnalyticsEngineService
from core.backtest_engine.service import BacktestEngineService
from core.data_engine.service import DataEngineService
from core.execution_engine.service import ExecutionEngineService
from core.risk_engine.service import RiskEngineService
from core.scanner_engine.service import ScannerEngineService
from core.service_base import EngineService
from core.strategy_engine.service import StrategyEngineService
from utils.event_bus import BaseEventBus, InMemoryEventBus, build_event_bus
from utils.schemas import EngineStatus


logger = logging.getLogger(__name__)


class PlatformOrchestrator:
    def __init__(self) -> None:
        self.event_bus: BaseEventBus = build_event_bus()
        self.engines = self._build_engines(self.event_bus)

    def _build_engines(self, event_bus: BaseEventBus) -> list[EngineService]:
        return [
            DataEngineService(event_bus),
            ScannerEngineService(event_bus),
            StrategyEngineService(event_bus),
            RiskEngineService(event_bus),
            ExecutionEngineService(event_bus),
            BacktestEngineService(event_bus),
            AnalyticsEngineService(event_bus),
        ]

    def _engine_map(self) -> dict[str, EngineService]:
        return {engine.service_name: engine for engine in self.engines}

    def engine_names(self) -> list[str]:
        return [engine.service_name for engine in self.engines]

    def get_engine(self, engine_name: str) -> EngineService:
        engine = self._engine_map().get(engine_name)
        if engine is None:
            raise KeyError(f"Unknown engine '{engine_name}'")
        return engine

    async def start_engines(self, engine_names: Iterable[str]) -> None:
        for engine_name in engine_names:
            await self.get_engine(engine_name).start()

    async def stop_engines(self, engine_names: Iterable[str]) -> None:
        for engine_name in engine_names:
            await self.get_engine(engine_name).stop()

    async def restart_engine(self, engine_name: str) -> None:
        engine = self.get_engine(engine_name)
        await engine.stop()
        await engine.start()

    async def start(self) -> None:
        try:
            await self.event_bus.start()
        except Exception as exc:
            logger.warning("Primary event bus startup failed: %s; falling back to memory bus", exc)
            self.event_bus = InMemoryEventBus()
            await self.event_bus.start()
            self.engines = self._build_engines(self.event_bus)

        await self.start_engines(self.engine_names())

    async def stop(self) -> None:
        await self.stop_engines(reversed(self.engine_names()))
        await self.event_bus.stop()

    def statuses(self) -> list[EngineStatus]:
        return [engine.status() for engine in self.engines]

