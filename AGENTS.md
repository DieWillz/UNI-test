# UNI repository instructions

Work only in the canonical `C:\LLM\UNI\uni` package unless the user explicitly
requests archival or variant code.

## Protected verification invariant

This rule is permanent and fail-closed:

`COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`

- A user-visible task MUST NOT use `success`, `done`, `completed`, or equivalent
  wording/status unless an independent verification decision contains concrete
  evidence.
- If an action ran but verification is missing, unavailable, stale, ambiguous,
  or failed, the terminal status MUST be `not_verified`.
- Low-level `ToolResult.success` means only that a tool call returned normally.
  It MUST NOT be promoted directly to user-visible task success.
- The protected files listed in `.github/CODEOWNERS` MUST NOT be weakened,
  bypassed, deleted, or made optional by an AI agent.
- Any change to this invariant requires explicit approval from the repository
  owner and must strengthen or preserve fail-closed behavior.
- Run `C:\LLM\python312\python.exe scripts\check_verification_invariant.py`
  and the verification tests before claiming the project works.

No test status, model narration, HTTP 200, process existence, or tool return is
evidence by itself. Evidence must describe a fresh observation of the requested
postcondition.

## Mandatory multi-agent synchronization preflight

Before accepting, starting, or resuming development work, every agent MUST complete this sequence in order:

1. MUST read `AGENTS.md` completely.
2. MUST read `docs/handoffs/UNI_MASTER_DIRECTION.md` completely.
3. MUST read `docs/handoffs/UNI_ACTIVE_WORK.md` completely.
4. MUST read the roadmap/spec/handoff for the assigned subsystem.
5. MUST run `git status` and inspect the diff of every file it intends to modify.
6. MUST explicitly acknowledge the revision it has actually reviewed:
   `python -m uni.direction_sync ack --agent "<agent name>"`
7. MUST check ownership for every intended write path:
   `python -m uni.direction_sync check --agent "<agent name>" --path <path>`
8. MUST NOT modify production or test files unless every required check returns `ALLOW / CURRENT`.

A missing ACK, stale revision, unknown agent, malformed coordination registry, malformed ACK state, or ownership conflict is fail-closed. The agent MUST stop the conflicting write instead of bypassing the gate.

Agents MUST NOT auto-ACK merely to clear `STALE_DIRECTION`. ACK is a deliberate statement that the current Master Direction, Active Work registry, and subsystem handoff were re-read and accepted for the current work.

Treat all unknown uncommitted changes as owned by another agent. Do not overwrite, reset, clean, restore, mass-checkout, stash, rebase, merge, or otherwise discard or absorb them.

If a required path is exclusive to another ACTIVE lane, do not edit it. Use an interface, independent file, handoff request, or explicit ownership transfer. A path with no conflicting active exclusive owner may be used only after the normal ACK and ownership check passes.

Owner-approved architectural changes from chat MUST be recorded in `UNI_MASTER_DIRECTION.md` (or a linked subsystem spec) before production implementation so later agents do not depend on private conversation history.

The live assignment registry is `docs/handoffs/UNI_ACTIVE_WORK.md`. Its machine-readable block is authoritative for agent/task/status/ownership/protected-scope/dependency metadata. Preserve other agents' assignments when updating your own lane.
