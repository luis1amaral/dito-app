"""JSON-lines engine server for driving Dito from the Flutter frontend.

Reads JSON commands from stdin and outputs JSON events to stdout.
"""

from __future__ import annotations

import json
import sys
import threading
import time

from . import config, paths
from .audio import devices
from .core import events as ev
from .core.session import Mode, Session
from .stt.engine import WhisperEngine


def _serialize_event(event: object) -> dict:
    if isinstance(event, ev.Started):
        return {
            "event": "started",
            "session_id": event.session_id,
            "mode": event.mode,
            "device_name": event.device,
        }
    if isinstance(event, ev.Level):
        return {
            "event": "level",
            "peak": round(event.peak, 4),
            "rms": round(event.rms, 4),
            "seconds": round(event.seconds, 2),
        }
    if isinstance(event, ev.AudioAlarm):
        state_str = event.state.value if hasattr(event.state, "value") else str(event.state)
        return {
            "event": "alarm",
            "state": state_str,
            "reason": event.reason,
            "fix_hint": event.fix_hint,
        }
    if isinstance(event, ev.PhaseChanged):
        phase_str = event.phase.value if hasattr(event.phase, "value") else str(event.phase)
        return {
            "event": "phase",
            "phase": phase_str,
            "detail": event.detail,
        }
    if isinstance(event, ev.Partial):
        return {
            "event": "partial",
            "index": event.index,
            "start_s": round(event.start_s, 2),
            "end_s": round(event.end_s, 2),
            "text": event.text,
        }
    if isinstance(event, ev.Finished):
        return {
            "event": "finished",
            "session_id": event.session_id,
            "mode": event.mode,
            "text": event.text,
            "seconds": round(event.seconds, 2),
            "folder": event.folder,
            "ever_heard_audio": event.ever_heard_audio,
        }
    if isinstance(event, ev.Published):
        return {
            "event": "published",
            "folder": event.folder,
            "note": event.note,
            "note_in_vault": event.note_in_vault,
            "minutes": event.minutes,
            "words": event.words,
            "warning": event.warning,
        }
    if isinstance(event, ev.Failed):
        return {
            "event": "failed",
            "session_id": event.session_id,
            "reason": event.reason,
            "folder": event.folder,
        }
    return {"event": "unknown", "raw": str(event)}


class EngineServer:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.engine = WhisperEngine(
            model=self.cfg.stt.model,
            language=self.cfg.stt.language,
            device=self.cfg.stt.device,
            idle_unload_min=self.cfg.stt.idle_unload_min,
            on_log=self._log,
        )
        self._session: Session | None = None
        self._lock = threading.Lock()

    def _emit(self, event: object) -> None:
        data = _serialize_event(event)
        line = json.dumps(data, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def _log(self, msg: str) -> None:
        sys.stderr.write(f"[engine] {msg}\n")
        sys.stderr.flush()

    def start_session(
        self,
        mode_str: str = "dictation",
        model: str | None = None,
        language: str | None = None,
        device: str | None = None,
        device_pref: str | None = None,
    ) -> None:
        with self._lock:
            if self._session is not None:
                self._log("session already in progress")
                return

            if model and model != self.engine.model_name:
                self.engine.model_name = model
                self.engine.unload()
            if language:
                self.engine.language = language
            if device_pref:
                self.engine.device_pref = device_pref
            if device is not None:
                self.cfg.audio.device = device

            mode = Mode.MEETING if mode_str == "meeting" else Mode.DICTATION
            session = Session(
                self.cfg,
                mode,
                self.engine,
                emit=self._emit,
                on_log=self._log,
            )
            self._session = session

        try:
            preflight = session.start()
            if not preflight.ok:
                with self._lock:
                    self._session = None
        except Exception as exc:
            self._log(f"could not start session: {exc}")
            with self._lock:
                self._session = None
            self._emit(
                ev.Failed(
                    session.session_id,
                    str(exc),
                    str(session.folder),
                )
            )

    def stop_session(self) -> None:
        with self._lock:
            session = self._session
            self._session = None

        if session is None:
            self._log("no active session to stop")
            return

        def work() -> None:
            try:
                session.stop()
            except Exception as exc:
                self._log(f"error stopping session: {exc}")

        threading.Thread(target=work, daemon=True, name="dito-engine-stop").start()

    def list_devices(self) -> None:
        inputs = devices.list_inputs()
        data = {
            "event": "devices",
            "devices": [
                {
                    "index": d.index,
                    "name": d.name,
                    "default": d.default,
                }
                for d in inputs
            ],
        }
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def status(self) -> None:
        data = {
            "event": "status",
            "state": "recording" if self._session else "idle",
            "model": self.engine.model_name,
            "backend": self.engine.backend,
        }
        sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def run(self) -> int:
        paths.ensure_dirs()
        self._emit(ev.Started("engine_ready", "engine", "init"))
        self.status()

        while True:
            try:
                raw_line = sys.stdin.readline()
            except Exception:
                break
            if not raw_line:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._log(f"invalid JSON: {line}")
                continue

            cmd = msg.get("cmd")
            if cmd == "start":
                self.start_session(
                    mode_str=msg.get("mode", "dictation"),
                    model=msg.get("model"),
                    language=msg.get("language"),
                    device=msg.get("device"),
                    device_pref=msg.get("device_pref"),
                )
            elif cmd == "stop":
                self.stop_session()
            elif cmd == "status":
                self.status()
            elif cmd == "list_devices":
                self.list_devices()
            elif cmd == "quit":
                self.stop_session()
                break
            else:
                self._log(f"unknown command: {cmd}")

        return 0


def run_server() -> int:
    return EngineServer().run()
