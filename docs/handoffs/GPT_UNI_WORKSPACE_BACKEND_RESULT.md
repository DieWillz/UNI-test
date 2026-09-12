# GPT UNI Workspace Backend Result

## Scope

Implemented the read/model/owner-verification backend facade for the future unified admin section `Разработка / Workspace`.

Created only:
- `uni/workspace/**`
- `tests/workspace/**`
- this handoff

Did not modify `uni/devcoord/**`, `uni/webui/**`, `uni/checkpoints/**`, `uni/operator/**`, or `uni/transports/**`.

`WorkspaceService` is deliberately not a coordinator. MAWC/DevCoord remains execution truth. The workspace package consumes data through Protocol boundaries and exposes normalized views for UI/API consumers.

## Public imports

WebUI/integration code should import from `uni.workspace`:

```python
from uni.workspace import (
    AgentSource, AgentWorkspaceView,
    CheckpointSource, CheckpointView,
    RevisionSource, TaskSource, TaskWorkspaceView,
    WorkspaceOverview, WorkspaceService,
    WorkspaceValidationError, UnknownWorkspaceTask,
)
```

## Exact service interface

```python
service = WorkspaceService(
    agent_source=agent_source,          # AgentSource
    task_source=task_source,            # TaskSource
    checkpoint_source=checkpoint_source,# CheckpointSource
    revision_source=revision_source,    # RevisionSource
)

overview: WorkspaceOverview = service.get_overview()
payload: dict = overview.to_dict()

updated_task: TaskWorkspaceView = service.record_owner_verification(
    task_id,
    verified=True,                      # False = reject
    note="Проверил, функционал реально работает",
    owner_identity="owner-id",
)
```

`get_overview().to_dict()` is the backend payload for logical `GET /api/workspace/overview`:

```json
{
  "master_revision": "...",
  "updated_at": "...",
  "agents": [],
  "tasks": [],
  "checkpoints": []
}
```

## Exact source Protocols

```python
class AgentSource(Protocol):
    def list_agents(self) -> Sequence[AgentWorkspaceView]: ...

class TaskSource(Protocol):
    def list_tasks(self) -> Sequence[TaskWorkspaceView]: ...
    def get_task(self, task_id: str) -> TaskWorkspaceView | None: ...
    def record_owner_verification(
        self,
        task_id: str,
        record: OwnerVerificationRecord,
        *,
        status: str,
    ) -> TaskWorkspaceView: ...

class CheckpointSource(Protocol):
    def list_checkpoints(self) -> Sequence[CheckpointView]: ...

class RevisionSource(Protocol):
    def get_master_revision(self) -> str: ...
```

The MAWC adapter should live outside `uni/workspace` and map existing DevCoord sessions/tasks/leases into the normalized views. This keeps `uni.workspace` free of DevCoord imports and avoids cyclic dependencies.

## Normalized view fields

`AgentWorkspaceView`:
`id`, `name`, `task`, `status`, `progress`, `updated_at`, `direction_revision`, `ack_revision`, `stale`, `owned_paths`, `blockers`.

`TaskWorkspaceView`:
`id`, `title`, `description`, `agent`, `status`, `progress`, `updated_at`, `acceptance_total`, `acceptance_passed`, `agent_verified`, `owner_verified`, `owner_verified_at`, `owner_note`, `dependencies`, plus verification metadata: `owner_verified_by`, `task_revision`, `verification_evidence_ref`, `source_revision`, `owner_verification`.

`CheckpointView`:
`id`, `label`, `created_at`, `reference`, `owner_verified`, `current`, `features`, `test_evidence`.

Checkpoint adapter mapping from current `uni.checkpoints.Checkpoint` should normally be:
- `reference = checkpoint.snapshot_ref`
- `owner_verified = bool(checkpoint.owner_verified_at)`
- `features = checkpoint.verified_features`
- `test_evidence = checkpoint.test_evidence`
- `current` determined by adapter against the current git/tree reference; the facade does not guess it.

No source data means empty lists. The backend never synthesizes placeholder tasks, agents, or checkpoints.

## Progress and owner verification rules

Progress is calculated only from acceptance + verification gates:
- `5/7 -> 71`
- complete acceptance + agent verification without owner approval -> `99`
- `100` only when acceptance is complete, agent verification is complete, and owner verification is true.

APPROVE is fail-closed. Before writing approval the task must have complete acceptance, completed agent verification, a task revision, verification evidence reference, and a source/master revision. The persisted record contains owner identity, UTC timestamp, note, task revision, verification evidence reference, and source revision.

REJECT stores the same owner decision record with `verified=False` and requests source status `development`. The source must return the persisted decision; otherwise `WorkspaceSourceError` is raised.

HTTP routes were intentionally not registered because `uni/webui/**` belongs to another active lane. WebUI can implement logical POST `/api/workspace/tasks/{task_id}/owner-verification` by validating JSON `verified` + `note`, resolving authenticated owner identity server-side, and calling `record_owner_verification()`.

## Verification evidence

Fresh verification after implementation:
- `C:\LLM\python312\python.exe -m pytest tests\workspace -q` -> `9 passed`
- `C:\LLM\python312\python.exe scripts\check_verification_invariant.py` -> `[PASS] COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED invariant`
- `C:\LLM\python312\python.exe -m uni.check_architecture --strict` -> `0 errors, 0 warnings`

Coordination note: `GPT UNI Workspace Backend` was not present as an assignment in the machine-readable `UNI_ACTIVE_WORK.md` during preflight. The new `uni/workspace/**` and `tests/workspace/**` paths did not overlap any active exclusive ownership. The registry was not edited because it belongs to the project coordination lane.
