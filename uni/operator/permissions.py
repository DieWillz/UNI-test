from __future__ import annotations

from dataclasses import dataclass

from .action_registry import ActionSpec
from .models import PermissionLevel


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class MissionPermissions:
    external_effects: bool = False
    critical: bool = False


class PermissionGate:
    """Separates capability from authorization for one mission."""

    def require(self, spec: ActionSpec, permissions: MissionPermissions) -> None:
        level = spec.permission
        if level in {PermissionLevel.READ, PermissionLevel.LOCAL_REVERSIBLE}:
            return
        if level is PermissionLevel.EXTERNAL_EFFECT:
            if permissions.external_effects:
                return
            raise PermissionDenied(f"external_effect_requires_approval: {spec.name}")
        if level is PermissionLevel.CRITICAL:
            if permissions.critical:
                return
            raise PermissionDenied(f"critical_action_requires_approval: {spec.name}")
        raise PermissionDenied(f"unsupported_permission_level: {level}")
