"""Delivering the transcribed text into whatever field has focus.

Clipboard + Ctrl+V, never synthetic per-character typing: accented pt-BR text comes out wrong
when typed key by key, and it is slow enough to be visible.

Three timings here are not arbitrary:
  * a short settle before Ctrl+V, so the clipboard write has landed before the paste reads it;
  * 250 ms before Enter, because Enter arriving first submits an empty field;
  * ~1 s before restoring the previous clipboard, because restoring immediately races the
    application that is still reading the clipboard during the paste.

Failure here used to lose the text entirely — the exception went to a log file nobody reads.
`paste()` returns a result instead of raising, so the caller can keep the text somewhere the user
can reach it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

SETTLE_S = 0.05
BEFORE_ENTER_S = 0.25
RESTORE_AFTER_S = 1.0


@dataclass(frozen=True)
class PasteResult:
    pasted: bool
    copied: bool
    error: str | None = None

    @property
    def message(self) -> str | None:
        """What to show the user. Silence on success; on failure, where the text still is."""
        if self.pasted:
            return None
        if self.copied:
            return "não consegui colar — o texto está na área de transferência"
        return "não consegui colar nem copiar — o texto está salvo na pasta da sessão"


def copy(text: str) -> bool:
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        # On Linux this is almost always a missing xclip. The caller reports it; raising here
        # would take the whole job queue down, which is how a dictation silently "stops working".
        return False


def paste(text: str, send_enter: bool = False, restore_clipboard: bool = True) -> PasteResult:
    if not text:
        return PasteResult(pasted=False, copied=False, error="texto vazio")

    previous: str | None = None
    if restore_clipboard:
        try:
            import pyperclip

            previous = pyperclip.paste()
        except Exception:
            previous = None

    if not copy(text):
        return PasteResult(
            pasted=False, copied=False, error="clipboard indisponível (falta xclip?)"
        )

    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        time.sleep(SETTLE_S)
        with kb.pressed(Key.ctrl):
            kb.press("v")
            kb.release("v")

        if send_enter:
            time.sleep(BEFORE_ENTER_S)
            kb.press(Key.enter)
            kb.release(Key.enter)
    except Exception as exc:
        return PasteResult(pasted=False, copied=True, error=f"{type(exc).__name__}: {exc}")

    if previous is not None:
        threading.Timer(RESTORE_AFTER_S, lambda: copy(previous)).start()

    return PasteResult(pasted=True, copied=True)
