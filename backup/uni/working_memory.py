"""
uni.working_memory — персистентная рабочая память агента.

Назначение:
    Простое key-value хранилище на JSON-файле. Используется агентом для
    хранения контекста между циклами (последние действия, факты о задаче,
    состояние диалога) и для сборки текстового контекста, который
    подставляется в system/user prompt перед вызовом Brain.chat().

Зависимости: стандартная библиотека (json, pathlib) — без внешних пакетов.

Пример использования:
    >>> from pathlib import Path
    >>> wm = WorkingMemory(Path("memory/working.json"))
    >>> wm.set("last_task", "открыть Chrome и найти видео про LM Studio")
    >>> wm.get("last_task")
    'открыть Chrome и найти видео про LM Studio'
    >>> wm.get_context(max_tokens=500)
    'last_task: открыть Chrome и найти видео про LM Studio'

Известные ограничения:
    - Не потокобезопасно и не process-safe (нет файловых блокировок).
      Для MVP это ок: агент — один процесс, один event loop.
    - get_context() режет по грубой оценке токенов (символы / 4), а не по
      реальному токенайзеру модели — для MVP этого достаточно, точный
      подсчёт токенов не входит в объём Build 3.
    - Значения должны быть JSON-сериализуемы (str, int, float, bool, list,
      dict, None). Попытка set() несериализуемого значения бросит TypeError
      при следующем persist().
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class WorkingMemory:
    """Персистентное key-value хранилище поверх JSON-файла."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except json.JSONDecodeError:
            # Повреждённый файл памяти не должен ронять агент при старте.
            # Оставляем файл как есть (для диагностики) и стартуем с пустой памятью.
            return {}

    def _persist(self) -> None:
        """Атомарная запись: пишем во временный файл рядом, затем rename."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ------------------------------------------------------------------
    # Public API (контракт зафиксирован координатором)
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._persist()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def delete(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._persist()

    def list_keys(self) -> list[str]:
        return list(self._data.keys())

    def get_context(self, max_tokens: int = 4000) -> str:
        """
        Форматирует память в виде текста "key: value" по одной строке,
        для вставки в prompt. Обрезает по грубой оценке токенов
        (~4 символа на токен), сохраняя самые НЕДАВНО изменённые записи
        (последние set() оказываются позже в dict — Python 3.7+
        гарантирует порядок вставки).
        """
        if not self._data:
            return ""

        max_chars = max_tokens * 4
        lines: list[str] = []
        # Идём от самых свежих записей к старым, чтобы при обрезке
        # терялся именно устаревший контекст, а не последний.
        for key in reversed(list(self._data.keys())):
            value = self._data[key]
            lines.append(f"{key}: {value}")

        result_lines: list[str] = []
        total_chars = 0
        for line in lines:
            total_chars += len(line) + 1  # +1 за перевод строки
            if total_chars > max_chars:
                break
            result_lines.append(line)

        # Возвращаем в исходном (хронологическом) порядке.
        return "\n".join(reversed(result_lines))

    def clear(self) -> None:
        self._data = {}
        self._persist()