# Dorch / XToys Stabilization Design

## Goal
Make UNI's Dorch control a single reliable autonomous path that can operate through Intiface without per-action owner confirmations, while keeping emergency stop, hard intensity cap, disconnect-to-zero behavior, and truthful verification.

## Canonical physical path
`UNI intent -> ControlQueue -> ToyControlCoordinator -> IntifaceBridge -> device`.
Browser DOM/XToys.app is not a production control path. Legacy DOM helpers may remain only as clearly dead compatibility code until removed safely.

## Authorization model
Persistent configuration is the authorization boundary: `autonomous.enabled=true` and `capabilities.xtoys.autonomous_physical=true` permit autonomous positive power. No `verified_physical` acknowledgment is required for every session or command.

A positive command is still rejected when Dorch control is disabled, STOP is latched, Intiface is unavailable, no device is present, or the hard `max_intensity` limit would be exceeded.

## Safety invariants
Emergency STOP remains immediate and cannot be auto-reset. `max_intensity` remains a hard ceiling. Loss of Intiface/device presence forces zero or prevents positive output. UI/LLM must never call a command "physically verified" when Intiface only accepted a command without independent physical feedback.
## Speech/action synchronization
UNI produces or accepts structured scenario steps containing the spoken line plus the device action, intensity/pattern, duration, and reason. The action is accepted into the canonical queue first. Speech is emitted only when the step becomes active and a command has actually been accepted by the coordinator; if the command is rejected, UNI emits a factual failure/status line instead of claiming the action happened.

The UI reads the same queue state as the executor: current step, pending steps, commanded value, connection state, last error, and verification state. No separate UI-only timeline may invent device state.

## Stabilization scope
Fix the `event_loop.py` missing `time` import. Correct queue horizon calculations for replacement operations. Add direct ControlQueue regression tests. Replace obsolete browser-DOM XToys tests and legacy autonomous expectations with Intiface/coordinator/queue tests. Fix the hanging role-switch UI test or its transport lifecycle. Restore an effective pytest timeout plugin/configuration.

Make the launcher honor `brain.llm_provider`: LM Studio mode must not start the embedded llama server; embedded mode starts and watches it. Keep live LM Studio health/vision smoke tests as acceptance evidence.

## Acceptance
All targeted Dorch/XToys/ControlQueue/autonomous tests pass. Verification invariant and architecture audit remain green. The full suite completes instead of hanging, with legacy tests updated or deliberately skipped only when they test removed behavior. With Intiface running but no device attached, UNI reports the server connection accurately and refuses positive motion without falsely claiming success. With a device present later, no extra per-action confirmation is required beyond enabled configuration and an unlatched STOP.