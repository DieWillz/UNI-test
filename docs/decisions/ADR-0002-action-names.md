# ADR-0002: Canonical action names

Status: Accepted

## Decision

Actions use `capability.action`, for example:

- `browser.navigate`
- `computer.click`
- `speech.speak`
- `vision.analyze_screen`

Legacy underscore names may exist only inside a temporary compatibility adapter.

## Reason

The planner, manifests, router, logs, and tests need one stable identifier.
