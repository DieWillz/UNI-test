from __future__ import annotations

import pytest

from uni.operator.action_registry import ActionSpec
from uni.operator.models import PermissionLevel
from uni.operator.permissions import MissionPermissions, PermissionDenied, PermissionGate


def spec(level: PermissionLevel) -> ActionSpec:
    return ActionSpec(name="demo.action", capability="demo", action="action",
                      description="demo", permission=level)


def test_read_and_local_reversible_are_allowed_by_default() -> None:
    gate = PermissionGate()
    gate.require(spec(PermissionLevel.READ), MissionPermissions())
    gate.require(spec(PermissionLevel.LOCAL_REVERSIBLE), MissionPermissions())


def test_external_effect_requires_explicit_approval() -> None:
    gate = PermissionGate()
    with pytest.raises(PermissionDenied):
        gate.require(spec(PermissionLevel.EXTERNAL_EFFECT), MissionPermissions())
    gate.require(spec(PermissionLevel.EXTERNAL_EFFECT), MissionPermissions(external_effects=True))
