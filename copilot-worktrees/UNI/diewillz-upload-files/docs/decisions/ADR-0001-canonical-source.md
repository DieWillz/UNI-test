# ADR-0001: Canonical source tree

Status: Accepted

## Decision

`C:\LLM\UNI\uni` is the only canonical product package.

Other model-specific and backup directories are reference-only. Code may be
ported from them only through a scoped task, review, and tests.

## Reason

Parallel copies have incompatible contracts and cannot be safely merged as
complete directories. A single source is required for reliable automation.
