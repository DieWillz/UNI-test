from __future__ import annotations

import json

from uni.webui.remote_session import RemoteRoomStore


def test_remote_room_routes_events_without_tokens(tmp_path):
    store = RemoteRoomStore(tmp_path)
    event = store.send("controller", "chat", "hello")

    assert store.poll("owner", 0) == [event]
    assert store.poll("controller", 0) == []
    persisted = json.loads(store.chat_path.read_text(encoding="utf-8"))
    assert persisted["payload"] == "hello"
    assert "token" not in persisted


def test_remote_room_reset_clears_ephemeral_events(tmp_path):
    store = RemoteRoomStore(tmp_path)
    store.send("owner", "offer", {"sdp": "test"})
    store.reset()

    assert store.poll("controller", 0) == []
    assert store.send("owner", "chat", "new")["id"] == 1
