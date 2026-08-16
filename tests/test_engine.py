"""The model's lifecycle, and the one rule that protects the alarm: never block the Qt thread."""

from __future__ import annotations

import threading
import time

from dito.stt.engine import WhisperEngine


class FakeModel:
    def transcribe(self, *_a, **_k):
        return iter(()), None


def loaded_engine(**kwargs) -> WhisperEngine:
    engine = WhisperEngine(**kwargs)
    engine._model = FakeModel()
    engine._backend = "fake"
    return engine


def test_unload_if_idle_does_not_wait_for_a_running_transcription():
    """The defect: it took the lock BEFORE checking anything, and `transcribe` holds that lock for
    the whole chunk — 16-20 s in a meeting at the measured RTF. It runs on the Qt thread, so the
    UI froze for that long, and the SEM ÁUDIO alarm, delivered by queued connection, froze with
    it. The alarm is the reason this product exists; it cannot queue behind a transcription."""
    engine = loaded_engine(idle_unload_min=0.0001)
    engine._last_use = time.monotonic() - 3600

    held = threading.Event()
    release = threading.Event()

    def hog() -> None:
        with engine._lock:
            held.set()
            release.wait(timeout=5)

    worker = threading.Thread(target=hog, daemon=True)
    worker.start()
    assert held.wait(timeout=2)

    started = time.monotonic()
    result = engine.unload_if_idle()
    elapsed = time.monotonic() - started

    release.set()
    worker.join(timeout=5)

    assert elapsed < 0.2, f"bloqueou por {elapsed:.2f}s na thread da interface"
    assert result is False, "ocupado é, por definição, não-ocioso"


def test_it_still_unloads_when_nothing_is_running():
    engine = loaded_engine(idle_unload_min=0.0001)
    engine._last_use = time.monotonic() - 3600
    assert engine.unload_if_idle() is True
    assert not engine.loaded


def test_a_pinned_model_is_never_unloaded():
    """A meeting pins it: a long silence must not stall the first chunk after every pause."""
    engine = loaded_engine(idle_unload_min=0.0001)
    engine._last_use = time.monotonic() - 3600
    engine.pin()
    assert engine.unload_if_idle() is False
    assert engine.loaded

    engine.unpin()
    assert engine.unload_if_idle() is True


def test_unpin_never_goes_negative():
    engine = loaded_engine()
    engine.unpin()
    engine.unpin()
    engine.pin()
    engine._last_use = time.monotonic() - 3600
    engine.idle_unload_min = 0.0001
    assert engine.unload_if_idle() is False, "o pin ainda vale depois de unpins a mais"


def test_zero_means_keep_it_loaded_forever():
    engine = loaded_engine(idle_unload_min=0)
    engine._last_use = time.monotonic() - 86400
    assert engine.unload_if_idle() is False
    assert engine.loaded


def test_a_recent_use_keeps_the_model():
    engine = loaded_engine(idle_unload_min=10)
    engine._last_use = time.monotonic()
    assert engine.unload_if_idle() is False


def test_unloading_twice_is_harmless():
    engine = loaded_engine()
    engine.unload()
    engine.unload()
    assert not engine.loaded
    assert engine.backend == "não carregado"
