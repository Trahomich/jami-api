import asyncio
import threading
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def publish_sync(self, channel: str, data: Any) -> None:
        with self._lock:
            queues = list(self._subscribers.get(channel, []))
        for queue in queues:
            queue.put_nowait(data)

    async def publish(self, channel: str, data: Any) -> None:
        self.publish_sync(channel, data)

    def subscribe(self, channel: str) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        with self._lock:
            self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[Any]) -> None:
        with self._lock:
            if channel in self._subscribers:
                try:
                    self._subscribers[channel].remove(queue)
                except ValueError:
                    pass
