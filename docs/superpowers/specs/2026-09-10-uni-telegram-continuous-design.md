# UNI Telegram Continuous Gateway Design

## Goal

Turn the existing additive Telegram transport into a production-ready external gateway for the same UNI core, without creating a second brain, agent, memory, or operator.

## Current baseline

Hermes has already created `uni/transports/`, `uni/transports/telegram/`, `uni/media/contracts.py`, and targeted tests under `tests/transports/`.

`TelegramAdapter` already normalizes Telegram-shaped input into `InboundMessage`, sends text/media, exposes STT/TTS hooks, and intentionally does not call Brain/Agent/Operator directly.

## Architecture

Keep Telegram as a transport boundary only. Add a thin gateway/runtime around the adapter for real polling, bounded concurrency, restart-safe update progress, rate limits, attachment spooling, and graceful shutdown.

The gateway emits normalized `InboundMessage` objects to an injected callback. Integration into `Agent/EventLoop` remains owned by ChatGPT and is explicitly out of scope for Hermes.

## Trust boundary

Telegram text, captions, filenames, attachments, forwarded content, and usernames are untrusted user data. Only configured numeric user IDs may establish OWNER/TRUSTED identity.

PUBLIC/GROUP traffic must never call Windows, filesystem, subprocess, browser Operator, or permission escalation directly from the transport layer.
## Runtime requirements

The Telegram runtime must support one active bot instance per token/config, long polling first, and a clean seam for adding webhook delivery later without changing the transport models.

Incoming updates are processed with a bounded global concurrency limit plus a per-conversation lock so two messages from the same session stay ordered while unrelated chats can run in parallel.

Update progress and deduplication must survive process restart using an injectable small state store. No unbounded in-memory sets or append-only growth.

Transient Telegram API failures may retry with bounded backoff. HTTP 429 must honor `retry_after`; invalid token, forbidden, malformed request, or permanent authorization failures must fail fast.

## Scaling requirements

Add per-user/per-chat rate limiting, bounded pending tasks, queue/backpressure behavior, graceful cancellation, and observable runtime counters. Never spawn unlimited asyncio tasks.

Attachment ingestion must enforce configured byte limits before full materialization when metadata permits it, use safe generated local names, store only in a configured spool/temp directory, and clean temporary files deterministically.

## Media and voice

Do not implement a concrete image/video model. Preserve `MediaGenerator` as the provider-neutral contract. Telegram may deliver generated files produced by an injected media provider later.

Voice support may use injected STT/TTS providers, but transport code must not instantiate the project's SpeechCapability itself.

## Repository safety

Hermes may modify only `uni/transports/**`, `uni/media/contracts.py` when strictly needed, `tests/transports/**`, and its single handoff file.

Hermes must not modify `uni/agent.py`, `uni/event_loop.py`, `uni/operator/**`, browser files, Dorch/XToys files, WebUI, config.py, or trajectory code.

No reset, restore, clean, stash, rebase, merge, cherry-pick, add, commit, or push. The working tree is intentionally shared and dirty.

## Completion rule

Hermes continues task-by-task until all plan tasks that are not externally blocked are implemented and targeted tests are green. A blocked task is recorded in the handoff and Hermes immediately proceeds to the next independent task rather than stopping to ask for permission.