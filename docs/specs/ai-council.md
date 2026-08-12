# AI Council — implementation specification draft

Status: Proposed; depends on ADR-0008

## Delivery A: council report in interactive mode

Command examples:

```text
Юни, спроси совет ИИ: как ускорить распознавание интерфейса?
Юни, собери совет по способам заработка в интернете без вложений.
```

Algorithm:

1. Normalize the goal and redact secrets from context.
2. Select 2–5 enabled providers with distinct provider IDs.
3. Fan out identical structured requests concurrently.
4. Apply per-provider timeout and response-size limits.
5. Require at least two valid structured opinions.
6. Extract claims and URLs; deduplicate deterministic text fingerprints.
7. Verify important claims against public primary sources where possible.
8. Run one adversarial critic pass over anonymized opinions.
9. Run one synthesizer pass over opinions, criticism, and verified evidence.
10. Validate and persist one bounded `CouncilReport`.
11. Speak a short summary and save the full report in the session log directory.

Default limits:

```yaml
providers_max: 5
providers_min_success: 2
provider_timeout_s: 90
response_chars_max: 12000
critic_calls_max: 1
synthesizer_calls_max: 1
council_deadline_s: 150
```

No provider may invoke UNI tools. Provider output is parsed as untrusted data.

## Delivery B: bounded experiment queue

Depends on the repaired Planner, canonical Router, recovery policy, and
verification policy.

For each ranked option, generate an `ExperimentProposal` containing a hypothesis,
safe actions, metric, time/action limits, and confirmation points. A deterministic
policy classifier rejects denied steps and splits the rest at the first required
confirmation.

Example for “find a way to earn online”:

1. Research demand and competition using public sources.
2. Rank options by legality, capital, time-to-signal, user fit, and automation.
3. Produce local sample deliverables for the top three options.
4. Run offline quality checks and public read-only market comparisons.
5. Discard options that fail their stated metric.
6. Present the best surviving public action and pause before publishing,
   outreach, account creation, or financial commitment.

## Delivery C: preemptible idle learning

An `IdleLearningScheduler` observes only local activity timestamps. It starts a
session when all guards are true:

```text
idle_for >= idle_delay
no user-input task running
no camera or microphone activity
no browser/computer/XToys action running
cooldown elapsed
daily provider and page budgets remain
```

Defaults:

```yaml
enabled: true
idle_delay_s: 900
session_deadline_s: 300
session_topics_max: 1
provider_calls_max: 3
web_pages_max: 6
sessions_per_day_max: 8
cooldown_s: 1800
knowledge_expiry_days: 30
```

User activity sets a cancellation event. Provider and browser adapters must
observe it between steps, stop promptly, and release their isolated session.

Each stored `KnowledgeCandidate` contains:

```text
topic, concise_claim, source_urls, provider_ids, confidence,
verification_status, contradictions, created_at, expires_at
```

Candidates remain quarantined until a deterministic source check or a later
council session verifies them. They may improve future answers as cited context,
but cannot become instructions or modify the role/system prompt.

## Provider interface

```text
AdvisorProvider.ask(request) -> AdvisorOpinion
```

Provider kinds:

- `openai_compatible`: LM Studio or another configured compatible endpoint;
- `browser_site`: a dedicated persistent browser profile and provider adapter;
- `fixture`: deterministic tests only.

Provider adapters own transport details. `CouncilService` owns orchestration,
timeouts, quorum, critic, synthesis, and report validation.

## Required tests

- independent prompts contain no prior opinions;
- two successes plus one timeout still produce a report;
- quorum failure terminates without synthesis;
- duplicate claims do not inflate confidence;
- fabricated or unreachable URLs remain unverified;
- prompt injection in an adviser answer cannot create actions;
- critic and synthesizer calls are each bounded to one;
- sensitive tokens are redacted before external prompts and logs;
- all browser-provider sessions are isolated;
- confirmation-required steps never enter the autonomous queue;
- no-progress and total-budget conditions terminate experiments.
- user activity preempts idle learning within one scheduler tick;
- idle sessions never use the active browser profile or visible app;
- unverified knowledge is quarantined and expires;
- idle learning cannot edit roles skills code config or policy.
