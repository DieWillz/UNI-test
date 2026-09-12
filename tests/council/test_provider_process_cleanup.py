import asyncio

from uni.council.provider import CodexProvider


def test_codex_provider_kills_process_on_timeout(monkeypatch):
    class HangingProcess:
        returncode = None

        def __init__(self):
            self.killed = False

        async def communicate(self):
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True
            self.returncode = -9

    proc = HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = CodexProvider(timeout_seconds=0.01)
    reply = asyncio.run(provider.ask("Codex", "test"))

    assert reply.error and "TimeoutError" in reply.error
    assert proc.killed is True


def test_codex_provider_kills_process_when_ask_is_cancelled(monkeypatch):
    class HangingProcess:
        returncode = None

        def __init__(self):
            self.killed = False

        async def communicate(self):
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True
            self.returncode = -9

    proc = HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    async def run_cancel():
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
        provider = CodexProvider(timeout_seconds=60)
        task = asyncio.create_task(provider.ask("Codex", "test"))
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return proc.killed

    assert asyncio.run(run_cancel()) is True
