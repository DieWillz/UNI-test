"""
Knowledge Base — долгосрочная память UNI.
Фаза 0.2: SQLite для хранения ответов совета, навыков, верифицированных утверждений.

Это НЕ нарушение MVP-философии — MVP_0_1.md явно относит SQLite к фазе 0.2:
"Excluded from MVP (Future Phases): SQLite / sqlite-vec / multi-tier memory → Phase 0.2"
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class CouncilResponse(BaseModel):
    """Ответ участника совета (сохраняется для обучения)."""
    response_id: str
    task_id: str
    provider: str
    topic: str
    response_text: str
    confidence: float
    verified: bool = False
    verification_evidence: Optional[str] = None
    used_in_patch: bool = False
    patch_success: Optional[bool] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Skill(BaseModel):
    """Навык UNI — извлечённый из успешных патчей."""
    skill_id: str
    name: str
    description: str
    source_task_ids: list[str] = Field(default_factory=list)
    code_pattern: str = ""
    success_count: int = 0
    failure_count: int = 0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class VerifiedClaim(BaseModel):
    """Верифицированное утверждение о коде."""
    claim_id: str
    claim_text: str
    file_path: str
    verified: bool
    evidence: str = ""
    verified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class KnowledgeBase:
    """
    Долгосрочная память UNI.

    Хранит:
    - Все ответы совета (для анализа паттернов и обучения)
    - Верифицированные утверждения о коде (для быстрого доступа)
    - Успешные патчи (для обучения)
    - Навыки (skills) — извлечённые из патчей
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Создаёт таблицы при первом запуске."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS council_responses (
                    response_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    verification_evidence TEXT,
                    used_in_patch INTEGER DEFAULT 0,
                    patch_success INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_responses_task
                    ON council_responses(task_id);
                CREATE INDEX IF NOT EXISTS idx_responses_provider
                    ON council_responses(provider);
                CREATE INDEX IF NOT EXISTS idx_responses_verified
                    ON council_responses(verified);

                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_task_ids TEXT NOT NULL,
                    code_pattern TEXT NOT NULL DEFAULT '',
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS verified_claims (
                    claim_id TEXT PRIMARY KEY,
                    claim_text TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    evidence TEXT DEFAULT '',
                    verified_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_claims_file
                    ON verified_claims(file_path);
            """)

    # ─── Council Responses ───────────────────────────────────────────────

    def store_response(self, response: CouncilResponse) -> None:
        """Сохраняет ответ совета для будущего обучения."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO council_responses
                (response_id, task_id, provider, topic, response_text,
                 confidence, verified, verification_evidence,
                 used_in_patch, patch_success, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response.response_id,
                    response.task_id,
                    response.provider,
                    response.topic,
                    response.response_text,
                    response.confidence,
                    int(response.verified),
                    response.verification_evidence,
                    int(response.used_in_patch),
                    response.patch_success,
                    response.created_at,
                ),
            )

    def find_similar_responses(
        self, topic: str, limit: int = 5
    ) -> list[CouncilResponse]:
        """
        Находит похожие ответы из прошлого (для контекста при синтезе).

        Фаза 0.3: добавить sqlite-vec для семантического поиска.
        Сейчас: простой текстовый поиск по ключевым словам.
        """
        keywords = [kw.lower() for kw in topic.split() if len(kw) > 3]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT * FROM council_responses
                WHERE verified = 1
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit * 10,),
            )

            results: list[CouncilResponse] = []
            for row in cursor.fetchall():
                response_text = row[4].lower()
                match_count = sum(1 for kw in keywords if kw in response_text)
                if match_count > 0:
                    results.append(
                        CouncilResponse(
                            response_id=row[0],
                            task_id=row[1],
                            provider=row[2],
                            topic=row[3],
                            response_text=row[4],
                            confidence=row[5],
                            verified=bool(row[6]),
                            verification_evidence=row[7],
                            used_in_patch=bool(row[8]),
                            patch_success=bool(row[9]) if row[9] is not None else None,
                            created_at=row[10],
                        )
                    )

            results.sort(
                key=lambda r: sum(
                    1 for kw in keywords if kw in r.response_text.lower()
                ),
                reverse=True,
            )
            return results[:limit]

    def mark_used_in_patch(
        self, response_id: str, success: bool
    ) -> None:
        """Помечает ответ как использованный в патче + результат."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE council_responses
                SET used_in_patch = 1, patch_success = ?
                WHERE response_id = ?
                """,
                (int(success), response_id),
            )

    # ─── Skills ──────────────────────────────────────────────────────────

    def extract_skill(
        self,
        task_id: str,
        patch_diff: str,
        skill_name: str,
        description: str,
    ) -> Skill:
        """Извлекает навык из успешного патча."""
        skill = Skill(
            skill_id=f"SKILL-{uuid.uuid4().hex[:8].upper()}",
            name=skill_name,
            description=description,
            source_task_ids=[task_id],
            code_pattern=patch_diff[:500],
            success_count=1,
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO skills
                (skill_id, name, description, source_task_ids, code_pattern,
                 success_count, failure_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill.skill_id,
                    skill.name,
                    skill.description,
                    json.dumps(skill.source_task_ids),
                    skill.code_pattern,
                    skill.success_count,
                    skill.failure_count,
                    skill.created_at,
                ),
            )

        return skill

    def get_top_skills(self, limit: int = 10) -> list[Skill]:
        """Возвращает навыки для инъекции в промпт совета."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT * FROM skills
                ORDER BY success_count DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            return [
                Skill(
                    skill_id=row[0],
                    name=row[1],
                    description=row[2],
                    source_task_ids=json.loads(row[3]),
                    code_pattern=row[4],
                    success_count=row[5],
                    failure_count=row[6],
                    created_at=row[7],
                )
                for row in cursor.fetchall()
            ]

    # ─── Verified Claims ─────────────────────────────────────────────────

    def store_claim(self, claim: VerifiedClaim) -> None:
        """Сохраняет результат верификации утверждения о коде."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO verified_claims
                (claim_id, claim_text, file_path, verified, evidence, verified_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    claim.claim_text,
                    claim.file_path,
                    int(claim.verified),
                    claim.evidence,
                    claim.verified_at,
                ),
            )

    def get_claims_for_file(self, file_path: str) -> list[VerifiedClaim]:
        """Возвращает все верифицированные утверждения для файла."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM verified_claims WHERE file_path = ?",
                (file_path,),
            )
            return [
                VerifiedClaim(
                    claim_id=row[0],
                    claim_text=row[1],
                    file_path=row[2],
                    verified=bool(row[3]),
                    evidence=row[4],
                    verified_at=row[5],
                )
                for row in cursor.fetchall()
            ]