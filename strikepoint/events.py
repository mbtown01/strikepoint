from __future__ import annotations

from dataclasses import dataclass
from queue import Queue, Empty
from typing import Any, Callable, DefaultDict, Dict, List, Type, TypeVar
from logging import getLogger


logger = getLogger("strikepoint")
T = TypeVar("T")


class EventBus:
    """Very small in-process pub/sub bus.

    Serial/pumped contract:
    - `publish(event)` enqueues the event.
    - `pump()` processes queued events *synchronously* in FIFO order.
    - Subscribers run on the caller's thread (usually the capture loop).

    This makes control flow deterministic and avoids an additional dispatcher
    thread. The tradeoff is that slow subscribers will slow the pump caller.
    """

    def __init__(self, *, maxQueue: int = 0):
        self._q: Queue[object] = Queue(maxsize=maxQueue)
        self._subs: DefaultDict[Type[object],
                                List[Callable[[Any], None]]] = DefaultDict(list)

    def subscribe(self, eventType: Type[T], handler: Callable[[T], None]) -> None:
        self._subs[eventType].append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, eventType: Type[T], handler: Callable[[T], None]) -> None:
        self._subs[eventType].remove(handler)

    def publish(self, event: object) -> None:
        self._q.put(event)

    def pump(self) -> int:
        """Process up to `maxEvents` queued events. Returns number processed."""
        while not self._q.empty():
            ev = self._q.get_nowait()
            for handler in self._subs[type(ev)]:
                try:
                    handler(ev)
                except Exception as e:
                    logger.error(
                        f"EventBus exception encountered processing event {ev}: {e}")


@dataclass(frozen=True)
class FrameEvent:
    frameSeq: int
    frameInfo: Any


@dataclass(frozen=True)
class LogBatchEvent:
    lines: List[str]


