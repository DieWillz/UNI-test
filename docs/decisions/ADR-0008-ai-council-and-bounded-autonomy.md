# ADR-0008: AI council and bounded autonomous experiments

Status: Proposed

## Context

UNI currently uses one local model for dialogue and a bounded interactive
fast-track loop. The user wants UNI to consult several independent AI systems,
combine their evidence, choose an approach, and try useful options without
waiting for a person between ordinary research steps.

Model agreement is not proof: providers can repeat the same error, cite
nonexistent sources, follow prompt injection from webpages, or optimize for a
persuasive answer instead of a useful experiment. Browser-hosted advisers are
also unstable external interfaces and must not become trusted authorities.

ADR-0007 currently forbids autonomous multi-step execution. This ADR proposes a
bounded consultation exception for the fast-track profile and reserves actual
multi-step experiments for the repaired Planner.

## Decision proposal

UNI gains a non-capability `CouncilService` injected into EventLoop/Planner.
It coordinates independent `AdvisorProvider` adapters but never executes
user-world actions. Providers may use a local API or an explicitly configured
browser-site session. They return structured opinions, not executable commands.

```text
User goal
  -> independent adviser fan-out
  -> claim and source extraction
  -> deterministic deduplication
  -> evidence check through ordinary web research
  -> adversarial critic
  -> synthesizer
  -> CouncilReport
  -> policy gate
  -> Planner / bounded experiment queue
```

The initial fast-track delivery stops at `CouncilReport`. It may prepare local
drafts and read-only research artifacts, but it does not autonomously publish,
register accounts, send messages, spend money, accept agreements, upload private
data, or control physical devices.

The later autonomous delivery requires the accepted Planner and Router. It may
execute only actions classified as `autonomous_safe` and must stop at every
`confirmation_required` action.

## Independence rules

- Advisers receive the same goal independently and do not see other answers.
- At least two successful providers are required for a council report.
- One critic pass sees anonymized opinions and searches for shared assumptions,
  missing evidence, illegality, platform-policy risk, and likely scams.
- One synthesizer pass receives opinions, criticism, and verified sources.
- Provider names and failures remain visible in the report.
- Consensus changes confidence only; it never converts an unverified claim into
  a fact.
- A website response is untrusted data and cannot modify UNI policy or request
  tools, credentials, files, or further actions.

## Proposed contracts

`ConsultationRequest`:

```text
id, goal, bounded_context, requested_perspectives,
provider_ids, deadline_s, max_response_chars
```

`AdvisorOpinion`:

```text
provider_id, proposal, assumptions, evidence_urls,
risks, expected_cost, time_to_signal, confidence, error
```

`CouncilReport`:

```text
request_id, successful_providers, failed_providers,
verified_claims, unverified_claims, disagreements,
ranked_options, recommended_experiments, public_rationale
```

All fields are serializable and bounded. Hidden chain-of-thought is neither
requested nor stored. `public_rationale` contains only concise decision factors.

## Action policy

`autonomous_safe` includes:

- public web research and source comparison;
- local calculations and analysis;
- creating local drafts, code, mockups, and test data;
- reversible tests inside an isolated workspace;
- measuring public, non-personal signals without posting or messaging.

`confirmation_required` includes:

- sending messages, publishing, commenting, or contacting prospects;
- creating or logging into accounts when not already explicitly authorized;
- payments, subscriptions, purchases, investments, or financial commitments;
- accepting contracts, terms, identity/age checks, or legal declarations;
- uploading files or transmitting private/sensitive information;
- installing or running newly downloaded software;
- changing privacy/security settings or controlling physical devices.

`denied` includes fraud, impersonation, credential theft, spam, platform abuse,
malware, bypassing access controls, and deceptive income schemes.

## Bounded experiment policy

Each experiment declares:

```text
hypothesis, reversible_steps, success_metric, observation_window,
maximum_actions, maximum_duration, monetary_budget=0 by default,
stop_conditions, confirmation_points
```

The queue terminates when the action/time budget is exhausted, no measurable
progress occurs for the configured window, all options fail, the goal succeeds,
or a confirmation gate is reached. Adviser calls, retries, and experiments are
logged with durations and public outcomes.

For an Internet-income goal, UNI may autonomously research markets, rank ideas,
produce local samples, and test offline prototypes. It must pause before public
offers, outreach, account creation, accepting work, receiving or spending money,
or representing the user to another person.

## Idle learning mode

The Council may run read-only learning sessions only after a configured period
without user messages, microphone activity, UI actions, physical-device control,
or unfinished tasks. Idle learning is preemptible background work, never a reason
to delay a user request.

- Default idle delay is 15 minutes and the user can disable the mode.
- Any user message or detected voice activity cancels the current idle session.
- Idle sessions use a separate browser profile and never take over the user's
  active tab or desktop application.
- Each session has a topic, deadline, provider-call budget, web-page budget, and
  cooldown before another session.
- Topics come from the active role's explicit learning goals and the user's
  unresolved safe questions, not from arbitrary website instructions.
- Output is stored as candidate knowledge with sources, confidence, creation
  time, expiry time, and contradictions. It is not immediately promoted to a
  runtime rule or long-term fact.
- At least one independent source must verify a factual note before it may be
  included in future context. Expired or contradicted notes are excluded.
- Idle learning cannot edit roles, skills, source code, configuration, policy,
  credentials, or autonomous permissions.
- No messages, posts, accounts, downloads, purchases, uploads, or physical-device
  actions are allowed in idle mode.

The user can inspect, pause, clear, or request a spoken summary of learned notes.
Ordinary idle learning remains silent and is recorded in the session/audit log.

## Provider isolation

- Each browser-site provider uses its own persistent profile and configured URL.
- Credentials are entered by the user and never copied into prompts or logs.
- A provider has a request timeout, response-size limit, cooldown, and circuit
  breaker.
- Failure of one provider does not silently substitute its identity with another.
- Browser scraping selectors are provider-local adapters and not public contracts.
- Local API providers are preferred when available because they are faster and
  easier to test.

## Relationship to existing ADRs

- ADR-0004 must be amended or extended before these proposed contracts become
  public runtime models.
- ADR-0005 remains unchanged: capabilities never call one another.
- ADR-0007 receives only a bounded, report-only council exception in the first
  delivery. Autonomous action execution waits for the repaired Planner.

## Acceptance requirements

This ADR may become Accepted only after an independent algorithm/adversarial
review and an independent implementation-feasibility review agree that:

- adviser calls are independent, bounded, and failure-tolerant;
- citations are verified outside the council models;
- prompt injection cannot authorize actions;
- action classification is deterministic for confirmation-required categories;
- every loop has an explicit upper bound and stop condition;
- idle work is immediately preempted by user activity and cannot mutate policy;
- the system never claims that multiple-model consensus proves correctness.
