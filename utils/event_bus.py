from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from typing import Awaitable, Callable

from redis.asyncio import Redis

from config.settings import settings
from utils.schemas import EventMessage


logger = logging.getLogger(__name__)

EventHandler = Callable[[EventMessage], Awaitable[None]]


class BaseEventBus:
    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def publish(self, event: EventMessage) -> None:
        raise NotImplementedError

    def subscribe(self, event_type: str, handler: EventHandler) -> Callable[[], None]:
        raise NotImplementedError

    def recent_events(self) -> list[EventMessage]:
        raise NotImplementedError


class InMemoryEventBus(BaseEventBus):
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._recent: deque[EventMessage] = deque(maxlen=250)

    async def start(self) -> None:
        logger.info("In-memory event bus started")

    async def stop(self) -> None:
        logger.info("In-memory event bus stopped")

    async def publish(self, event: EventMessage) -> None:
        self._recent.appendleft(event)
        handlers = [
            *self._subscribers.get(event.event_type, []),
            *self._subscribers.get("*", []),
        ]
        if handlers:
            await asyncio.gather(*(handler(event) for handler in handlers))

    def subscribe(self, event_type: str, handler: EventHandler) -> Callable[[], None]:
        handlers = self._subscribers.setdefault(event_type, [])
        handlers.append(handler)

        def unsubscribe() -> None:
            current = self._subscribers.get(event_type, [])
            if handler in current:
                current.remove(handler)

        return unsubscribe

    def recent_events(self) -> list[EventMessage]:
        return list(self._recent)


class RedisEventBus(InMemoryEventBus):
    def __init__(self, redis_url: str) -> None:
        super().__init__()
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._channel = "platform.events"

    async def start(self) -> None:
        self._redis = Redis.from_url(self._redis_url, decode_responses=True)
        await self._redis.ping()
        self._pubsub_task = asyncio.create_task(self._listen())
        logger.info("Redis event bus started")

    async def stop(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
        if self._redis:
            await self._redis.aclose()
        logger.info("Redis event bus stopped")

    async def publish(self, event: EventMessage) -> None:
        self._recent.appendleft(event)
        if not self._redis:
            raise RuntimeError("Redis event bus has not been started")
        await self._redis.publish(self._channel, event.model_dump_json())

    async def _listen(self) -> None:
        if not self._redis:
            return

        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                event = EventMessage.model_validate(json.loads(message["data"]))
                handlers = [
                    *self._subscribers.get(event.event_type, []),
                    *self._subscribers.get("*", []),
                ]
                if handlers:
                    await asyncio.gather(*(handler(event) for handler in handlers))
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()


def build_event_bus() -> BaseEventBus:
    backend = settings.event_bus_backend.lower()

    if backend == "memory":
        return InMemoryEventBus()

    if backend == "redis":
        return RedisEventBus(settings.redis_url)

    if backend == "auto":
        try:
            return RedisEventBus(settings.redis_url)
        except Exception:  # pragma: no cover - defensive fallback
            logger.warning("Redis event bus unavailable at construction time, falling back to memory")
            return InMemoryEventBus()

    logger.warning("Unknown event bus backend '%s', falling back to memory", settings.event_bus_backend)
    return InMemoryEventBus()

