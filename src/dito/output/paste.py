"""Text into the focused field — armadilhas 4.1: clipboard + Ctrl+V, never synthetic typing."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

# See docs/armadilhas.md 4.2 and 4.3: Enter waits for the paste, the restore waits even longer.
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
        # Almost always a missing xclip (armadilhas 4.4); raising here kills the whole job queue.
        return False


def paste(text: str, send_enter: bool = False, restore_clipboard: bool = True) -> PasteResult:
    """Returns a result, never raises (armadilhas 4.4: the text used to be lost here)."""
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
