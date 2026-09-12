# GPT UNI Known Good Recovery

STATUS: IMPLEMENTED / TARGETED VERIFICATION PASS / OWNER CHECKPOINT APPROVAL STILL EXTERNAL

AGENT: GPT UNI Known Good Recovery

## Scope

Implemented a standalone Known Good checkpoint subsystem in `uni/checkpoints/`.
It does not import WebUI, DevCoord, Workspace, Operator, or Transports.
Unknown dirty changes in the shared repository were not modified or discarded.

The subsystem deliberately separates agent/test evidence from repository-owner approval.
An agent cannot promote its own test result into Owner Verification.

## Checkpoint levels

### FEATURE_VERIFIED

A feature checkpoint stores explicitly selected repository files as a content-addressed snapshot.
It records the current Git revision, master-direction revision, owner approval, dependencies,
verified tasks/features, test evidence, optional architecture/invariant evidence, and file list.
Selected files may come from a dirty workspace because the snapshot captures their exact bytes.

### PROJECT_KNOWN_GOOD

A project checkpoint references a committed Git tree and revision.
It is accepted only when owner approval, master revision, tests, architecture evidence,
and verification-invariant evidence are all present.
Creation is fail-closed when the workspace is dirty or changes during capture.
The checkpoint stores both `source_git_revision` and the corresponding Git tree hash.

## Checkpoint format

`Checkpoint` metadata contains:

- `id`, `type`, `label`, `created_at`
- `owner_verified_at`, `owner_note`, `owner_approval_ref`
- `master_revision`, `source_git_revision`, `snapshot_ref`
- `verified_tasks`, `verified_features`
- `test_evidence`, `architecture_evidence`
- `verification_invariant_evidence`
- feature-only `dependencies` and `files`

Metadata is JSON under `<store_root>/metadata/`.
Feature snapshots are under `<store_root>/snapshots/<checkpoint-id>/` with a manifest and hashes.
Project snapshots use `git-tree:<tree-hash>` rather than copying an arbitrary dirty workspace.

Metadata loading is strict: required values must be non-empty strings and evidence fields must
be arrays of non-empty strings. Tampered owner approval or malformed evidence fails closed.
Feature manifests are hash-checked and snapshot paths are constrained to the snapshot root.

## Restore safety model

`prepare_restore(checkpoint_id)` is diagnostic only and never mutates the current workspace.
It returns a `RestorePlan` with:

- source checkpoint and target revision
- files that differ from the checkpoint
- files that would disappear when moving back to an older project revision
- current dirty state and dirty-file conflicts
- a separate safe target workspace path
- `activation_allowed=False`

For feature checkpoints, the stored snapshot manifest is validated before planning.
For project checkpoints, the stored Git tree reference is re-derived and compared before planning.
Unknown or malformed checkpoints are rejected.

`create_emergency_snapshot(label)` is available before any future activation stage.
It records HEAD, current dirty-state metadata, a binary patch for tracked changes,
and a tar archive of untracked files without resetting, cleaning, checking out, or restoring them.

Actual mutation of the active checkout is intentionally not part of this subsystem's public API.
A later activation layer must first stage/verify the prepared target in an isolated workspace,
create an emergency snapshot, require explicit activation, and preserve the same fail-closed rules.

## Public API

Import from `uni.checkpoints`:

- `CheckpointManager.list_checkpoints()`
- `CheckpointManager.inspect_checkpoint(checkpoint_id)`
- `CheckpointManager.create_feature_checkpoint(...)`
- `CheckpointManager.create_project_checkpoint(...)`
- `CheckpointManager.prepare_restore(checkpoint_id)`
- `CheckpointManager.create_emergency_snapshot(label)`

Public models/errors include `Checkpoint`, `CheckpointType`, `RestorePlan`,
`EmergencySnapshot`, `CheckpointError`, `CheckpointSafetyError`, and `UnknownCheckpointError`.

## Git safety boundary

`GitBackend` is read-mostly and uses an explicit command allowlist:
`rev-parse`, `status`, `diff`, and `ls-tree`.

No implementation path invokes `git reset`, `git clean`, `git checkout`, or `git restore`.
The current repository is never rolled back as part of checkpoint tests.
All mutation-oriented recovery tests use temporary Git repositories/fixtures.

## Tests

`tests/checkpoints/test_manager.py` covers the requested TDD contract plus tamper/race hardening:

1. no Owner Verification -> no Project Known Good
2. dirty project state -> fail closed
3. master revision preserved
4. prepare_restore is workspace-read-only
5. restore plan lists changed/removal candidates
6. unknown checkpoint blocked
7. current workspace preserved and emergency snapshot is non-destructive
8. feature/project checkpoint semantics differ
9. destructive Git commands are not invoked by the backend
Additional coverage verifies:

- feature snapshots can preserve an explicitly owner-verified dirty file
- tampered owner metadata is rejected
- scalar/malformed evidence metadata is rejected
- feature snapshot path traversal is rejected
- PROJECT_KNOWN_GOOD fails closed if the workspace changes during capture

## Limitations

This subsystem does not declare the current `C:\LLM\UNI` workspace Known Good.
The shared workspace is currently dirty and therefore cannot pass Project Known Good creation.
A feature checkpoint still requires a concrete external owner-approval reference supplied by the caller.
The module stores approval evidence; it does not invent or infer owner approval from tests or agent text.

There is no destructive "activate current checkout" method by design.
Activation belongs in a separately reviewed integration stage after isolated restore verification.
Emergency snapshots preserve tracked changes and untracked files; ignored files are outside that snapshot contract.

## Integration points

Workspace backend can instantiate `CheckpointManager(repo_root, store_root=...)` and expose the
read-only list/inspect/prepare operations directly without depending on WebUI.
Owner-approval workflow should pass a durable approval reference and timestamp into create methods.
MAWC/Workspace should provide the current master-direction revision rather than fabricating it.
A future activation coordinator should consume `RestorePlan`, stage the target separately, verify it,
call `create_emergency_snapshot()`, and only then request explicit owner activation.

## Verification evidence

Final command outputs are recorded after implementation in the verification section below.

Verification run after implementation:

- `python -m compileall -q uni/checkpoints tests/checkpoints` -> PASS
- `pytest tests/checkpoints tests/test_verification_invariant.py -q` -> `20 passed`
- `python scripts/check_verification_invariant.py` -> `[PASS] COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED invariant`
- static scan of `uni/checkpoints/*.py` -> no `git reset`, `git clean`, `git checkout`, or `git restore` invocation patterns

The current shared workspace remains dirty from parallel agents, so no real `PROJECT_KNOWN_GOOD`
checkpoint was created for `C:\LLM\UNI`, and no rollback/activation was executed there.
