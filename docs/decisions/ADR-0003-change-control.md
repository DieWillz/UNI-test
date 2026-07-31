# ADR-0003: Architectural change control

Status: Accepted

## Decision

Public contracts and dependency direction change only through an accepted ADR.
An implementer that discovers a contract problem submits a change request and
stops the affected work.

The coordinator accepts an implementation only when architecture review, code
review, and automated checks agree.

## Reason

Silent local variations created the current incompatible implementations.
