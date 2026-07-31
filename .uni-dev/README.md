# UNI Development Orchestrator

This directory is the machine-readable coordination layer for developing UNI.
It is not part of the UNI runtime.

Workflow:

1. Coordinator selects one `approved` task whose dependencies are complete.
2. Architect confirms the task uses accepted contracts.
3. Developer changes only `allowed_paths`.
4. Tester runs the listed acceptance checks.
5. Reviewer reports blocking findings.
6. Coordinator marks the task complete or returns it with evidence.

No agent may mark its own implementation accepted.
