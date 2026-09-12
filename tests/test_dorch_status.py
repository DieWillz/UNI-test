from types import SimpleNamespace

from uni.webui import server


class QueueState:
    def status(self):
        return {
            "stopped": False,
            "mode": "autonomous",
            "current_step": None,
            "pending_steps": [],
            "steps": [],
            "total_remaining_seconds": 0,
            "control_epoch": 0,
            "queue_revision": 1,
            "last_error": "",
        }


def test_dorch_status_distinguishes_intiface_server_from_device_presence():
    handler = object.__new__(server._Handler)
    bridge = SimpleNamespace(status=lambda: {
        "connected": True,
        "devices": [],
        "url": "ws://127.0.0.1:12345",
        "last_error": "",
    })
    coordinator = SimpleNamespace(
        _bridge=bridge,
        current_value=0,
        emergency_stopped=False,
    )
    handler._toy_coordinator = lambda: coordinator
    agent = SimpleNamespace(control_queue=QueueState())

    status = handler._dorch_session_status(agent)

    assert status["intiface_connected"] is True
    assert status["device_connected"] is False
    assert status["devices"] == []
    assert "устройство не найдено" in status["status"].casefold()
