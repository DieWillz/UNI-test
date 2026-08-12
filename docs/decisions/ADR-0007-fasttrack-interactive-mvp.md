# ADR-0007: Fast-track interactive MVP profile

Status: Accepted

## Context

The user needs a usable same-day UNI build that can listen, speak, control a
browser and the XToys tab, search the web, and optionally use Vision. The full
autonomous Planner migration remains incomplete.

## Decision

The same-day profile is an interactive command loop, not the unfinished
autonomous Planner:

1. Deterministic Russian command matching handles browser navigation, search,
   XToys controls, and Vision requests.
2. An OpenAI-compatible local model handles free-form dialogue and may request
   tools through a temporary underscore-name API adapter. Internally, commands
   are normalized to canonical dotted names.
3. Browser and XToys share a non-capability `BrowserSession` backed by one
   persistent visible Chrome profile. Capabilities do not call one another.
4. XToys UI operations are reported as dispatched unless the resulting state is
   explicitly observed. The profile must not claim semantic verification it did
   not perform.
5. Vision analyzes a screenshot supplied by the browser session; it does not
   own desktop capture in this profile.
6. The profile remains bounded to one action per deterministic voice command.
   Planner, retry DAG, and autonomous multi-step execution remain blocked.

## Consequences

- The user gets a usable conversational/browser MVP without adopting the broken
  OpenCode Planner.
- A dedicated persistent browser profile preserves the XToys login between
  runs but does not attach to an arbitrary already-open personal Chrome tab.
- LM Studio is optional for deterministic commands and required for free-form
  dialogue and Vision analysis.
