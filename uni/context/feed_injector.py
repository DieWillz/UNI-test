"""Парсер и инжектор внешнего контекста/стилей для ответов Юни.

Адаптировано из ТЗ «Чат-интерфейс, Камера, Context Feed». Отличия:
  * Внешний текст всегда НЕДОВЕРЕННЫЕ данные (как в council) — он идёт
    только в системный промпт как «подсказка стиля», НЕ вызывает инструменты.
  * Реальный скрейпинг по умолчанию ВЫКЛ (config.context.allow_external_scrape);
    метод fetch_style_hints сам по сети не ходит, если scrape запрещён.
  * httpx используется лениво (только если включён scrape), чтобы модуль
    можно было импортировать без сетевых зависимостей.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re

logger = logging.getLogger(__name__)

# Удаляем HTML-теги целиком, затем оставляем только безопасные символы.
_TAG_RE = re.compile(r"<[^>]*>")
_PHRASE_RE = re.compile(r"[^\w\s\-\.,!?;:«»\"'а-яёА-ЯЁ]+", flags=re.IGNORECASE)
_MAX_HINT_CHARS = 200


def _sanitize(text: str) -> str:
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = _PHRASE_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:_MAX_HINT_CHARS].strip()


class ContextFeedInjector:
    """Сбор стилевых подсказок из внешних фидов для системного промпта."""

    def __init__(self, *, allow_external_scrape: bool = False) -> None:
        self.active_feeds: list[str] = []
        self._allow_external_scrape = bool(allow_external_scrape)
        self._cached_prompts: list[str] = []

    # ---------- управление фидами ----------
    def add_feed_url(self, url: str) -> bool:
        url = (url or "").strip()
        if not url or url in self.active_feeds:
            return False
        self.active_feeds.append(url)
        return True

    def remove_feed_url(self, url: str) -> bool:
        url = (url or "").strip()
        if url in self.active_feeds:
            self.active_feeds.remove(url)
            return True
        return False

    def list_feeds(self) -> list[str]:
        return list(self.active_feeds)

    def set_external_scrape(self, allowed: bool) -> None:
        self._allow_external_scrape = bool(allowed)

    # ---------- кэш подсказок ----------
    def cache_local_hints(self, hints: list[str]) -> None:
        """Добавить локально заданные подсказки (без сети)."""
        for h in hints:
            clean = _sanitize(str(h))
            if clean and clean not in self._cached_prompts:
                self._cached_prompts.append(clean)

    # ---------- генерация подсказки ----------
    def build_style_hint(self, rate: float = 0.6, rng: random.Random | None = None) -> str:
        """Вернуть строку-подсказку для системного промпта на основе rate.

        rate (0..1) — «Injection Rate / Spiciness»: чем выше, тем вероятнее
        подсказка вообще появится и тем больше их будет. Без сети использует
        только локально закешированные подсказки.
        """
        rate = max(0.0, min(1.0, float(rate)))
        rng = rng or random.Random()
        if rate <= 0.0 or not self._cached_prompts:
            return ""
        if rng.random() > rate:
            return ""
        count = 1 + (1 if rng.random() < rate else 0)
        chosen = rng.sample(self._cached_prompts, min(count, len(self._cached_prompts)))
        hints = "; ".join(chosen)
        return f"\n[Стилевая подсказка из внешнего источника (только для тона): {hints}]"

    async def fetch_style_hints(self, rate: float = 0.6) -> str:
        """Собрать подсказки из фидов (если разрешён внешний scrape).

        По умолчанию (scrape выключен) просто возвращает локально
        закешированные подсказки через build_style_hint — без сети.
        """
        if self._allow_external_scrape and self.active_feeds:
            try:
                await self._scrape_feeds()
            except Exception as exc:  # noqa: BLE001 — scrape не должен ломать чат
                logger.warning("Context feed scrape failed: %s", exc)
        return self.build_style_hint(rate)

    async def _scrape_feeds(self) -> None:
        """Ленивый scrape фидов (только если разрешено). Таймаут на запрос."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx недоступен — внешний scrape пропущен")
            return
        new_hints: list[str] = []
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            for url in self.active_feeds:
                try:
                    resp = await client.get(url)
                    text = resp.text or ""
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Не удалось загрузить фид %s: %s", url, exc)
                    continue
                # Грубый отбор коротких фраз-подсказок из текста страницы.
                for line in text.splitlines():
                    line = line.strip()
                    if 12 <= len(line) <= 120 and not line.startswith(("http", "<", "{", "[")):
                        clean = _sanitize(line)
                        if clean:
                            new_hints.append(clean)
        # Ограничиваем кэш, чтобы не разрастался бесконечно.
        self._cached_prompts = (new_hints + self._cached_prompts)[:50]
