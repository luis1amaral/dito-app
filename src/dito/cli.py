"""Command line entry point.

The old version configured everything through argparse, which meant the only way to change a
hotkey was to remember a flag. Configuration now lives in the TOML file and in the settings
window; what stays here is diagnosis and one-shot jobs: `doctor`, `selftest`, `transcribe`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__, config, paths
from .audio import devices
from .audio.capture import BLOCKSIZE, Capture, CaptureError
from .audio.level import Reading, State, Watchdog, measure
from .audio.writer import WavWriter
from .i18n import _
from .i18n import setup as setup_language
from .platform import alsa_mixer, audio_system

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

    print("\n" + _("Dito — diagnosis") + "\n")

    print(" " + _("configuration"))
    cfg_path = paths.config_file()
    _line(_("file"),
          str(cfg_path) if cfg_path.exists()
          else _("{path} (does not exist yet)").format(path=cfg_path),
          OK if cfg_path.exists() else DIM)
    _line(_("dictation key"), cfg.hotkeys.push_to_talk.upper())
    _line(_("meeting key"), cfg.hotkeys.meeting_toggle.upper())
    _line(_("library"), str(cfg.library_dir()))

    print("\n " + _("microphone"))
    inputs = devices.list_inputs()
    if not inputs:
        _line(_("inputs"), _("none found"), BAD)
        problems += 1
    else:
        for d in inputs:
            _line(_("input") if d.default else "", str(d), OK if d.default else DIM)

    if devices.missing(cfg.audio.device):
        _line(_("configured"), devices.describe(cfg.audio.device), BAD)
        problems += 1
    else:
        _line(_("in use"), devices.describe(cfg.audio.device))

    print("\n " + _("audio server"))
    if not audio_system.available():
        _line(_("mixer"), _("unavailable — no mute detection"), WARN)
    else:
        health = audio_system.health()
        _line(_("default source"), health.name or _("unknown"), DIM)
        muted = health.muted
        _line(_("muted"), {True: _("YES"), False: _("no"), None: _("can't tell")}[muted],
              BAD if muted else (OK if muted is False else WARN))
        vol = health.volume
        _line(_("volume"), f"{vol}%" if vol is not None else _("can't tell"),
              BAD if (vol is not None and vol < 5) else OK)
        if health.blocks_recording:
            problems += 1

        # The blind spot: PipeWire can report 94% while the ALSA control underneath reads
        # `Capture 0 [0%]`, and the mic delivers silence with every pactl reading looking fine.
        gain = alsa_mixer.capture_gain(alsa_mixer.card_of_source(health.name))
        if not gain.checked:
            _line(_("hardware gain"), _("could not be checked"), DIM)
        elif gain.silent:
            _line(_("hardware gain"), gain.reason or _("silent"), BAD)
            _line("", _("fix: {command}").format(command=gain.fix_command), DIM)
            problems += 1
        else:
            atuais = ", ".join(f"{c.name} {c.pct}%" for c in gain.controls)
            _line(_("hardware gain"),
                  _("card {card} — {controls}").format(card=gain.card, controls=atuais))

    print("\n " + _("model"))
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
        _line(cfg.stt.model, _("cached ({size} MB)").format(size=f"{size / 1e6:.0f}"))
    else:
        _line(cfg.stt.model, _("not downloaded — downloads on first use"), WARN)

    print()
    if problems:
        message = _("{count} problem(s) preventing or hurting dictation.").format(count=problems)
        print(_paint(f" {message}\n", BAD))
    else:
        print(_paint(" " + _("all set.") + "\n", OK))
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
    wav_path = paths.selftest_audio()

    alerts = cfg.audio.alerts
    watchdog = Watchdog(dead_ms=alerts.dead_ms, quiet_ms=alerts.quiet_ms)

    source = args.source
    print("\n " + _("selftest — source «{source}», {seconds}s").format(
        source=source, seconds=f"{args.seconds:g}"))
    print(" " + _("recording to {path}").format(path=wav_path) + "\n")

    capture: Capture | None = None
    if source == "mic":
        device = devices.resolve(args.device if args.device is not None else cfg.audio.device)
        capture = Capture(device=device, sample_rate=sample_rate)
        try:
            capture.start()
        except CaptureError as exc:
            print(_paint(" " + _("microphone unavailable: {error}").format(error=exc), BAD))
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
            print("\n " + _("interrupted"))
        finally:
            if capture is not None:
                capture.stop()

    size = wav_path.stat().st_size if wav_path.exists() else 0
    print("\n " + _("result"))
    _line(_("blocks"), str(blocks), DIM)
    _line(_("highest peak"), f"{peak_max:.4f}", OK if peak_max >= 0.004 else BAD)
    _line(_("final state"), state.value, OK if state is State.OK else BAD)
    _line(_("alarm at"), f"{first_alarm:.2f}s" if first_alarm else _("did not fire"),
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
            State.OK: _("audio is back"),
            State.QUIET: _("AUDIO TOO LOW"),
            State.DEAD: _("NO AUDIO — the microphone is not picking up"),
        }[state]
        print(f"  {elapsed:6.2f}s  {_paint(label, color)}")
        if state is not State.OK and first_alarm is None:
            first_alarm = elapsed
    return state, first_alarm


def cmd_ui(args: argparse.Namespace) -> int:
    """Open the Dito window. Called by the application menu entry.

    If a daemon is already listening, this does not start a second process — it asks the running
    one to show its window, which is what the user meant by launching the app again.
    """
    from .app import run

    return run(show_window=True)


def cmd_listen(args: argparse.Namespace) -> int:
    """The daemon: tray, hotkeys, overlay — and no window.

    This is what the autostart entry runs. Nothing appears at login except the tray icon; the
    window exists only when asked for. `--headless` drops Qt entirely and prints to the terminal,
    which is how the chain gets debugged without the UI in the picture.
    """
    if not args.headless:
        from .app import run

        return run(show_window=False)
    return _listen_headless(args)


def _listen_headless(args: argparse.Namespace) -> int:
    from .core import events as ev
    from .core.session import Mode, Session
    from .output import paste as paster
    from .platform import HotkeyManager, KeyMode
    from .stt.engine import WhisperEngine

    cfg = config.load()
    paths.ensure_dirs()

    ptt = (args.key or cfg.hotkeys.push_to_talk).lower()
    meeting_key = (args.meeting_key or cfg.hotkeys.meeting_toggle).lower()

    engine = WhisperEngine(
        model=cfg.stt.model,
        language=cfg.stt.language,
        device=cfg.stt.device,
        idle_unload_min=cfg.stt.idle_unload_min,
        on_log=lambda m: print(f"  {_paint(m, DIM)}"),
    )

    current: dict[str, Session] = {}
    lock = __import__("threading").Lock()

    def show(event) -> None:
        if isinstance(event, ev.Level):
            return
        if isinstance(event, ev.AudioAlarm):
            if event.state.value == "dead":
                dead = _("NO AUDIO — {reason}").format(reason=event.reason or "")
                print(f"  {_paint(dead, BAD)}")
                if event.fix_hint:
                    fix = _("fix: {command}").format(command=event.fix_hint)
                    print(f"  {_paint(fix, DIM)}")
            elif event.state.value == "quiet":
                print(f"  {_paint(_('audio too low'), WARN)}")
            else:
                print(f"  {_paint(_('audio is back'), OK)}")
        elif isinstance(event, ev.Partial):
            print(f"  {_paint(f'[{event.end_s:.0f}s]', DIM)} {event.text}")
        elif isinstance(event, ev.Failed):
            print(f"  {_paint(event.reason, BAD)}")
            where = _("the audio is in {folder}").format(folder=event.folder or "?")
            print(f"  {_paint(where, DIM)}")

    def begin(name: str) -> None:
        mode = Mode.MEETING if name == "meeting" else Mode.DICTATION
        with lock:
            if name in current:
                return
            session = Session(cfg, mode, engine, emit=show, on_log=lambda m: print(f"  {m}"))
            current[name] = session
        print(f"\n● {_('meeting') if mode is Mode.MEETING else _('recording')}…")
        if not session.start().ok:
            with lock:
                current.pop(name, None)

    def end(name: str) -> None:
        with lock:
            session = current.pop(name, None)
        if session is None:
            return
        print("  " + _("transcribing…"))
        result = session.stop()
        if not isinstance(result, ev.Finished):
            return
        if not result.text:
            aviso = (_("nothing recognized — and the microphone picked nothing up")
                     if not result.ever_heard_audio else _("nothing recognized"))
            print(f"  {_paint(aviso, BAD if not result.ever_heard_audio else WARN)}")
            kept = _("the audio was kept in {folder}").format(folder=result.folder)
            print(f"  {_paint(kept, DIM)}")
            return
        print(f"  → {result.text}")
        if cfg.output.paste and not args.no_paste:
            outcome = paster.paste(
                result.text,
                send_enter=cfg.output.enter and not args.no_enter,
                restore_clipboard=cfg.output.restore_clipboard,
            )
            if outcome.message:
                print(f"  {_paint(outcome.message, WARN)}")
                # The audio is gone by now; what recovers the text is the session file.
                print(f"  {_paint(str(session.meta_path), DIM)}")

    manager = HotkeyManager(
        on_start=begin, on_stop=end, grab=cfg.hotkeys.grab,
        on_log=lambda m: print(f"  {_paint(m, DIM)}"),
    )
    manager.bind("dictation", ptt, KeyMode.HOLD)
    manager.bind("meeting", meeting_key, KeyMode.TOGGLE)

    print(f"\n Dito {__version__} — " + _("ready."))
    print("   " + _("hold {key} and speak; release to transcribe").format(
        key=_paint(ptt.upper(), OK)))
    print("   " + _("{key} starts and stops the meeting (no time limit)").format(
        key=_paint(meeting_key.upper(), OK)))
    print("   " + _("Ctrl+C exits.") + "\n")

    manager.start()
    try:
        while True:
            time.sleep(1.0)
            engine.unload_if_idle()
    except KeyboardInterrupt:
        print("\n " + _("finished."))
    finally:
        manager.stop()
        with lock:
            for name in list(current):
                current.pop(name)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Answers instantly, because it asks the running process rather than guessing from a PID
    file. The previous version slept 14 seconds and then read a PID that had been stale for
    hours — it once claimed 117814 while the live process was 1812."""
    from .platform import instance

    reply = instance.send(instance.STATUS)
    if reply is None:
        print(_paint(" " + _("stopped"), DIM))
        return 1
    print(f" {_paint(_('listening'), OK)} — {reply}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    from .platform import instance

    if instance.send(instance.QUIT) is None:
        print(_paint(" " + _("it was already stopped"), DIM))
        return 0
    print(" " + _("stopped."))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Asks GitHub what the newest release is and, unless `--check`, installs it."""
    from . import update as updater

    try:
        release = updater.check()
    except updater.UpdateError as exc:
        print(_paint(" " + str(exc), BAD))
        return 2

    if release is None:
        print(" " + _("Dito {version} is the newest there is.").format(version=__version__))
        return 0

    print("\n " + _paint(_("new version: {version}").format(version=release.version), OK))
    for line in release.notes.strip().splitlines()[:8]:
        print(f"   {_paint(line, DIM)}")

    if args.check:
        print("\n " + _("run «dito update» to install it") + "\n")
        return 0

    if not updater.can_apply():
        print(_paint(" " + _("this Dito did not come from the installer — update it the same "
                             "way you installed it"), WARN))
        return 3

    print(" " + _("downloading {name}…").format(name=release.asset))
    try:
        installer = updater.download(release)
        updater.install(installer, silent=args.silent)
    except updater.UpdateError as exc:
        print(_paint(" " + str(exc), BAD))
        return 2

    print(" " + _("checksum matches. The installer is taking over; Dito will close.") + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dito", description=_("Offline voice dictation."))
    p.add_argument("--version", action="version", version=f"dito {__version__}")
    subs = p.add_subparsers(dest="comando")

    d = subs.add_parser(
        "doctor", help=_("checks microphone, mute, volume, model and configuration")
    )
    d.set_defaults(func=cmd_doctor)

    s = subs.add_parser("selftest", help=_("records a few seconds and proves the audio alarm"))
    s.add_argument("--seconds", type=float, default=5.0)
    s.add_argument("--source", choices=("mic", "zeros"), default="mic",
                   help=_("«zeros» simulates a muted microphone with no microphone needed"))
    s.add_argument("--device", default=None)
    s.set_defaults(func=cmd_selftest)

    ui = subs.add_parser("ui", help=_("opens the Dito window"))
    ui.set_defaults(func=cmd_ui)

    listen = subs.add_parser("listen", help=_("starts dictation in the tray, with no window"))
    listen.add_argument("--headless", action="store_true",
                        help=_("no Qt: terminal only, to debug the chain without the interface"))
    listen.add_argument("--key", default=None, help=_("overrides the dictation key (e.g. f7)"))
    listen.add_argument("--meeting-key", default=None, help=_("overrides the meeting key"))
    listen.add_argument("--no-paste", action="store_true", help=_("only prints, does not paste"))
    listen.add_argument("--no-enter", action="store_true", help=_("pastes without pressing Enter"))
    listen.set_defaults(func=cmd_listen)

    st = subs.add_parser("status", help=_("says whether dictation is listening, right now"))
    st.set_defaults(func=cmd_status)

    stop = subs.add_parser("stop", help=_("shuts down the dictation that is running"))
    stop.set_defaults(func=cmd_stop)

    up = subs.add_parser("update", help=_("looks for a new version and installs it"))
    up.add_argument("--check", action="store_true", help=_("only says what exists, downloads "
                                                           "nothing"))
    up.add_argument("--silent", action="store_true", help=_("installs without a single window"))
    up.set_defaults(func=cmd_update)

    return p


def _readable_output() -> None:
    """See docs/armadilhas.md 5.9: redirected stdout is cp1252, and one `●` kills the thread."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _readable_output()
    # Before the parser is built: argparse keeps the help strings it was given.
    setup_language(os.environ.get("DITO_LANG") or config.load().ui.language)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Bare `dito` opens the window. Someone who typed the app's name wants the app, not help.
        return cmd_ui(args)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
