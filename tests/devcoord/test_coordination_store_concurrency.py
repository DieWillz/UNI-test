from __future__ import annotations

import threading
import time

from uni.devcoord.models import CoordinatorEvent, DevelopmentTask
from uni.devcoord.store import CoordinationStore


def _task(title: str) -> DevelopmentTask:
    return DevelopmentTask(
        title=title,
        goal=f"goal {title}",
        instructions=f"instructions {title}",
        provider_sequence=["stub"],
    )


def test_two_store_instances_do_not_lose_concurrent_task_updates(tmp_path, monkeypatch):
    path = tmp_path / "coord.json"
    first = CoordinationStore(path)
    second = CoordinationStore(path)
    start = threading.Barrier(3)
    real_read = CoordinationStore._read

    def delayed_read(self):
        data = real_read(self)
        time.sleep(0.05)
        return data

    monkeypatch.setattr(CoordinationStore, "_read", delayed_read)
    errors: list[Exception] = []
    tasks = [_task("first"), _task("second")]

    def save(store, task):
        start.wait(timeout=2)
        try:
            store.save_task(task)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=save, args=(first, tasks[0])),
        threading.Thread(target=save, args=(second, tasks[1])),
    ]
    for thread in threads:
        thread.start()
    start.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    monkeypatch.undo()
    stored = {task.id for task in CoordinationStore(path).list_tasks()}
    assert stored == {task.id for task in tasks}


def test_two_store_instances_do_not_lose_concurrent_events(tmp_path, monkeypatch):
    path = tmp_path / "coord.json"
    first = CoordinationStore(path)
    second = CoordinationStore(path)
    start = threading.Barrier(3)
    real_read = CoordinationStore._read

    def delayed_read(self):
        data = real_read(self)
        time.sleep(0.05)
        return data

    monkeypatch.setattr(CoordinationStore, "_read", delayed_read)
    errors: list[Exception] = []
    events = [
        CoordinatorEvent(event="first", task_id="task-1"),
        CoordinatorEvent(event="second", task_id="task-1"),
    ]

    def append(store, event):
        start.wait(timeout=2)
        try:
            store.append_event(event)
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=append, args=(first, events[0])),
        threading.Thread(target=append, args=(second, events[1])),
    ]
    for thread in threads:
        thread.start()
    start.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    monkeypatch.undo()
    stored = {event.event for event in CoordinationStore(path).events_for("task-1")}
    assert stored == {"first", "second"}
