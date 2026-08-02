# ADR-0008: AI Council (development consensus) and bounded autonomy

- Status: accepted
- Date: 2026-08-02
- Supersedes: COUNCIL-001 (spec), implements COUNCIL-002 (report-only council)

## Context

The coordinator wants to stop manually copy-pasting the concept between AI
participants. A module should automate the consensus loop: deliver a brief
(ideas / files / tasks) to each participant and collect their replies + signatures,
using the cheapest transport — API when the model is free/local, browser automation
when it is a paid closed web chat.

MANIFESTO v2.5 already mandates:
- adviser calls are independent, bounded, failure-tolerant (§3.3, COUNCIL-001);
- consensus is separated from evidence verification;
- browser adviser output is untrusted data (§7);
- idle/safe actions are explicit; denied schemes and prompt injection cannot create
  actions (§6, AUTONOMY-001).

## Decision

1. Add `uni/council/` implementing a **report-only** council:
   - `provider.py` — `ApiProvider` (OpenAI-compatible HTTP) and `BrowserProvider`
     (Playwright automation of a web chat). Both return `ParticipantReply` marked
     `via="api"|"browser"`.
   - `participants.py` — registry of participants; `transport: api|browser` decides
     the channel. API is preferred when the endpoint is free/local; browser is the
     fallback for paid/closed models.
   - `round.py` — `CouncilRound.run()` fans out the brief to all participants in
     parallel (bounded by a semaphore), collects untrusted replies, extracts trailing
     `Name = ...` signature lines, then asks a local Critic and local Coordinator to
     synthesize. Writes one markdown report + JSON meta under `artifacts_dir`.
   - `run.py` — CLI: `python -m uni.council.run --topic ... --brief-file ...`.
2. **Untrusted data contract**: participant text is never executed and never calls a
   UNI tool. Signatures are recorded verbatim but flagged unverified until the human
   coordinator accepts them (per MANIFESTO §11: a model signature is its position in its
   own session, not a joint agreement between models).
3. **Separate browser profile** for web-AI transport so it never mixes with the user's
   bank / mail / intimate sessions (MANIFESTO §7).
4. **No secrets** are sent to any participant; API keys are redacted from the stored
   spec; the local manifest is never transmitted.
5. Bounds: concurrency ≤ 8, per-participant timeout ≤ 600s, brain/model failures are
   reported as errors and never abort the whole round.

## Consequences

- Positive: the manual consensus loop is replaced by one command; artifacts are
  local-first and auditable; ethics invariants from v2.5 are preserved.
- Negative: browser transport depends on third-party DOM that may change; such
  participants are best-effort and their failures are non-fatal.
- Councillor output does not change runtime code. Turning a consensus into an action
  still requires COORDINATOR (human) acceptance and a normal ADR/task flow.

## Compliance with manifest MUSTs

- §3.1 Purpose Integrity: council never substitutes hidden goals; it only relays the
  coordinator's explicit brief.
- §3.3 Policy Engine: council has no tool-call capability, so it cannot bypass policy.
- §7 Browser adapter: separate profile, untrusted output, no secrets, off by default
  unless invoked.
