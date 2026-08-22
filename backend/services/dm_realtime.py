"""In-process real-time delivery for open private-message conversations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class Subscription:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]


_subscriptions: dict[str, set[Subscription]] = {}
_lock = Lock()


def subscribe(conversation_id: str, loop: asyncio.AbstractEventLoop) -> Subscription:
    subscription = Subscription(loop=loop, queue=asyncio.Queue(maxsize=50))
    with _lock:
        _subscriptions.setdefault(conversation_id, set()).add(subscription)
    return subscription


def unsubscribe(conversation_id: str, subscription: Subscription) -> None:
    with _lock:
        subscribers = _subscriptions.get(conversation_id)
        if not subscribers:
            return
        subscribers.discard(subscription)
        if not subscribers:
            _subscriptions.pop(conversation_id, None)


def _enqueue(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        # A slow tab should not block message delivery to other subscribers.
        pass


def publish(conversation_id: str, event: dict[str, Any]) -> None:
    with _lock:
        subscribers = list(_subscriptions.get(conversation_id, set()))
    for subscription in subscribers:
        subscription.loop.call_soon_threadsafe(_enqueue, subscription.queue, event)
