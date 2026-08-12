# ADR-0009: Development Coordination Layer

Status: Accepted

Date: 2026-08-02

Task: DEV-COORD-001

## Context

UNI is developed with several AI providers. Today the human coordinator copies
prompts, files, results, and status messages between them manually. This loses
provenance, repeats work, and makes it difficult for one participant to resume
where another stopped.

The accepted UNI Manifesto v2.5 requires structured handoff, minimum necessary
context, untrusted external-model output, and explicit separation between
orchestration and product capabilities.

## Decision

Create a development-only coordination layer under `uni.devcoord`.

It owns:

- a durable task state store;
- typed handoff packages;
- explicit artifact references with hashes;
- an agent/provider registry;
- deterministic provider routing;
- bounded API and browser transports;
- an append-only public event trail.

It does not import or invoke UNI capabilities, the product ToolExecutor,
physical devices, personal WorkingMemory, or the product EventLoop.

## Provider policy

Provider transport is configured explicitly; the coordinator never guesses
whether an API is free.

- `api` is allowed when the provider is marked `api_cost: free`, or when the
  operator explicitly enables paid API use.
- `browser` may be used for providers whose API is paid, provided a dedicated
  browser profile and selectors are configured.
- Browser automation does not bypass authentication, CAPTCHA, rate limits,
  subscriptions, or provider terms.
- Browser output is untrusted data and cannot execute tools or mutate policy.
- Disabled providers are never selected.

## Context policy

Only explicitly named workspace artifacts may be attached. Each artifact is
resolved inside the workspace and recorded with path, size, and SHA-256.
Small text artifacts may be embedded in a bounded prompt; binaries and large
files are referenced by metadata only.

Provider responses are recorded as proposals. They do not change source files
or task status to complete automatically.

## Handoff contract

Every provider receives a typed handoff containing:

```text
task_id, goal, instructions, from_agent, to_agent,
context_summary, constraints, artifacts, previous_results,
expected_output
```

## Failure and termination

- Each provider call has a timeout and response-size bound.
- A task has an explicit provider sequence and maximum number of steps.
- A failure is recorded and handed to the next configured participant only
  when the task policy allows continuation.
- No retry loop is hidden inside a provider transport.

## Consequences

The first version automates development handoff and report collection. It is
not the product AI Council, does not accept its own work, and does not grant
autonomous source-code mutation. Later ADRs may add reviewed patch application,
Git branches, and independent acceptance gates.

