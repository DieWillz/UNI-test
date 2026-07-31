# UNI Architecture

## Product

UNI is a local modular autonomous agent that turns a natural-language goal into
verified actions on a computer.

The MVP acceptance scenario is:

> Hear or receive a request, open Chrome, find a requested YouTube video, play
> it, verify the result, and report completion.

## Canonical control loop

```text
User
  ↓
Agent
  ↓
AgentContext
  ↓
Planner → TaskQueue
  ↓
Action
  ↓
CapabilityRouter
  ↓
Capability → OS / application
  ↓
ActionResult + Observation
  └──────────────→ AgentContext → Planner
```

The runtime lifecycle is:

```text
Observe → Think → Plan → Speak → Act → Verify → Recover
```

## Responsibilities

- `Agent` owns lifecycle and user interaction.
- `AgentContext` is the single serializable mutable goal state passed through
  the loop. Runtime services such as TaskQueue, WorkingMemory, Router, and the
  LLM client are injected into Agent/EventLoop separately.
- `Planner` decomposes goals and replans only when semantic judgment is needed.
- `TaskQueue` handles dependencies, priorities, and ready tasks deterministically.
- `CapabilityRouter` resolves a canonical action name to one capability.
- `Capability` executes an action and always returns `ActionResult`.
- `WorkingMemory` stores bounded runtime context.
- `LLMClient` communicates with the configured model provider.
- Markdown files provide roles, skills, workflows, and domain knowledge.

## Dependency rules

```text
Agent → Planner / Router / Context
Planner → contracts + capability manifests
Router → contracts + capability registry
Capability → contracts + external adapter
```

Forbidden dependencies:

- Capability → another Capability
- Capability → Planner
- Executor → Planner
- Planner → concrete Browser/Computer/Speech/Vision implementation
- Canonical package → archived implementation

## Contract policy

The canonical contracts live in `uni/contracts.py` and are defined by accepted
ADR-0004. Capability routing is defined by accepted ADR-0005.

All action names will use `capability.action`. Legacy underscore names must be
adapted at one boundary during migration and then removed.

An architectural contract can change only after an ADR is accepted.
