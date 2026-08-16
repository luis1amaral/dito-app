"""The control protocol, identical on every backend; only the transport below it changes."""

from __future__ import annotations

# Do NOT rename: contract with the sibling `defalt` project (docs/armadilhas.md 5.1).
LEGACY_LOCK_NAME = "defalt-voice-input"

SHOW = "show"
PING = "ping"
QUIT = "quit"
STATUS = "status"
ENCODING = "utf-8"


class AlreadyRunning(RuntimeError):
    pass
