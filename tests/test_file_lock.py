from __future__ import annotations

import threading
from pathlib import Path

from uni.utils import file_lock


def test_concurrent_acquire_has_single_winner(tmp_path, monkeypatch) -> None:
    target = tmp_path / "shared.txt"
    barrier = threading.Barrier(2)
    real_exists = Path.exists

    def synchronized_exists(path: Path) -> bool:
        if str(path) == f"{target}.lock":
            barrier.wait(timeout=2)
            return False
        return real_exists(path)

    monkeypatch.setattr(Path, "exists", synchronized_exists)
    results: list[bool] = []

    def contender() -> None:
        results.append(file_lock.acquire_lock(str(target)))

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(results) == [False, True]

def test_timeout_waits_for_lock_release(tmp_path) -> None:
    import time

    target = tmp_path / "waited.txt"
    assert file_lock.acquire_lock(str(target)) is True

    def release_later() -> None:
        time.sleep(0.05)
        file_lock.release_lock(str(target))

    releaser = threading.Thread(target=release_later)
    releaser.start()
    started = time.monotonic()
    acquired = file_lock.acquire_lock(str(target), timeout=0.5)
    elapsed = time.monotonic() - started
    releaser.join(timeout=1)

    assert acquired is True
    assert elapsed >= 0.04
    file_lock.release_lock(str(target))
