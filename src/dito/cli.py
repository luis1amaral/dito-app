"""Command line entry point.

The old version configured everything through argparse, which meant the only way to change a
hotkey was to remember a flag. Configuration now lives in the TOML file and in the settings
window; what stays here is diagnosis and one-shot jobs: `doctor`, `selftest`, `transcribe`.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__, config, paths
from .audio import devices
from .audio.capture import BLOCKSIZE, Capture, CaptureError
from .audio.level import Reading, State, Watchdog, measure
from .audio.writer import WavWriter
from .platform.linux_x11 import audio_system

OK = "\033[32m"
WARN = "\033[33m"
BAD = "\033[31m"
DIM = "\033[2m"
OFF = "\033[0m"


def _paint(text: str, color: str) -> str:
    return f"{color}{text}{OFF}" if sys.stdout.isatty() else text


def _line(label: str, value: str, color: str = OK) -> None:
    print(f"  {label:<22} {_paint(value, color)}")


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = config.load()
    problems = 0

    print("\nDito — diagnóstico\n")

    print(" configuração")
    cfg_path = paths.config_file()
    _line("arquivo", str(cfg_path) if cfg_path.exists() else f"{cfg_path} (ainda não existe)",
          OK if cfg_path.exists() else DIM)
    _line("tecla de ditado", cfg.hotkeys.push_to_talk.upper())
    _line("tecla de reunião", cfg.hotkeys.meeting_toggle.upper())
    _line("biblioteca", str(cfg.library_dir()))

    print("\n microfone")
    inputs = devices.list_inputs()
    if not inputs:
        _line("entradas", "nenhuma encontrada", BAD)
        problems += 1
    else:
        for d in inputs:
            _line("entrada" if d.default else "", str(d), OK if d.default else DIM)

    if devices.missing(cfg.audio.device):
        _line("configurado", devices.describe(cfg.audio.device), BAD)
        problems += 1
    else:
        _line("em uso", devices.describe(cfg.audio.device))

    print("\n servidor de áudio")
    if not audio_system.available():
        _line("pactl", "não instalado — sem detecção de mute", WARN)
    else:
        health = audio_system.health()
        _line("fonte padrão", health.name or "desconhecida", DIM)
        muted = health.muted
        _line("mudo", {True: "SIM", False: "não", None: "não sei"}[muted],
              BAD if muted else (OK if muted is False else WARN))
        vol = health.volume
        _line("volume", f"{vol}%" if vol is not None else "não sei",
              BAD if (vol is not None and vol < 5) else OK)
        if health.blocks_recording:
            problems += 1

    print("\n modelo")
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    hits = list(cache.glob(f"models--*faster-whisper-{cfg.stt.model}")) if cache.exists() else []
    if hits:
        # Skip symlinks: the HF cache stores each file once under blobs/ and links to it from
        # snapshots/, so following links counts every byte twice.
        size = sum(
            f.stat().st_size
            for f in hits[0].rglob("*")
            if f.is_file() and not f.is_symlink()
        )
        _line(cfg.stt.model, f"em cache ({size / 1e6:.0f} MB)")
    else:
        _line(cfg.stt.model, "não baixado — baixa no primeiro uso", WARN)

    print()
    if problems:
        print(_paint(f" {problems} problema(s) que impedem ou prejudicam o ditado.\n", BAD))
    else:
        print(_paint(" tudo pronto.\n", OK))
    return 1 if problems else 0


def _zero_blocks(seconds: float, sample_rate: int, blocksize: int):
    """A source that behaves exactly like the failure being defended against: a stream that keeps
    delivering, on time, with every sample at zero. No microphone needed to prove the alarm."""
    import numpy as np

    silence = np.zeros(blocksize, dtype="float32")
    period = blocksize / sample_rate
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(period)
        yield silence, measure(silence), time.monotonic()


def cmd_selftest(args: argparse.Namespace) -> int:
    cfg = config.load()
    paths.ensure_dirs()

    sample_rate = devices.SAMPLE_RATE
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = paths.sessions_dir() / f"{stamp}_selftest"
    wav_path = folder / "audio.wav"

    alerts = cfg.audio.alerts
    watchdog = Watchdog(dead_ms=alerts.dead_ms, quiet_ms=alerts.quiet_ms)

    source = args.source
    print(f"\n selftest — fonte «{source}», {args.seconds:g}s")
    print(f" gravando em {wav_path}\n")

    capture: Capture | None = None
    if source == "mic":
        device = devices.resolve(args.device if args.device is not None else cfg.audio.device)
        capture = Capture(device=device, sample_rate=sample_rate)
        try:
            capture.start()
        except CaptureError as exc:
            print(_paint(f" microfone indisponível: {exc}", BAD))
            return 2

    t0 = time.monotonic()
    watchdog.restart(t0)
    state = State.OK
    peak_max = 0.0
    first_alarm: float | None = None
    blocks = 0

    with WavWriter(wav_path, sample_rate) as writer:
        try:
            if capture is not None:
                deadline = t0 + args.seconds
                while time.monotonic() < deadline:
                    item = capture.blocks.get(timeout=2.0)
                    if item is None:
                        break
                    blocks += 1
                    peak_max = max(peak_max, item.reading.peak)
                    writer.write(item.audio)
                    state, first_alarm = _tick(
                        watchdog, item.reading, item.monotonic, t0, state, first_alarm
                    )
            else:
                for audio, reading, now in _zero_blocks(args.seconds, sample_rate, BLOCKSIZE):
                    blocks += 1
                    peak_max = max(peak_max, reading.peak)
                    writer.write(audio)
                    state, first_alarm = _tick(watchdog, reading, now, t0, state, first_alarm)
        except KeyboardInterrupt:
            print("\n interrompido")
        finally:
            if capture is not None:
                capture.stop()

    size = wav_path.stat().st_size if wav_path.exists() else 0
    print("\n resultado")
    _line("blocos", str(blocks), DIM)
    _line("pico máximo", f"{peak_max:.4f}", OK if peak_max >= 0.004 else BAD)
    _line("estado final", state.value, OK if state is State.OK else BAD)
    _line("alarme em", f"{first_alarm:.2f}s" if first_alarm else "não disparou",
          OK if first_alarm else DIM)
    _line("wav", f"{size / 1024:.0f} kB  ({size and (size - 44) / 2 / sample_rate:.1f}s)",
          OK if size > 44 else BAD)
    if capture is not None and capture.overflows:
        _line("overflows", str(capture.overflows), WARN)
    print()

    # The WAV must always exist with real content, alarm or not — that is the safety net working.
    return 0 if size > 44 else 3


def _tick(
    watchdog: Watchdog,
    reading: Reading,
    now: float,
    t0: float,
    previous: State,
    first_alarm: float | None,
) -> tuple[State, float | None]:
    state = watchdog.feed(reading.peak, now)
    if state is not previous:
        elapsed = now - t0
        color = {State.OK: OK, State.QUIET: WARN, State.DEAD: BAD}[state]
        label = {
            State.OK: "áudio voltou",
            State.QUIET: "AUDIO MUITO BAIXO",
            State.DEAD: "SEM ÁUDIO — o microfone não está captando",
        }[state]
        print(f"  {elapsed:6.2f}s  {_paint(label, color)}")
        if state is not State.OK and first_alarm is None:
            first_alarm = elapsed
    return state, first_alarm


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dito", description="Ditado por voz offline.")
    p.add_argument("--version", action="version", version=f"dito {__version__}")
    subs = p.add_subparsers(dest="comando")

    d = subs.add_parser("doctor", help="checa microfone, mute, volume, modelo e configuração")
    d.set_defaults(func=cmd_doctor)

    s = subs.add_parser("selftest", help="grava alguns segundos e prova o alarme de áudio")
    s.add_argument("--seconds", type=float, default=5.0)
    s.add_argument("--source", choices=("mic", "zeros"), default="mic",
                   help="«zeros» simula o microfone mudo sem precisar de microfone")
    s.add_argument("--device", default=None)
    s.set_defaults(func=cmd_selftest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
