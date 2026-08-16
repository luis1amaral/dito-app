"""Focus grab/restore on a private thread with its own X connection (armadilhas 2.3, 2.4)."""

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
        """Must land before the paste, or the text goes into Dito's own review card."""
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
                    # Never remember ourselves: two grabs in a row would return focus to us.
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
                # A window closed under us: losing one restore beats losing the thread forever.
                continue
