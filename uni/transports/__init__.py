"""Transport abstractions for UNI.

Transports are platform adapters that normalize inbound messages from external
channels (Telegram, Discord, WebUI, voice, etc.) into a common internal model,
and that turn normalized outbound messages back into platform-specific delivery.
"""
