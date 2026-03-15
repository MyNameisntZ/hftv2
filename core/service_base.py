from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from config.settings import settings
from database.models import ServiceHeartbeat, SystemEvent
from database.session import SessionLocal
from utils.event_bus import BaseEventBus
from utils.schemas import EngineStatus, EventMessage


logger = logging.getLogger(__name__)


class EngineService:
    service_name = "engine"
    subscriptions: tuple[str, ...] = ()

    def __init__(self, event_bus: BaseEventBus) -> None:
        self.event_bus = event_bus
        self._task: asyncio.Task | None = None
        self._running = False
        self._status = "created"
        self._last_heartbeat: datetime | None = None
        self._started_at: datetime | None = None
        self._message = "initializing"
        self._metrics: dict[str, Any] = {}
        self._unsubscribers: list = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._status = "starting"
        self._started_at = datetime.utcnow()
        self._message = "service starting"
        for event_type in self.subscriptions:
            self._unsubscribers.append(self.event_bus.subscribe(event_type, self.handle_event))
        self._task = asyncio.create_task(self._run_loop(), name=f"{self.service_name}-loop")
        logger.info("%s started", self.service_name)

    async def stop(self) -> None:
        if not self._running and self._status == "stopped":
            return
        self._running = False
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._status = "stopped"
        await self._heartbeat("stopped", "service stopped")
        logger.info("%s stopped", self.service_name)

    async def _run_loop(self) -> None:
        await self.on_start()
        try:
            while self._running:
                await self.run_cycle()
                self._status = "running"
                await self._heartbeat("running", self._message)
                await asyncio.sleep(settings.service_loop_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - startup/runtime safeguard
            logger.exception("%s crashed", self.service_name)
            self._status = "error"
            await self._heartbeat("error", str(exc))
            raise
        finally:
            await self.on_stop()

    async def on_start(self) -> None:
        await self._heartbeat("starting", "service starting")

    async def on_stop(self) -> None:
        return None

    async def run_cycle(self) -> None:
        return None

    async def handle_event(self, event: EventMessage) -> None:
        return None

    async def publish(self, event_type: str, payload: dict[str, Any], symbol: str | None = None) -> None:
        event = EventMessage(event_type=event_type, source=self.service_name, symbol=symbol, payload=payload)
        with SessionLocal() as db:
            db.add(
                SystemEvent(
                    event_type=event.event_type,
                    source=event.source,
                    symbol=event.symbol,
                    payload=event.payload,
                )
            )
            db.commit()
        await self.event_bus.publish(event)

    async def _heartbeat(self, status: str, message: str | None = None) -> None:
        self._last_heartbeat = datetime.utcnow()
        self._message = message or status

        with SessionLocal() as db:
            heartbeat = db.scalar(
                select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == self.service_name)
            )
            if heartbeat is None:
                heartbeat = ServiceHeartbeat(service_name=self.service_name, status=status, message=message)
                db.add(heartbeat)
            heartbeat.status = status
            heartbeat.message = message
            heartbeat.last_seen = self._last_heartbeat
            db.commit()

    def status(self) -> EngineStatus:
        return EngineStatus(
            name=self.service_name,
            healthy=self._status in {"starting", "running"},
            status=self._status,
            last_heartbeat=self._last_heartbeat,
            message=self._message,
            metrics={
                **self._metrics,
                "running": self._running,
                "started_at": self._started_at,
            },
        )

