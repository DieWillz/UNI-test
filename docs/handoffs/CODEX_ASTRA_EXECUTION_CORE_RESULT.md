STATUS
PARTIAL — implementation in progress; no tests or runtime checks executed.

CHANGED
This handoff and CODEX_ASTRA_TEST_REQUESTS.md are maintained by Codex Astra / UNI Execution Core.

ARCHITECTURE
Owner directive, 2026-09-12: preserve one OperatorRuntime -> MissionPlanner -> MissionPlan -> MissionExecutor -> fresh Observation -> PostconditionVerifier -> TaskOutcome. Implement deterministic bounded planner input, typed progress and recovery, authoritative STOP and semantic visible execution inside the existing Operator. This records the implementation contract before production changes; it supplements the shared Operator roadmap without changing the canonical architecture.
Every planner request, including format repair, must fit input plus the actual output reservation. Preserve the full user goal and explicit postconditions; fail closed if essential context cannot fit. Never slice serialized JSON.
STOP invalidates queued and active generations. Replanning is bounded and cannot replay a possibly applied side effect or discard existing postconditions. Progress is a read-only projection of executor state.

LEGACY ADAPTERS
Legacy paths are read-only and remain owner-reserved. No consolidation is authorized in this pass.

KNOWN RISKS
External verification is required. Existing dirty Operator files were transferred intact; other lanes must not be overwritten.

NOT_VERIFIED
All implementation, imports, tests, browser/Windows behavior and runtime acceptance remain unverified.

NEXT
Implement within transferred paths and provide exact test requests for a separate verification agent.
