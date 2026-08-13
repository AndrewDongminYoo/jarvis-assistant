import asyncio
import sys
import time
from pathlib import Path

from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from server import PendingAction  # noqa: E402


def test_pending_action_not_expired_when_fresh():
    p = PendingAction(action="MAIL:SEND:a::hi", history=[], asked_at=time.time())
    assert p.expired() is False  # nosec B101


def test_pending_action_expired_after_window():
    p = PendingAction(
        action="MAIL:SEND:a::hi",
        history=[],
        asked_at=time.time() - 60.0,
        expires_in=30.0,
    )
    assert p.expired() is True  # nosec B101


def test_pending_registry_exists_and_is_empty_by_default():
    assert hasattr(server, "_pending")  # nosec B101
    server._pending.clear()
    assert server._pending == {}  # nosec B101


def test_ws_voice_pending_cleanup_on_disconnect(monkeypatch):
    connection_id = "connection-to-clean"
    monkeypatch.setattr(
        server,
        "_new_connection_id",
        lambda: connection_id,
        raising=False,
    )
    server._pending.clear()
    server._pending[connection_id] = PendingAction(
        action="MAIL:SEND:a::hi",
        history=[],
        asked_at=time.time(),
    )

    class DisconnectingWS:
        headers = {"host": f"localhost:{server.PORT}"}

        async def accept(self):
            return None

        async def receive_json(self):
            raise WebSocketDisconnect(code=1000)

    asyncio.run(server.ws_voice(DisconnectingWS()))

    assert connection_id not in server._pending  # nosec B101
