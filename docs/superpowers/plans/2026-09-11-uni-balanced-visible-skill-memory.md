# UNI Balanced Visible + Verified Skill Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make UNI visibly perform normal user-facing interactions while retaining structural perception/verification and learning reusable workflows only from independently VERIFIED missions.

**Architecture:** Add a deterministic execution-policy layer and focused visible-action driver inside `uni/operator/`, then integrate them into the existing single `MissionExecutor`. Add a separate SQLite-backed verified-skill subsystem that compiles trusted learned recipes back into ordinary `MissionPlan` objects, preserving existing permissions, STOP/InputBroker and verification gates.

**Tech Stack:** Python 3.12, asyncio, Pydantic models already used by UNI, Windows UIA/pyautogui through existing `ComputerCapability`, Playwright through existing `BrowserSession`, stdlib `sqlite3`, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-11-uni-balanced-visible-skill-memory-design.md`

## Global Constraints

- Canonical repo/package only: `C:\LLM\UNI\uni`.
- Permanent invariant: `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`.
- Default execution mode: `BALANCED_VISIBLE`.
- Never reuse learned coordinates without fresh semantic target/context validation.
- Only `TaskOutcome.status == VERIFIED` may create or strengthen durable skills.
- Do not duplicate Brain, Agent, Operator, BrowserSession or ComputerCapability.
- Before every edit: `git status` + diff of the exact target file; unknown edits belong to another agent.
- No reset/clean/mass checkout/restore of the shared working tree.
- In the shared dirty workspace, do not `git add`, `git commit` or `git push` unless the repository owner explicitly authorizes it.

---
### Task 1: Deterministic execution policy

**Files:**
- Create: `uni/operator/execution_policy.py`
- Create: `tests/operator/test_execution_policy.py`
- Read only: `uni/operator/action_registry.py`, `uni/operator/models.py`

**Interfaces:**
- Produces: `ExecutionMode`, `ExecutionMethod`, `ExecutionDecision`, `ExecutionPolicy.decide(...)`.
- Consumes: `ActionSpec`, optional `UIElement`, and simple capability facts; no provider imports.

- [ ] **Step 1: Write the failing policy tests**

```python
from uni.operator.execution_policy import ExecutionMode, ExecutionMethod, ExecutionPolicy


def test_balanced_visible_prefers_visible_for_desktop_click(action_spec, button):
    decision = ExecutionPolicy().decide(ExecutionMode.BALANCED_VISIBLE, action_spec, target=button)
    assert decision.method is ExecutionMethod.VISIBLE_PHYSICAL


def test_balanced_visible_keeps_read_direct(read_spec, button):
    decision = ExecutionPolicy().decide(ExecutionMode.BALANCED_VISIBLE, read_spec, target=button)
    assert decision.method is ExecutionMethod.DIRECT_STRUCTURAL
```
- [ ] **Step 2: Run RED**

Run:
`C:\LLM\python312\python.exe -m pytest tests\operator\test_execution_policy.py -q`

Expected: import/definition failure because `execution_policy.py` does not exist yet.

- [ ] **Step 3: Implement the minimal policy types**

```python
class ExecutionMode(str, Enum):
    VISIBLE = "visible"
    BALANCED_VISIBLE = "balanced_visible"
    FAST = "fast"

class ExecutionMethod(str, Enum):
    DIRECT_STRUCTURAL = "direct_structural"
    VISIBLE_PHYSICAL = "visible_physical"
    SAFE_FALLBACK = "safe_fallback"

@dataclass(frozen=True)
class ExecutionDecision:
    method: ExecutionMethod
    reason: str
    requires_screen_target: bool = False
    direct_fallback_allowed: bool = True
```

Policy rules must classify read/inspect/filesystem as direct and normal desktop click/fill/check/uncheck/select as visible in `BALANCED_VISIBLE` only when a trustworthy bbox exists.
- [ ] **Step 4: Run GREEN and policy matrix tests**

Run:
`C:\LLM\python312\python.exe -m pytest tests\operator\test_execution_policy.py -q`

Expected: PASS, including `VISIBLE`, `BALANCED_VISIBLE`, `FAST`, missing-bbox and ambiguous-target cases.

- [ ] **Step 5: Verify no unrelated changes**

Run:
`git diff --check -- uni/operator/execution_policy.py tests/operator/test_execution_policy.py`

Expected: no whitespace errors. Do not commit in the shared dirty workspace.

### Task 2: Visible Windows action driver

**Files:**
- Create: `uni/operator/visible_actions.py`
- Create: `tests/operator/test_visible_actions.py`
- Read only: `uni/operator/input_broker.py`, `uni/operator/windows_provider.py`, `uni/capabilities/computer.py`

**Interfaces:**
- Consumes: resolved `UIElement`, `ComputerCapability`-compatible executor and `InputBroker` lease owned by the caller.
- Produces: `VisibleActionDriver.click(element)`, `fill(element, text)`, `toggle(element, checked)`, `select(element, value)` returning `ToolResult`.

- [ ] **Step 1: Write failing visible-click and fill tests**
```python
@pytest.mark.asyncio
async def test_visible_click_moves_then_clicks(button, fake_computer):
    driver = VisibleActionDriver(fake_computer)
    result = await driver.click(button)
    assert result.success is True
    assert [name for name, _ in fake_computer.calls[:2]] == ["move_human", "click_human"]

@pytest.mark.asyncio
async def test_visible_fill_focuses_then_types(textbox, fake_computer):
    driver = VisibleActionDriver(fake_computer)
    result = await driver.fill(textbox, "UNI")
    assert result.success is True
    assert any(name == "click_human" for name, _ in fake_computer.calls)
    assert any(name in {"type_unicode", "paste"} for name, _ in fake_computer.calls)
```

- [ ] **Step 2: Run RED**

Run:
`C:\LLM\python312\python.exe -m pytest tests\operator\test_visible_actions.py -q`

Expected: missing `VisibleActionDriver`.

- [ ] **Step 3: Implement visible actions using fresh bbox centers**

Reject `element.bbox is None`, disabled targets and sensitive fill targets. Use existing human-motion actions from `ComputerCapability`; do not call `pyautogui` directly from the new driver.
