"""Borrowing keyboard focus and giving it back.

The review card needs the keyboard, so it has to take focus. But the text it holds is going to be
pasted into whatever the user was typing in — so focus must go back to that window *before* the
paste, or the text lands in Dito's own card.

This runs on a dedicated thread with its own X connection, and that is not tidiness. Reading who
currently owns focus is a round-trip, and a round-trip on the UI thread is what froze the badge
in the previous version — bisected at the time: 120 state cycles pass without the focus grab and
hang with it. If X ever wedges this connection, this thread strands; the interface and the
recording do not.

Xlib is also not thread-safe, so this connection is used by this thread and nothing else.
"""

from __future__ import annotations

import queue
import threading

_GRAB = "grab"
_RESTORE = "restore"


class FocusBroker:
    """Serialises focus changes onto one thread. Fire-and-forget: callers never block."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, int]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._previous = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._serve, daemon=True, name="dito-focus")
        self._thread.start()

    def take(self, window_id: int) -> None:
        self.start()
        self._queue.put((_GRAB, window_id))

    def give_back(self) -> None:
        if self._thread is not None:
            self._queue.put((_RESTORE, 0))

    def _serve(self) -> None:
        try:
            from Xlib import X, display
        except Exception:
            return

        try:
            dsp = display.Display()
        except Exception:
            return

        while True:
            op, window_id = self._queue.get()
            try:
                if op == _GRAB:
                    owner = dsp.get_input_focus().focus
                    # Only remember the previous owner if it is not us: taking focus twice in a
                    # row would otherwise record Dito's own card as the place to return to.
                    if getattr(owner, "id", None) != window_id:
                        self._previous = owner
                    dsp.create_resource_object("window", window_id).set_input_focus(
                        X.RevertToParent, X.CurrentTime
                    )
                    dsp.flush()
                elif op == _RESTORE:
                    previous, self._previous = self._previous, None
                    if previous is not None and not isinstance(previous, int):
                        previous.set_input_focus(X.RevertToParent, X.CurrentTime)
                        dsp.flush()
            except Exception:
                # A window that closed while we held its handle raises here. Losing focus
                # restoration is a small annoyance; taking the thread down would mean every later
                # dictation pastes into the wrong place.
                continue
