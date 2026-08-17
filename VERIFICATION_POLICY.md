# UNI Verification Policy

Normative invariant:

`COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`

`verified` is the only successful terminal task status. `success`, `done`, and
`completed` are not valid terminal task statuses. A low-level action may return
`ToolResult.success=True`, but the enclosing task remains `not_verified` until
an independent verifier records at least one concrete evidence item.

Verification evidence must be fresh, tied to the requested postcondition, and
produced after the action. Examples include a read-after-write value, a fresh
screen observation showing the target state, a server response followed by a
separate state query, or a device status observation correlated to the command.

If verification cannot run, the correct status is `not_verified`. It is never
permitted to infer completion from model text, HTTP 200, a live PID, a green
unit test, or the absence of an exception.

Enforcement layers:

1. `uni/contracts.py` rejects `verified` without evidence.
2. `uni/config.py` rejects disabled verification.
3. User-facing WebUI and mission endpoints publish explicit verification state.
4. `scripts/check_verification_invariant.py` fails on known bypass patterns.
5. Tests and CI execute the invariant checker.
6. `.github/CODEOWNERS` requires owner review for protected files when branch
   protection and required reviews are enabled on GitHub.

Local files cannot be made absolutely immutable against an administrator or a
process with unrestricted write access. Durable enforcement therefore also
requires remote branch protection, required CI, required CODEOWNER review, and
restricted direct pushes to the protected branch.
