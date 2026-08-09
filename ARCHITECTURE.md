# UNI Architecture

## Product

UNI is a local modular autonomous agent that turns a natural-language goal into
verified actions on a computer.

The MVP acceptance scenario is:

> Hear or receive a request, open Chrome, find a requested YouTube video, play
> it, verify the result, and report completion.

## Architecture phase

The current architecture is **reactive** (accepted by ADR-0007 Fast-track MVP).
A future phase will introduce a Planner/TaskQueue for autonomous multi-step
execution.

**Current (reactive):** deterministic regex command matching + LLM free-form
with tool-calls, orchestrated by EventLoop. One action per deterministic voice
command; LLM may chain up to 3 tools in free-form mode.

**Planned (autonomous):** Planner → TaskQueue → CapabilityRouter for multi-step
goal decomposition, dependency resolution, retry, and recovery.

## Canonical control loop (current)

```text
User input (voice / text / one-shot command)
  ↓
EventLoop.parse_direct_command (regex — 40+ patterns)
  ├── match → direct execution via ToolExecutor
  └── no match → EventLoop._free_form (LLM with tool-calls)
        ↓
      ToolExecutor.execute(capability.action, args)
        ↓
      Capability.execute(action, **kwargs) → ToolResult
        ↓
      EventLoop formats answer + speaks (if enabled)
```

The runtime lifecycle is:

```text
Listen/Read → Match/Think → Execute → Observe → Speak → Loop
```

## Responsibilities

- `Agent` owns lifecycle, DI wiring, and user interaction. Creates and wires
  Brain, BrowserSession, all Capabilities, CapabilityRegistry, ToolExecutor,
  EventLoop, and AutonomousController.
- `EventLoop` is the central orchestrator: parses direct commands, routes
  free-form LLM dialogue, manages background task slots, audio lock, and
  mixed voice+text input.
- `Brain` communicates with the configured LLM provider (LM Studio,
  OpenAI-compatible API). Handles tool-calls, Vision, and automatic model
  selection.
- `ToolExecutor` resolves canonical `capability.action` names to capability
  instances and dispatches execution. Currently uses a static routing table;
  planned migration to manifest-based `CapabilityRouter` (ADR-0005).
- `Capability` executes an action and always returns `ToolResult`.
  Implementations: Speech, Browser, Computer, Vision, XToys, Camera, Memory.
- `CapabilityRegistry` holds registered capabilities by name. Used by
  ToolExecutor for dispatch.
- `WorkingMemory` stores bounded runtime context: dialogue pairs, explicit
  facts, with secret redaction and atomic writes.
- `SessionLogger` timestamps user input, actions, results, thoughts, speech,
  camera/screenshot events under a session directory.

## Dependency rules

```text
Agent → EventLoop / Brain / CapabilityRegistry / ToolExecutor / BrowserSession
EventLoop → Brain / CapabilityRegistry / ToolExecutor / WorkingMemory
ToolExecutor → CapabilityRegistry → Capability
Capability → contracts + external adapter (Playwright, pyautogui, cv2, etc.)
```

Forbidden dependencies:

- Capability → another Capability
- Capability → Planner
- Executor → Planner
- Capability → concrete implementation of another capability
- Canonical package → archived/reference implementation

## Contract policy

The canonical contracts live in `uni/contracts.py` and are defined by accepted
ADR-0004. Capability routing is defined by accepted ADR-0005 (manifest-based
router planned; static routing table used currently).

All action names use `capability.action` (e.g. `browser.navigate`,
`xtoys.set_intensity`). Legacy underscore names (`browser_navigate`) are
normalized at the `ToolExecutor.canonical_name` boundary.

An architectural contract can change only after an ADR is accepted.

## Planned migrations

| Component | Current | Target | ADR |
|---|---|---|---|
| Planning | Regex + LLM free-form | Planner → TaskQueue | ADR-0004, PLAN-001 |
| Routing | Static `_ROUTING` dict | Manifest-based CapabilityRouter | ADR-0005, ROUTER-002 |
| State | `AgentState` enum + scattered fields | `AgentContext` (Pydantic model) | ADR-0004, CORE-002 |
| Results | `ToolResult` only | `ActionResult` with verification metadata | ADR-0004, CORE-002 |
| Event loop | Reactive direct-command loop | Autonomous Planner-integrated loop | INTEGRATE-001 |
