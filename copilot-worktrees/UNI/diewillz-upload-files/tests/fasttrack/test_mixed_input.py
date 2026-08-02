import asyncio
import threading

from uni.config import Config
from uni.event_loop import EventLoop


def test_mixed_mode_is_default_and_keeps_spoken_responses():
    config = Config()
    assert config.agent.input_mode == "mixed"
    assert config.agent.speak_responses is True


def test_text_worker_submits_to_shared_input_queue(monkeypatch):
    async def scenario():
        queue = asyncio.Queue()
        stopped = threading.Event()
        loop = asyncio.get_running_loop()
        values = iter(["текстовая команда"])

        def reader(_prompt):
            try:
                return next(values)
            except StopIteration as exc:
                raise EOFError from exc

        monkeypatch.setattr("builtins.input", reader)
        await asyncio.to_thread(EventLoop._text_input_worker, loop, queue, stopped)
        source, text = await asyncio.wait_for(queue.get(), timeout=1)
        assert (source, text) == ("text", "текстовая команда")

    asyncio.run(scenario())
