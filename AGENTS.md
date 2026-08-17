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
