"""WebSocket event broadcasting for real-time scan progress."""

import logging

from fastapi import WebSocket

from ..core.models import ScanEvent

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Manages WebSocket connections and broadcasts scan events."""

    def __init__(self):
        # scan_id → set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._event_history: dict[str, list[dict]] = {}
        self._max_history = 1000

    async def connect(self, scan_id: str, websocket: WebSocket) -> None:
        """Register a WebSocket connection for a scan."""
        await websocket.accept()
        if scan_id not in self._connections:
            self._connections[scan_id] = set()
        self._connections[scan_id].add(websocket)

        # Send event history to catch up
        for event_data in self._event_history.get(scan_id, []):
            try:
                await websocket.send_json(event_data)
            except Exception:
                break

    def disconnect(self, scan_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if scan_id in self._connections:
            self._connections[scan_id].discard(websocket)
            if not self._connections[scan_id]:
                del self._connections[scan_id]

    async def broadcast(self, event: ScanEvent) -> None:
        """Broadcast an event to all connected clients for that scan."""
        event_data = {
            "type": event.type,
            "scan_id": event.scan_id,
            "domain_id": event.domain_id,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
        }

        # Store in history
        if event.scan_id not in self._event_history:
            self._event_history[event.scan_id] = []
        history = self._event_history[event.scan_id]
        if len(history) < self._max_history:
            history.append(event_data)

        # Send to all connected clients
        connections = self._connections.get(event.scan_id, set()).copy()
        dead = []
        for ws in connections:
            try:
                await ws.send_json(event_data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(event.scan_id, ws)

    def cleanup(self, scan_id: str) -> None:
        """Clean up event history for a completed scan (keep for replay)."""
        pass  # Keep history for late-connecting clients

    def clear(self, scan_id: str) -> None:
        """Fully remove scan data."""
        self._connections.pop(scan_id, None)
        self._event_history.pop(scan_id, None)
