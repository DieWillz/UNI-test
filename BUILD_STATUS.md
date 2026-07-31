# UNI Build Status

Updated: 2026-07-31

## Canonical source

`C:\LLM\UNI\uni`

The following directories are read-only reference variants:

- `Uni-Claude`
- `Uni-DeepSeek`
- `Uni-OpenCode`
- `Claude`
- `backup`
- `1`
- nested `uni\uni`

## Evidence-based status

| Area | Status | Notes |
|---|---|---|
| Configuration | partial | Pydantic configuration exists; environment is not installed |
| LLM client (`Brain`) | partial | Implementations differ across variants |
| Working memory | divergent | Root, Claude, DeepSeek, and OpenCode implementations differ |
| Capabilities | partial | Implementations exist, but contracts are not uniform |
| Registry / executor | divergent | Static underscore routing conflicts with dotted planner actions |
| Planner | experimental | Present in root/DeepSeek/OpenCode; action and dependency validation is incomplete |
| Task queue | experimental | Dependency references cannot reliably map to generated task IDs |
| Event loop | divergent | Root reactive loop and OpenCode planner loop are separate designs |
| Agent context | missing | No accepted central runtime context |
| Retry / recovery | incomplete | Algorithms exist, but are not integrated end-to-end |
| Human-in-the-loop | missing | Required after exhausted replans |
| Tests | blocked | Active Python lacks project dependencies and pytest |
| MVP scenario | not passing | No verified end-to-end run |

## Variant inventory

Hashes below are abbreviated SHA-256 values observed on 2026-07-31.

| Module | Root | Claude | DeepSeek | OpenCode | Initial disposition |
|---|---|---|---|---|---|
| `contracts.py` | `74C85D971803` | `A15AD04884D8` | same as root | same as Claude | Architecture review required |
| `planner.py` | `3C828B24DEEA` | missing | same as root | same as root | Keep as algorithm source, do not accept unchanged |
| `event_loop.py` | `301F7D95FC40` | missing | `967CB3E79DD3` | `9AB1246C46AE` | Rebuild after contracts; do not merge wholesale |
| `working_memory.py` | `0E856DD3A0BF` | `2D3519BF01EF` | `EE5606B73D8E` | `75EDE53FF07C` | Compare behavior and select by tests |
| `capabilities/registry.py` | `B312505584F4` | missing | `7D49FA61AD55` | `65E37AAC2085` | Define manifest contract first |
| `tools/executors.py` | `81B7A433741F` | missing | `B0582B84D77D` | `31CEF760E183` | Replace static duplication with router |

## Immediate blockers

1. No single accepted `Action`, `ActionResult`, `Observation`, or `AgentContext`.
2. Planner emits dotted names while current executor routes underscore names.
3. Planner dependency IDs are not translated into generated task IDs.
4. Tests and runtime code disagree about imports and result types.
5. Duplicate package trees make accidental edits and imports likely.

## Definition of MVP complete

The MVP is complete only when one canonical process performs the YouTube scenario,
records every `ActionResult`, verifies playback, retries a transient failure, and
requests user help after bounded recovery failure.
