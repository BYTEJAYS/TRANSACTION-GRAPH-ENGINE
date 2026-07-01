"""
Async Kafka consumer — reads from topics and dispatches messages
to registered handler callbacks.
"""

import json
import asyncio
from typing import Callable, Dict, Any, Optional, Awaitable, List

from config import settings

try:
    from aiokafka import AIOKafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


Handler = Callable[[Dict[str, Any]], Awaitable[None]]


class KafkaConsumerService:
    """
    Subscribes to one or more Kafka topics and dispatches decoded
    messages to registered async handlers.
    """

    def __init__(self, topics: List[str], group_id: Optional[str] = None):
        self._topics = topics
        self._group_id = group_id or settings.KAFKA_GROUP_ID
        self._consumer: Optional[Any] = None
        self._handlers: Dict[str, List[Handler]] = {t: [] for t in topics}
        self._enabled = settings.KAFKA_ENABLED and KAFKA_AVAILABLE
        self._running = False

    def register_handler(self, topic: str, handler: Handler):
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    async def start(self):
        if not self._enabled:
            return
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
            fetch_max_wait_ms=100,
        )
        await self._consumer.start()

    async def stop(self):
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    async def consume(self):
        """Main consumption loop; call as a background task."""
        if not self._enabled or not self._consumer:
            return

        self._running = True
        async for msg in self._consumer:
            if not self._running:
                break
            topic = msg.topic
            payload = msg.value
            handlers = self._handlers.get(topic, [])
            for handler in handlers:
                try:
                    await handler(payload)
                except Exception:
                    pass
