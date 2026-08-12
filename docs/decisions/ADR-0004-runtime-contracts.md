# ADR-0004: Canonical runtime contracts

Status: Accepted

Task: CORE-001

## Decision

UNI uses one Pydantic v2 contract family in `uni/contracts.py`. The
dataclass contracts in `planner_interface.py` and public `ToolResult` are
legacy migration sources, not parallel contracts.

## Common types

```text
ResultStatus = success | failure | timeout | cancelled
ErrorType    = none | transient | permanent | timeout
TaskStatus   = pending | running | completed | failed | cancelled
```

Identifiers are UUID values serialized as strings. Timestamps are Unix seconds
as non-negative floats until a later migration ADR changes the format.

Canonical action names match:

```text
^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$
```

## Action

Fields:

```text
id: UUID
name: canonical dotted action name
params: dict[str, JsonValue]
depends_on: list[UUID]
priority: integer 0..2
```

Rules:

- Planner creates `id` once.
- Router, queue, and capability never replace it.
- `depends_on` contains resolved Action IDs, never LLM-local step numbers.
- duplicate/self dependencies are invalid.
- manifest parameter validation occurs after plan parsing and before dispatch.

## VerificationResult

Fields:

```text
passed: bool
note: string, maximum 1000 characters
timestamp: non-negative Unix seconds
observation_ref: optional string, maximum 2048 characters
```

The presence of `VerificationResult` means verification ran. Absence means
"not verified", never implicit success.

## ActionResult

Fields:

```text
action_id: UUID
status: ResultStatus
error_type: ErrorType
data: optional JsonValue
artifact_ref: optional string, maximum 2048 characters
error: optional string, maximum 4000 characters
verification: optional VerificationResult
timestamp: non-negative Unix seconds
```

`data`, when present, must serialize as UTF-8 JSON to at most 65,536 bytes.
Larger data is stored externally and referenced through `artifact_ref`.

Invariant matrix:

| status | error_type | error |
|---|---|---|
| success | none | must be absent |
| failure | transient or permanent | required |
| timeout | timeout | required |
| cancelled | none | cancellation reason required |

No other combination is valid.

A success with `verification.passed=false` remains an execution success but is
not accepted as goal progress by recovery/verification policy.

## Observation

Fields:

```text
source: capability name
summary: string, maximum 2000 characters
artifact_ref: optional string, maximum 2048 characters
timestamp: non-negative Unix seconds
```

Binary data and complete page dumps are never embedded.

## Task

Fields:

```text
action: Action
status: TaskStatus
retry_count: non-negative integer
max_retries: non-negative integer
sequence: non-negative integer used for stable queue ordering
```

`Task.id` is a computed read-only property returning `action.id`. It is not a
stored input field and is never independently generated.

`depends_on` and `priority` are read from the contained Action.

Result-to-task mapping:

- accepted success -> completed;
- unrecovered failure/timeout -> failed;
- cancelled -> cancelled;
- retry/replan decisions do not mark completed.

Only TaskQueue mutates task status and retry count.

## AgentContext

`AgentContext` is serializable goal state, not a service container.

Fields:

```text
goal: non-empty string, maximum 4000 characters
state: AgentState-compatible string/enum
history: list[ActionResult]
last_observation: optional Observation
current_action_id: optional UUID
replans_used: non-negative integer
goal_verified: bool
```

Runtime services (`TaskQueue`, `WorkingMemory`, Router, LLM client) are injected
into Agent/EventLoop separately and are not Pydantic fields.

Ownership:

| Field | Only writer |
|---|---|
| goal | Agent |
| state | EventLoop |
| history | EventLoop, append-only |
| last_observation | EventLoop |
| current_action_id | EventLoop |
| replans_used | Planner through EventLoop transition |
| goal_verified | EventLoop after verification |

Capabilities and Router never receive AgentContext.

## Dependency resolution

LLM output uses local positive integer `step` values. Planner:

1. validates unique steps;
2. allocates each Action UUID;
3. builds `step -> Action.id`;
4. resolves every dependency;
5. rejects unknown, self, duplicate, and cyclic dependencies;
6. constructs Tasks only after successful resolution.

TaskQueue never sees step numbers.

## Exceptions and async boundaries

- Capability executes asynchronously and converts known operational failures to
  ActionResult.
- Router executes asynchronously, dispatches once, and converts boundary
  failures to ActionResult.
- An unexpected programming exception is `permanent` by default, not
  automatically retryable.
- Planner may raise typed plan-validation/exhaustion errors for EventLoop to
  transition into replan, waiting-user, or error.
- synchronous external libraries are wrapped inside the owning capability.

## Scope

CORE-002 changes only:

```text
uni/contracts.py
tests/unit/test_contracts.py
```

Migration of capabilities, ToolResult users, Planner, Router, and EventLoop is
performed by later tasks.
