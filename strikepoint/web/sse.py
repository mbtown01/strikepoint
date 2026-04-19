import json
import queue
import threading


class SSEManager:
    """Pushes Server-Sent Events to all connected browser clients.

    Thread-safe: push() is called from the capture driver thread;
    stream() runs in per-request Flask threads.
    """

    def __init__(self):
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()

    def push(self, event_type: str, data: dict) -> None:
        """Broadcast an event to every connected client."""
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        with self._lock:
            dead = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._clients.remove(q)

    def stream(self):
        """Generator yielded as a Flask SSE response.

        Registers a per-client queue, yields events as they arrive,
        and deregisters the queue when the client disconnects.
        """
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._clients.append(q)
        try:
            while True:
                try:
                    yield q.get(timeout=5)
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with self._lock:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass
