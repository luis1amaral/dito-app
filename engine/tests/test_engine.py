"""The model's lifecycle, and the one rule that protects the alarm: never block the Qt thread."""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest

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
    # Source strings are English and the catalogue translates on read — see engine.backend.
    assert engine.backend == "not loaded"


# ---- o modelo que ainda nao esta no disco --------------------------------------------


def test_a_half_downloaded_model_is_not_cached(tmp_path, monkeypatch):
    """O snapshot existe desde o primeiro byte; quem prova que o modelo veio inteiro e o blob.
    Sem esta checagem o app declarava «em cache» e o ctranslate2 falhava logo depois."""
    from dito.stt import engine as eng

    monkeypatch.setattr(eng, "MODEL_CACHE", tmp_path)
    folder = tmp_path / "models--Systran--faster-whisper-small"
    (folder / "blobs").mkdir(parents=True)
    (folder / "snapshots" / "abc").mkdir(parents=True)

    assert eng.model_cached("small") is False

    (folder / "blobs" / "deadbeef").write_bytes(b"x" * 11_000_000)
    assert eng.model_cached("small") is True


def test_a_model_still_downloading_says_so_instead_of_naming_a_file(monkeypatch):
    """O defeito de 16/08/2026: trocar de modelo nas configuracoes disparava o download, e uma
    transcricao nessa janela devolvia «Unable to open file model.bin» — uma mensagem do ctranslate2
    que cita um arquivo que o usuario nunca escolheu. Ver docs/armadilhas.md 3.12."""
    from dito.stt import engine as eng

    monkeypatch.setattr(eng, "model_cached", lambda _n: False)

    def boom(*_a, **_k):
        raise RuntimeError("Unable to open file model.bin in model '/x/y'")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=boom))

    engine = eng.WhisperEngine(model="small", device="cpu")
    with pytest.raises(eng.ModelNotReady) as erro:
        engine.load()

    assert "model.bin" not in str(erro.value), "o erro do ctranslate2 vazou para o usuario"
    assert "small" in str(erro.value)
