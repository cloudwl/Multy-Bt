from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        message = {
            "event": event,
            "payload": payload,
            "timestamp": int(time.time() * 1000),
        }
        for queue in list(self._subscribers):
            await queue.put(message)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
