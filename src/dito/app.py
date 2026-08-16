"""Composition root: the only place that knows about every part at once.

Threading is the thing to get right here. Audio arrives on PortAudio's realtime thread, hotkeys
on pynput's listener thread, transcription on a worker, and Qt owns the main thread and refuses
to be touched from any other. Every event therefore crosses one bridge — a Qt signal — and every
widget update happens on the far side of it. The previous version learned this the hard way:
touching a widget from the listener thread is what made the UI die with no traceback.

The other rule: **stopping a recording must not run on the thread that detected the key.** The
hotkey watcher polls the physical keymap; blocking it for the length of a transcription means the
next key press is missed entirely.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import config as cfgmod
from . import paths
from .audio.level import State as AudioState
from .core import events as ev
from .core import publish
from .core.session import Mode, Session
from .i18n import _
from .i18n import setup as setup_language
from .output import paste as paster
from .platform.linux_x11 import audio_system, instance, notify
from .platform.linux_x11.focus import FocusBroker
from .platform.linux_x11.hotkeys import HotkeyManager
from .platform.linux_x11.hotkeys import Mode as KeyMode
from .stt.engine import WhisperEngine
from .ui import theme
from .ui.icons import app_icon
from .ui.overlay import Overlay
from .ui.review import ReviewCard
from .ui.tray import Tray
from .ui.window import MainWindow

DICTATION = "dictation"
MEETING = "meeting"


class Bridge(QObject):
    """The single crossing point from worker threads into Qt."""

    event = Signal(object)
    log = Signal(str)
    command = Signal(str)


class DitoApp:
    def __init__(self, cfg: cfgmod.Config | None = None, show_window: bool = False) -> None:
        self.cfg = cfg or cfgmod.load()
        self._show_window = show_window
        self._lock: object | None = None
        self._window: MainWindow | None = None
        self._sessions: dict[str, Session] = {}
        self._sessions_lock = threading.Lock()
        self._last_text: str | None = None
        self._paused = False
        self._alarm_ringing = False
        self._last_alarm_sound = 0.0
        self._pending: ev.Finished | None = None

    # ---- lifecycle -------------------------------------------------------------------

    def run(self) -> int:
        # Before any widget: a string translated at construction time cannot change afterwards.
        setup_language(self.cfg.ui.language)
        try:
            self._lock = instance.claim()
        except instance.AlreadyRunning:
            # Not an error: the user launched Dito while it was already listening. Ask the running
            # one to show its window, which is what they actually wanted.
            if instance.send(instance.SHOW):
                return 0
            print(_("dictation is already running."))
            return 1

        paths.ensure_dirs()

        self.qt = QApplication.instance() or QApplication([])
        self.qt.setApplicationName("Dito")
        self.qt.setDesktopFileName("com.defalt.dito")
        self.qt.setWindowIcon(app_icon())
        # Closing the window must not end the process: the daemon keeps listening. Quitting is an
        # explicit choice in the tray menu.
        self.qt.setQuitOnLastWindowClosed(False)

        self.palette = theme.palette(theme.resolve_mode(self.cfg.ui.theme))
        self.qt.setStyleSheet(theme.stylesheet(self.palette))

        self.bridge = Bridge()
        self.bridge.event.connect(self._on_event, Qt.ConnectionType.QueuedConnection)
        self.bridge.command.connect(self._run_command, Qt.ConnectionType.QueuedConnection)

        self.overlay = Overlay(self.palette)
        self.overlay.fix_requested.connect(self._fix_audio)

        # The review card takes focus (you type in it) and must give it back before pasting.
        # The broker keeps every X round-trip off the UI thread — a round-trip there is what
        # froze the badge in the previous version.
        self.focus = FocusBroker()
        self.review = ReviewCard(self.palette, focus_broker=self.focus)
        self.review.send.connect(self._review_sent)
        self.review.discard.connect(self._review_discarded)

        self.engine = WhisperEngine(
            model=self.cfg.stt.model,
            language=self.cfg.stt.language,
            device=self.cfg.stt.device,
            idle_unload_min=self.cfg.stt.idle_unload_min,
            on_log=lambda m: print(m, flush=True),
        )

        self.hotkeys = HotkeyManager(
            on_start=self._begin,
            on_stop=self._end,
            grab=self.cfg.hotkeys.grab,
            on_log=lambda m: print(m, flush=True),
        )
        self._bind_hotkeys()

        self.tray = Tray(
            on_open=self.open_window,
            on_quit=self._quit,
            on_copy_last=self._copy_last,
            on_toggle_pause=self._set_paused,
        )
        if self.cfg.ui.tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.tray.set_ready(self.cfg.hotkeys.push_to_talk, self.cfg.hotkeys.meeting_toggle)

        self.control = instance.ControlServer(self._on_command)
        self.control.start()

        self.hotkeys.start()

        # Idle unload runs on the Qt clock rather than a thread of its own: it only ever needs to
        # ask a cheap question once a minute, and one fewer thread is one fewer thing to join.
        self._idle = QTimer()
        self._idle.setInterval(60_000)
        self._idle.timeout.connect(lambda: self.engine.unload_if_idle())
        self._idle.start()

        self._preflight_warning()

        if self._show_window:
            self.open_window()

        try:
            return self.qt.exec()
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        """Quitting must not throw away a recording in progress.

        This used to `clear()` the session dictionary without calling stop() on anything, so
        quitting from the tray during a forty-minute meeting lost the whole thing: no transcript,
        no publish, session.json frozen at "recording". Now every live session is finished
        properly first, and only then does the rest come down.
        """
        with self._sessions_lock:
            live = list(self._sessions.values())
            self._sessions.clear()

        for session in live:
            try:
                print("[exiting] finishing the recording in progress…", flush=True)
                result = session.stop()
                if isinstance(result, ev.Finished) and result.mode == MEETING and result.text:
                    started = datetime.now() - timedelta(seconds=result.seconds)
                    publish.publish_meeting(
                        Path(result.folder), result.text, result.seconds, started,
                        self.cfg, f"reuniao-{started:%H%M}",
                    )
            except Exception as exc:
                self._log_error(f"while finishing the recording: {type(exc).__name__}: {exc}")

        self.hotkeys.stop()
        self.control.stop()

    def _quit(self) -> None:
        self._shutdown()
        self.qt.quit()

    # ---- hotkeys ---------------------------------------------------------------------

    def _bind_hotkeys(self) -> None:
        self.hotkeys.bind(DICTATION, self.cfg.hotkeys.push_to_talk, KeyMode.HOLD)
        self.hotkeys.bind(MEETING, self.cfg.hotkeys.meeting_toggle, KeyMode.TOGGLE)

    def _begin(self, name: str) -> None:
        if self._paused:
            return
        mode = Mode.MEETING if name == MEETING else Mode.DICTATION
        session = Session(
            self.cfg, mode, self.engine,
            emit=self.bridge.event.emit,
            on_log=lambda m: print(m, flush=True),
        )
        with self._sessions_lock:
            if name in self._sessions:
                return
            self._sessions[name] = session

        # start() must not be able to leave a ghost behind. It was unprotected, and an OSError
        # from the WavWriter (full disk, unwritable folder) propagated into the pynput thread
        # leaving the entry in place — after which every later press hit the "already recording"
        # guard and the key never worked again, with nothing on screen to say why.
        try:
            ok = session.start().ok
        except Exception as exc:
            ok = False
            self._log_error(f"could not start recording: {type(exc).__name__}: {exc}")
            self.bridge.event.emit(
                ev.Failed(session.session_id,
                          _("could not start recording: {error}").format(error=exc),
                          str(session.folder))
            )
        if not ok:
            with self._sessions_lock:
                self._sessions.pop(name, None)

    def _log_error(self, message: str) -> None:
        print(f"[error] {message}", flush=True)

    def _end(self, name: str) -> None:
        with self._sessions_lock:
            session = self._sessions.pop(name, None)
            idle = not self._sessions
        if session is None:
            # A refused start emits the alarm and leaves nothing to stop, so releasing the key hit
            # this `return` and the red pill stayed on screen for good — armadilhas 9.5.
            if idle:
                self.overlay.dismiss_alarm_after(theme.Motion.TOAST_MS)
            return
        # Off the hotkey thread: that thread is polling the physical keymap, and blocking it for
        # the length of a transcription means the next key press is simply missed.
        threading.Thread(
            target=self._finish, args=(session,), daemon=True, name="dito-finish"
        ).start()

    def _finish(self, session: Session) -> None:
        result = session.stop()
        if not isinstance(result, ev.Finished) or result.mode == MEETING:
            # A meeting is written to a file, never pasted: dumping an hour of transcript into
            # whatever field happens to have focus would be a small catastrophe.
            return
        if not result.text:
            return
        if self.cfg.output.confirm:
            # The review card owns the paste from here: it has to hand focus back to the window
            # the user was typing in first, or the text lands in the card itself.
            self._pending = result
            return
        if self.cfg.output.paste:
            self._paste_now(result.text, result.session_id, result.folder)

    def _paste_now(self, text: str, session_id: str, folder: str) -> None:
        outcome = paster.paste(
            text,
            send_enter=self.cfg.output.enter,
            restore_clipboard=self.cfg.output.restore_clipboard,
        )
        if outcome.message:
            self.bridge.event.emit(ev.Failed(session_id, outcome.message, folder))

    # ---- events (Qt thread) ----------------------------------------------------------

    def _on_event(self, event: object) -> None:
        if isinstance(event, ev.Started):
            meeting = event.mode == MEETING
            self.overlay.show_recording(meeting=meeting)
            self.tray.set_recording(meeting=meeting)
            self._alarm_ringing = False

        elif isinstance(event, ev.Level):
            self.overlay.push_level(event.rms)

        elif isinstance(event, ev.AudioAlarm):
            self._on_alarm(event)

        elif isinstance(event, ev.PhaseChanged):
            if event.phase is ev.Phase.TRANSCRIBING:
                self.overlay.show_working(event.detail or "")
                self.tray.set_transcribing()

        elif isinstance(event, ev.Partial):
            self.overlay.show_working(
                _("{minutes} min transcribed").format(minutes=int(event.end_s // 60))
            )

        elif isinstance(event, ev.Finished):
            self._on_finished(event)

        elif isinstance(event, ev.Published):
            self._on_published(event)

        elif isinstance(event, ev.Failed):
            self.overlay.show_toast(_("Could not paste"), event.reason)
            notify.notify("Dito", event.reason, urgent=False)
            self.tray.set_ready(
                self.cfg.hotkeys.push_to_talk, self.cfg.hotkeys.meeting_toggle
            )

    def _on_alarm(self, event: ev.AudioAlarm) -> None:
        if event.state is AudioState.DEAD:
            self.overlay.show_dead(event.reason, _("Fix") if event.fix_hint else None)
            self.tray.set_alarm(event.reason or _("the microphone is not picking up"))
            self._ring(event.reason)
        elif event.state is AudioState.QUIET:
            self.overlay.show_quiet(event.reason or _("audio too low"))
        else:
            self._alarm_ringing = False
            self.overlay.show_recording(meeting=MEETING in self._sessions)

    def _ring(self, reason: str | None) -> None:
        """Sound and notification fire once per alarm, then at most every ten seconds. Repeating
        on every tick would turn the alarm into noise the user learns to ignore, which is the same
        as having no alarm."""
        now = time.monotonic()
        if self._alarm_ringing and now - self._last_alarm_sound < 10:
            return
        self._last_alarm_sound = now
        first = not self._alarm_ringing
        self._alarm_ringing = True
        if self.cfg.audio.alerts.sound:
            notify.alarm_sound()
        if self.cfg.audio.alerts.notify and first:
            notify.notify(
                _("Dito — NO AUDIO"),
                reason or _("the microphone is not picking anything up"),
                urgent=True,
            )

    def _on_finished(self, event: ev.Finished) -> None:
        self.tray.set_ready(self.cfg.hotkeys.push_to_talk, self.cfg.hotkeys.meeting_toggle)
        if event.text:
            self._last_text = event.text
            self.tray.set_last_text(event.text)
            if event.mode == MEETING:
                self._publish_meeting(event)
            elif self.cfg.output.confirm:
                self.overlay.dismiss()
                self.review.present(event.text)
            else:
                self.overlay.dismiss()
        elif not event.ever_heard_audio:
            # The exact failure this project exists for. Never a silent no-op.
            self.overlay.show_dead(
                _("nothing was picked up — the audio is saved, you can try again"), None
            )
            notify.notify(
                _("Dito — nothing was picked up"),
                _("the microphone delivered no audio. The recording is in {folder}").format(
                    folder=event.folder
                ),
                urgent=True,
            )
        else:
            self.overlay.show_toast(_("Nothing recognized"))
        if self._window is not None and self._window.isVisible():
            self._window.sessions.reload()

    def _publish_meeting(self, event: ev.Finished) -> None:
        """Ask for a subject, then write text + audio + note off the UI thread.

        The prompt lands immediately after the user deliberately pressed stop, which is the one
        moment a dialog is expected rather than an interruption — and a meeting without a name is
        a file nobody finds again. Escape keeps the timestamp.
        """
        from PySide6.QtWidgets import QInputDialog

        self.overlay.show_working(_("saving the meeting…"))
        started = datetime.now() - timedelta(seconds=event.seconds)
        default = f"reuniao-{started:%H%M}"

        subject, accepted = QInputDialog.getText(
            self._window, _("Meeting"), _("Meeting subject:"), text=default
        )
        subject = (subject or default).strip() if accepted else default

        minutes, words = int(event.seconds // 60), len(event.text.split())

        def work() -> None:
            # A thread that dies without emitting leaves the pill on "saving…" forever — the same
            # lesson session.stop() already learned. Every worker here owes an event, always.
            try:
                result = publish.publish_meeting(
                    Path(event.folder), event.text, event.seconds, started, self.cfg, subject
                )
                published = ev.Published(
                    folder=str(result.folder),
                    note=str(result.note) if result.note else None,
                    note_in_vault=result.note_in_vault,
                    minutes=minutes,
                    words=words,
                    warning=result.warnings[0] if result.warnings else None,
                )
            except Exception as exc:
                self._log_error(f"while saving the meeting: {type(exc).__name__}: {exc}")
                published = ev.Published(
                    folder=event.folder, note=None, note_in_vault=False,
                    minutes=minutes, words=words,
                    warning=_("could not save the meeting: {error}").format(error=exc),
                )
            self.bridge.event.emit(published)

        threading.Thread(target=work, daemon=True, name="dito-publish").start()

    def _on_published(self, event: ev.Published) -> None:
        detail = _("{minutes} min · {words} words").format(
            minutes=event.minutes, words=event.words
        )
        if event.warning:
            self.overlay.show_toast(_("Meeting saved, with a caveat"), event.warning, ms=6000)
            notify.notify(_("Dito — meeting saved"), event.warning)
        else:
            where = (
                _("note in the vault") if event.note_in_vault
                else _("note next to the recording")
            )
            self.overlay.show_toast(_("Meeting saved"), f"{detail} · {where}")
            notify.notify(_("Dito — meeting saved"), f"{detail}\n{event.folder}")
        if self._window is not None and self._window.isVisible():
            self._window.sessions.reload()

    # ---- review card -----------------------------------------------------------------

    def _review_sent(self, text: str) -> None:
        pending, self._pending = self._pending, None
        self._last_text = text
        self.tray.set_last_text(text)
        if not self.cfg.output.paste:
            return

        def work() -> None:
            # Focus went back a moment ago and X takes a beat to settle; pasting immediately can
            # land the Ctrl+V in the window that is on its way out.
            time.sleep(0.15)
            self._paste_now(
                text,
                pending.session_id if pending else "",
                pending.folder if pending else "",
            )

        threading.Thread(target=work, daemon=True, name="dito-paste").start()

    def _review_discarded(self) -> None:
        self._pending = None
        self.overlay.show_toast(_("Discarded"), ms=1200)

    # ---- actions ---------------------------------------------------------------------

    def _fix_audio(self) -> None:
        """The Fix button. Only ever does the thing the diagnosis named."""
        if audio_system.is_muted():
            audio_system.unmute()
        volume = audio_system.volume_pct()
        if volume is not None and volume < 5:
            audio_system.set_volume(80)
        self.overlay.show_toast(_("Tried to unmute"), _("speak again to check"))

    def _copy_last(self) -> None:
        if self._last_text:
            paster.copy(self._last_text)
            self.overlay.show_toast(_("Copied"))

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            self.hotkeys.pause()
            self.tray.set_paused()
        else:
            self.hotkeys.resume()
            self.tray.set_ready(
                self.cfg.hotkeys.push_to_talk, self.cfg.hotkeys.meeting_toggle
            )

    def open_window(self) -> None:
        if self._window is None:
            self._window = MainWindow(
                self.cfg,
                self.palette,
                icon=app_icon(),
                pause_hotkeys=self.hotkeys.pause,
                resume_hotkeys=self.hotkeys.resume,
                conflicts=self._conflicts,
                on_config_changed=self._reload_config,
            )
        self._window.present()

    def _conflicts(self, key: str, owner: str) -> str | None:
        return self.hotkeys.conflicts(key, ignoring=owner)

    def _reload_config(self) -> None:
        """Applied live. The gap between changing a hotkey and it working has to be zero, or the
        user presses a key that does nothing and concludes the app is broken."""
        self.hotkeys.pause()
        self._bind_hotkeys()
        self.hotkeys.resume()
        self.engine.idle_unload_min = self.cfg.stt.idle_unload_min
        if self.engine.model_name != self.cfg.stt.model:
            self.engine.model_name = self.cfg.stt.model
            self.engine.unload()
        self.tray.set_ready(self.cfg.hotkeys.push_to_talk, self.cfg.hotkeys.meeting_toggle)

    def _on_command(self, command: str) -> str:
        """Runs on the control socket's thread, so acting happens via the bridge.

        QTimer.singleShot from a thread with no Qt event loop silently does nothing — which is
        why `dito stop` answered "stopped." and stopped nothing, and `dito ui` never raised the
        window. See docs/armadilhas.md 5.7.
        """
        if command in (instance.SHOW, instance.QUIT):
            self.bridge.command.emit(command)
            return "ok"
        if command == instance.PING:
            return "ok"
        if command == instance.STATUS:
            state = _("paused") if self._paused else _("listening")
            return _(
                "{state} · {dictation_key} dictates, {meeting_key} meeting · "
                "model {model} ({backend})"
            ).format(
                state=state,
                dictation_key=self.cfg.hotkeys.push_to_talk.upper(),
                meeting_key=self.cfg.hotkeys.meeting_toggle.upper(),
                model=self.cfg.stt.model,
                backend=self.engine.backend,
            )
        return "?"

    def _run_command(self, command: str) -> None:
        """On the Qt thread, where touching widgets and quitting are legal."""
        if command == instance.SHOW:
            self.open_window()
        elif command == instance.QUIT:
            self._quit()

    def _preflight_warning(self) -> None:
        """Say it before the first key press, not after 99 seconds of speech."""
        health = audio_system.health()
        if health.blocks_recording:
            reason = health.reason or _("microphone unavailable")
            self.tray.set_alarm(reason)
            notify.notify("Dito", reason, urgent=True)


def run(show_window: bool = False, cfg: cfgmod.Config | None = None) -> int:
    return DitoApp(cfg=cfg, show_window=show_window).run()


def ensure_ui_or_hint() -> Callable[[], int]:
    return lambda: run(show_window=True)
