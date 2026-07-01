"""
Async Kafka producer — publishes transactions and fraud alerts
to the appropriate topics.  Degrades gracefully when Kafka is disabled.
"""

import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

from config import settings

try:
    from aiokafka import AIOKafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


def _json_serializer(obj: Any) -> bytes:
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    return json.dumps(obj, default=default).encode("utf-8")


class KafkaProducerService:
    """Wraps AIOKafkaProducer with retry logic and graceful fallback."""

    def __init__(self):
        self._producer: Optional[Any] = None
        self._enabled = settings.KAFKA_ENABLED and KAFKA_AVAILABLE
        self._fallback_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)

    async def start(self):
        if not self._enabled:
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=_json_serializer,
            compression_type="gzip",
            linger_ms=5,
            max_batch_size=32_768,
            request_timeout_ms=10_000,
            retry_backoff_ms=200,
        )
        await self._producer.start()

    async def stop(self):
        if self._producer:
            await self._producer.stop()

    async def produce(self, topic: str, message: Dict[str, Any], key: Optional[str] = None):
        """Publish a message; falls back to an internal async queue if Kafka is down."""
        key_bytes = key.encode() if key else None
        if self._enabled and self._producer:
            try:
                await self._producer.send_and_wait(
                    topic,
                    value=message,
                    key=key_bytes,
                )
                return
            except Exception as exc:
                # Silently fall through to queue fallback
                pass

        # Fallback: push to internal queue for downstream consumers
        if not self._fallback_queue.full():
            await self._fallback_queue.put({"topic": topic, "message": message})

    async def produce_transaction(self, txn_dict: Dict[str, Any]):
        topic = settings.KAFKA_TOPICS["raw"]
        await self.produce(topic, txn_dict, key=txn_dict.get("transaction_id"))

    async def produce_flagged(self, txn_dict: Dict[str, Any]):
        topic = settings.KAFKA_TOPICS["flagged"]
        await self.produce(topic, txn_dict, key=txn_dict.get("transaction_id"))

    async def produce_fraud_alert(self, alert_dict: Dict[str, Any]):
        topic = settings.KAFKA_TOPICS["fraud_alerts"]
        await self.produce(topic, alert_dict, key=alert_dict.get("alert_id"))

    async def produce_graph_update(self, update_dict: Dict[str, Any]):
        topic = settings.KAFKA_TOPICS["graph_updates"]
        await self.produce(topic, update_dict)

    @property
    def fallback_queue(self) -> asyncio.Queue:
        return self._fallback_queue

    @property
    def is_kafka_active(self) -> bool:
        return self._enabled and self._producer is not None
