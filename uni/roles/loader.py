"""Role Loader - loads roles from Markdown files"""

from pathlib import Path
from dataclasses import dataclass


@dataclass
class Role:
    name: str
    language: str
    voice: str
    system_prompt: str
    behavior: str
    constraints: str
    nsfw: bool = False


class RoleLoader:
    def __init__(self, roles_dir: Path | None = None):
        self.roles_dir = roles_dir or Path(__file__).resolve().parent

    def load(self, role_name: str) -> Role:
        """Load role from Markdown file."""
        if not role_name or Path(role_name).name != role_name:
            raise ValueError(f"Invalid role name: {role_name!r}")
        role_file = self.roles_dir / f"{role_name}.md"
        if not role_file.exists():
            raise FileNotFoundError(f"Role not found: {role_file}")

        content = role_file.read_text(encoding="utf-8")
        return self._parse_role(role_name, content)

    def _parse_role(self, name: str, content: str) -> Role:
        """Parse Markdown role file."""
        # Parse frontmatter
        lines = content.split("\n")
        frontmatter = {}
        body_start = 0

        if lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    body_start = i + 1
                    break
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip()

        body = "\n".join(lines[body_start:]).strip()

        # Extract sections
        system_prompt = self._extract_section(body, "System Prompt")
        behavior = self._extract_section(body, "Behavior")
        constraints = self._extract_section(body, "Constraints")

        # Build full system prompt
        full_prompt = self._build_system_prompt(system_prompt, behavior, constraints)

        return Role(
            name=name,
            language=frontmatter.get("language", "ru"),
            voice=frontmatter.get("voice", "default"),
            system_prompt=full_prompt,
            behavior=behavior,
            constraints=constraints,
            nsfw=str(frontmatter.get("nsfw", "false")).strip().lower() == "true",
        )

    def _extract_section(self, body: str, section_name: str) -> str:
        """Extract a section from Markdown body."""
        lines = body.split("\n")
        in_section = False
        content = []

        for line in lines:
            if line.startswith(f"## {section_name}") or line.startswith(f"# {section_name}"):
                in_section = True
                continue
            if in_section and line.startswith("#"):
                break
            if in_section:
                content.append(line)

        return "\n".join(content).strip()

    def _build_system_prompt(self, system_prompt: str, behavior: str, constraints: str) -> str:
        """Build complete system prompt."""
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if behavior:
            parts.append(f"## Поведение\n{behavior}")
        if constraints:
            parts.append(f"## Ограничения\n{constraints}")
        return "\n\n".join(parts)


def get_default_role() -> str:
    """Get default role content."""
    return """---
name: assistant
language: ru
voice: default
---

# System Prompt

Ты — UNI, универсальный локальный AI-агент. Ты управляешь компьютером, браузером, можешь видеть экран, слышать и говорить.

## Behavior

- Думай вслух: объясняй, что делаешь, перед каждым действием
- Проверяй результат: после каждого действия убеждайся, что оно успешно
- Задавай вопросы: если не уверен, спрашивай у пользователя
- Говори по-русски по умолчанию
- Будь проактивным: предлагай следующие шаги

## Constraints

- Никогда не выполняй разрушительные команды без подтверждения
- Не обращайся к паролям, ключам, секретам
- Уважай приватность пользователя
- Не уходи в бесконечные циклы — проверяй результат и корректируйся
"""

# ===== WebUI-интеграция (U-01/T-09): список и текущая роль =====
import threading

_CURRENT_ROLE = "assistant"
_ROLE_LOCK = threading.Lock()


def list_roles() -> list[str]:
    """Возвращает список имён ролей (без .md) из папки roles/."""
    roles_dir = Path(__file__).resolve().parent
    return sorted(p.stem for p in roles_dir.glob("*.md"))


def get_current_role() -> str:
    return _CURRENT_ROLE


def set_current_role(name: str) -> None:
    """Сохраняет выбранную роль (в памяти процесса).

    Реальная загрузка system-prompt в event_loop — в задаче T-09.
    """
    global _CURRENT_ROLE
    with _ROLE_LOCK:
        if name not in list_roles():
            raise ValueError(f"Роль не найдена: {name}")
        _CURRENT_ROLE = name

