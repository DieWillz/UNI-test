# ADR-0005: Capability manifest, registry, and router

Status: Accepted

Task: ROUTER-001

Depends on: ADR-0004

## Dependency direction

The only runtime dispatch direction is:

```text
EventLoop -> CapabilityRouter -> Capability
```

Forbidden:

```text
Capability -> Capability
Capability -> CapabilityRouter
Capability -> Planner
Planner -> concrete Capability implementation
```

Multi-capability orchestration belongs to Planner/EventLoop or a declarative
workflow. A capability may own an external library/adapter, but never another
UNI capability instance.

## Parameter models: one source of truth

Every action has one Pydantic v2 parameter model.

- Router validates `Action.params` with that model.
- JSON Schema exposed to the LLM is derived with
  `model_json_schema()`.
- A second manually maintained parameter-schema dictionary is forbidden.

## ActionSpec

Implemented with the capability base contracts.

Fields:

```text
name: full canonical dotted action name
description: non-empty string, maximum 2000 characters
params_model: type[BaseModel], excluded from ordinary serialization
idempotent: bool
expected_duration_s: optional positive float
verification_required: bool
```

`params_json_schema` is derived from `params_model`; it is not stored
independently.

## CapabilityManifest

Fields:

```text
name: canonical capability name
description: non-empty string, maximum 2000 characters
actions: non-empty tuple/list[ActionSpec]
```

Every ActionSpec prefix must equal `CapabilityManifest.name`.

## Capability interface

```text
manifest: CapabilityManifest
async execute(action: Action) -> ActionResult
```

Capability receives a validated Action. It does not receive AgentContext,
Router, Registry, Planner, or another Capability.

## Registry

Registration is atomic: validate the complete candidate manifest and all
conflicts before mutating any index.

Startup registration rejects:

- duplicate capability names;
- duplicate full action names;
- invalid capability or dotted names;
- action prefix/manifest owner mismatch;
- empty action lists;
- missing/non-Pydantic parameter models;
- invalid expected durations.

Registry exposes read-only capability/manifests/action-spec lookup needed by
Router and Planner. It does not execute actions.

A registration/configuration conflict raises a startup configuration exception;
it is not converted to an ActionResult because no user action is executing yet.

## Router

Canonical method:

```text
async route(action: Action) -> ActionResult
```

Algorithm:

1. Resolve the exact full action name in Registry.
2. Unknown action -> permanent failure result with the same action ID.
3. Validate params using ActionSpec.params_model.
4. Invalid params -> permanent failure result with the same action ID.
5. Call Capability.execute exactly once.
6. Validate the returned ActionResult.
7. Return a conforming result unchanged.

If the capability returns a different `action_id`, Router returns a permanent
internal contract-failure result. It does not silently rewrite the ID.

If an unexpected exception escapes Capability, Router returns a permanent
internal failure by default. Known operational exception mapping belongs inside
the capability.

Every Router-produced result includes:

- input `action.id`;
- conforming status/error/error_type;
- timestamp;
- no retry.

Router never:

- retries;
- replans;
- verifies the goal;
- mutates AgentContext;
- calls another action;
- corrects a malformed capability result silently.

`idempotent` and `verification_required` are Planner/verification metadata. They
do not authorize Router behavior beyond one dispatch.

## Planner exposure

Planner receives descriptions and generated JSON Schemas from the same
registered manifests used by Router. This prevents prompt/dispatch drift.

## Enforcement

`scripts/check_architecture.py` rejects imports between concrete files under
`uni/capabilities/`, except imports from the designated base contract module.
Registry is infrastructure and may import the base contract; concrete
capabilities must not import Registry.

## Implementation scope

ROUTER-002 may change only:

```text
uni/capabilities/base.py
uni/capabilities/registry.py
uni/capabilities/router.py
tests/unit/test_capability_manifest.py
tests/unit/test_capability_router.py
scripts/check_architecture.py
```

Existing concrete capability migration is a later scoped task.
