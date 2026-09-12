from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from uni.capabilities.computer import ComputerCapability
from uni.contracts import TaskStatus, VerificationStatus
from uni.operator.executor import MissionExecutor
from uni.operator.file_provider import FileProvider
from uni.operator.models import MissionPlan, PlanStep, Postcondition, SceneSnapshot, TargetSpec
from uni.operator.perception import PerceptionBroker
from uni.operator.windows_provider import WindowsProvider

_RUN_LIVE = os.name == "nt" and os.getenv("UNI_RUN_WINDOWS_E2E") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN_LIVE,
    reason="set UNI_RUN_WINDOWS_E2E=1 on an interactive Windows desktop",
)


class _NullBrowser:
    async def inspect(self) -> SceneSnapshot:
        return SceneSnapshot(errors=["dom_not_used"])

class _UnusedPlanner:
    async def plan(self, *args, **kwargs):
        raise AssertionError("prebuilt plan expected")


class _UnusedToolExecutor:
    async def execute(self, *args, **kwargs):
        raise AssertionError("operator provider expected")


async def _wait_for_window(computer: ComputerCapability, title: str, timeout: float = 8.0):
    deadline = asyncio.get_running_loop().time() + timeout
    last = None
    while asyncio.get_running_loop().time() < deadline:
        last = await computer.execute("focus_window", title=title)
        if last.success:
            return last
        await asyncio.sleep(0.1)
    raise AssertionError(f"test window did not become focusable: {getattr(last, 'message', '')}")


@pytest.mark.asyncio
async def test_mission_executor_windows_uia_to_filesystem(tmp_path: Path) -> None:
    script = Path(__file__).with_name("fixtures") / "winforms_operator_fixture.ps1"
    output = tmp_path / "saved.txt"
    title = f"UNI Operator E2E {uuid4().hex}"
    text = "UNI Night MissionExecutor E2E"
    proc = subprocess.Popen(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-OutputPath", str(output), "-Title", title,
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        computer = ComputerCapability(
            use_uia=True,
            use_human_motion=False,
            action_badge_enabled=False,
            verified_physical=True,
        )
        await _wait_for_window(computer, title)
        windows = WindowsProvider(computer)
        perception = PerceptionBroker(
            _NullBrowser(), windows, vision=None, ocr_finder=lambda _: None,
        )
        files = FileProvider()
        executor = MissionExecutor(
            planner=_UnusedPlanner(), perception=perception,
            tool_executor=_UnusedToolExecutor(), windows_provider=windows,
            file_provider=files,
        )
        plan = MissionPlan(goal="write and save", steps=[
            PlanStep(
                id="fill",
                action="operator.desktop.fill",
                target=TargetSpec(name="Document", role="textbox", exact=True),
                params={"text": text},
                retry_budget=0,
                postcondition=Postcondition(
                    kind="element.value_equals", params={"value": text},
                ),
            ),
            PlanStep(
                id="save",
                action="operator.desktop.click",
                dependencies=["fill"],
                target=TargetSpec(name="Save", role="button", exact=True),
                retry_budget=0,
                postcondition=Postcondition(
                    kind="file.text_equals",
                    params={"path": str(output), "text": text},
                ),
            ),
        ])
        outcome = await executor.run("write and save", plan=plan)
        assert outcome.status is TaskStatus.VERIFIED
        assert outcome.verification.status is VerificationStatus.VERIFIED
        assert [item.action.name for item in outcome.actions] == [
            "operator.desktop.fill",
            "operator.desktop.click",
        ]
        assert all(item.verified for item in outcome.actions)
        assert output.read_text(encoding="utf-8") == text
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


@pytest.mark.asyncio
async def test_windows_provider_real_checkbox_and_combobox(tmp_path: Path) -> None:
    script = Path(__file__).with_name("fixtures") / "winforms_operator_fixture.ps1"
    output = tmp_path / "unused.txt"
    title = f"UNI Operator Controls {uuid4().hex}"
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-OutputPath", str(output), "-Title", title],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        computer = ComputerCapability(use_uia=True, use_human_motion=False,
                                      action_badge_enabled=False, verified_physical=True)
        await _wait_for_window(computer, title)
        windows = WindowsProvider(computer)
        checked = await windows.act("check", target=TargetSpec(name="Remember me", role="checkbox", exact=True))
        assert checked.success is True
        scene = await windows.inspect()
        assert windows.resolve(TargetSpec(name="Remember me", role="checkbox", exact=True), scene).checked is True
        selected = await windows.act("select", target=TargetSpec(name="Theme", role="combobox", exact=True), value="Light")
        assert selected.success is True
        scene = await windows.inspect()
        assert windows.resolve(TargetSpec(name="Theme", role="combobox", exact=True), scene).value == "Light"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=3)


@pytest.mark.asyncio
async def test_windows_provider_reads_document_control(tmp_path: Path) -> None:
    script = Path(__file__).with_name("fixtures") / "winforms_operator_fixture.ps1"
    output = tmp_path / "unused-document.txt"
    title = f"UNI Operator Document {uuid4().hex}"
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-OutputPath", str(output), "-Title", title],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        computer = ComputerCapability(use_uia=True, use_human_motion=False,
                                      action_badge_enabled=False, verified_physical=True)
        await _wait_for_window(computer, title)
        windows = WindowsProvider(computer)
        scene = await windows.inspect()
        notes = windows.resolve(TargetSpec(name="Notes", role="document", exact=True), scene)
        assert notes.value == "Document seed"
        result = await windows.act("read", target=TargetSpec(name="Notes", role="document", exact=True))
        assert result.success is True
        assert result.data["value"] == "Document seed"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=3)
