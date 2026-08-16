"""The settings tab: every change applies and saves at once, atomically, with no Save button."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from .. import __version__
from .. import config as cfgmod
from ..audio import devices
from ..i18n import AUTO, DEFAULT, _
from . import live
from .components import (
    Button,
    Card,
    ControlSize,
    Field,
    FormRow,
    Row,
    Select,
    Spin,
    Switch,
)
from .keycapture import KeyCapture
from .theme import Palette, Space


def _models() -> list[tuple[str, str]]:
    return [
        ("tiny", _("tiny — the fastest, gets more wrong")),
        ("base", _("base")),
        ("small", _("small — the balance (default)")),
        ("medium", _("medium — better, ~3× slower on the CPU")),
        ("large-v3", _("large-v3 — the best, heavy")),
    ]


def _themes() -> list[tuple[str, str]]:
    return [
        ("auto", _("Follow the system")),
        ("light", _("Light")),
        ("dark", _("Dark")),
    ]


def _languages() -> list[tuple[str, str]]:
    return [(AUTO, _("Follow the system")), (DEFAULT, "English"), ("pt_BR", "Português")]


def _devices(current: str = "") -> list[tuple[str, str]]:
    """A pinned input the app cannot open stays listed, labelled — silently dropping it rewrites
    the setting the moment the screen opens. See docs/armadilhas.md 1.12."""
    found = [("", _("System default"))]
    for d in devices.list_inputs():
        if devices.supports_rate(d.index):
            found.append((d.name, d.name))
        elif d.name == current:
            found.append((d.name, _("{device} — does not record at 16 kHz").format(device=d.name)))
    return found


class SettingsPage(QWidget):
    changed = Signal()
    # (version, problem) — the network answer, carried back to the Qt thread.
    _checked = Signal(str, str)
    notice = Signal(str)

    def __init__(
        self,
        cfg: cfgmod.Config,
        palette: Palette,
        pause_hotkeys: Callable[[], None] | None = None,
        resume_hotkeys: Callable[[], None] | None = None,
        conflicts: Callable[[str, str], str | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._palette = palette
        self._pause = pause_hotkeys or (lambda: None)
        self._resume = resume_hotkeys or (lambda: None)
        self._conflicts = conflicts or (lambda _k, _o: None)
        self._loading = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Space.LG)

        self._cards: list[Card] = []
        for build in (
            self._hotkeys_section,
            self._audio_section,
            self._stt_section,
            self._meeting_section,
            self._library_section,
            self._appearance_section,
            self._update_section,
        ):
            card = build()
            self._cards.append(card)
            root.addWidget(card)
        root.addStretch(1)

        # Built empty, filled here: one method owns every string, and it is the same one the
        # language switch calls later.
        self.retranslate()
        self._loading = False

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette

    # ---- sections --------------------------------------------------------------------

    def _hotkeys_section(self) -> Card:
        card = Card()
        self._hotkeys_card = card

        self.ptt = KeyCapture(
            self.cfg.hotkeys.push_to_talk,
            self._palette,
            validate=lambda k: self._validate(k, "push_to_talk"),
            on_capture_start=self._pause,
            on_capture_end=self._resume,
        )
        self.ptt.captured.connect(lambda k: self._set_key("push_to_talk", k))
        self.ptt.rejected.connect(lambda m: self._reject(self._ptt_row, m))

        self.meeting = KeyCapture(
            self.cfg.hotkeys.meeting_toggle,
            self._palette,
            validate=lambda k: self._validate(k, "meeting_toggle"),
            on_capture_start=self._pause,
            on_capture_end=self._resume,
        )
        self.meeting.captured.connect(lambda k: self._set_key("meeting_toggle", k))
        self.meeting.rejected.connect(lambda m: self._reject(self._meeting_row, m))

        self._ptt_row = FormRow("", self.ptt, errorable=True)
        self._meeting_row = FormRow("", self.meeting, errorable=True)
        card.add(Row(self._ptt_row, self._meeting_row))

        self.grab = Switch(
            self.cfg.hotkeys.grab, on_toggle=lambda v: self._set("hotkeys", "grab", v)
        )
        self._grab_row = FormRow("", self.grab, inline=True)
        card.add(self._grab_row)
        return card

    def _audio_section(self) -> Card:
        card = Card()
        self._audio_card = card

        self.device = Select(
            _devices(self.cfg.audio.device or ""),
            on_change=lambda v: self._set("audio", "device", v),
        )
        self.device.set_value(self.cfg.audio.device or "")
        self._device_row = FormRow("", self.device)
        card.add(self._device_row)

        self.alarm_sound = Switch(
            self.cfg.audio.alerts.sound, on_toggle=lambda v: self._set_alert("sound", v)
        )
        self._sound_row = FormRow("", self.alarm_sound, inline=True)

        self.alarm_notify = Switch(
            self.cfg.audio.alerts.notify, on_toggle=lambda v: self._set_alert("notify", v)
        )
        self._notify_row = FormRow("", self.alarm_notify, inline=True)
        card.add(self._sound_row, self._notify_row)
        return card

    def _stt_section(self) -> Card:
        card = Card()
        self._stt_card = card

        self.model = Select(_models(), on_change=lambda v: self._set("stt", "model", v))
        self.model.set_value(self.cfg.stt.model)
        self._model_row = FormRow("", self.model)
        card.add(self._model_row)

        self.paste = Switch(
            self.cfg.output.paste, on_toggle=lambda v: self._set("output", "paste", v)
        )
        self._paste_row = FormRow("", self.paste, inline=True)

        self.enter = Switch(
            self.cfg.output.enter, on_toggle=lambda v: self._set("output", "enter", v)
        )
        self._enter_row = FormRow("", self.enter, inline=True)
        card.add(self._paste_row, self._enter_row)

        self.unload = Spin(suffix=_(" min"), maximum=240)
        self.unload.setValue(self.cfg.stt.idle_unload_min)
        self.unload.valueChanged.connect(
            lambda v: self._set("stt", "idle_unload_min", float(v))
        )
        self._unload_row = FormRow("", self.unload)
        card.add(self._unload_row)
        return card

    def _meeting_section(self) -> Card:
        card = Card()
        self._meeting_card = card

        self.vault = Field(self.cfg.meeting.obsidian.vault)
        self.vault.editingFinished.connect(
            lambda: self._set_obsidian("vault", self.vault.text().strip())
        )
        self._vault_row = FormRow("", self.vault)
        card.add(self._vault_row)
        return card

    def _library_section(self) -> Card:
        card = Card()
        self._library_card = card

        self.library = Field(self.cfg.library.folder)
        self.library.editingFinished.connect(
            lambda: self._set("library", "folder", self.library.text().strip())
        )
        self._browse = Button(size=ControlSize.MD, on_click=self._pick_library)

        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(Space.SM)
        box.addWidget(self.library, 1)
        box.addWidget(self._browse)

        self._library_row = FormRow("", holder)
        card.add(self._library_row)
        return card

    def _appearance_section(self) -> Card:
        card = Card()
        self._appearance_card = card

        self.theme = Select(_themes(), on_change=self._set_theme)
        self.theme.set_value(self.cfg.ui.theme)
        self._theme_row = FormRow("", self.theme)

        self.language = Select(_languages(), on_change=self._set_language)
        self.language.set_value(self.cfg.ui.language)
        self._language_row = FormRow("", self.language)

        card.add(Row(self._theme_row, self._language_row))
        return card

    def _update_section(self) -> Card:
        card = Card()
        self._update_card = card

        self._check = Button(_("Check for updates"), on_click=self._check_updates)
        self._update_row = FormRow("", self._check)
        card.add(self._update_row)
        self._checked.connect(self._update_answered)
        return card

    def _check_updates(self) -> None:
        """Off the Qt thread: the request reaches GitHub over the network and can hang for
        seconds, and a settings window frozen mid-click reads as a crash."""
        self._check.set_loading(True)
        threading.Thread(target=self._ask_for_a_new_version, daemon=True).start()

    def _ask_for_a_new_version(self) -> None:
        from .. import update as updater

        try:
            release = updater.check()
        except updater.UpdateError as exc:
            self._checked.emit("", str(exc))
            return
        self._checked.emit(release.version if release else "", "")

    def _update_answered(self, version: str, problem: str) -> None:
        self._check.set_loading(False)
        if problem:
            self.notice.emit(problem)
        elif version:
            self.notice.emit(
                _("version {version} is out — run «dito update» to install it")
                .format(version=version)
            )
        else:
            self.notice.emit(
                _("Dito {version} is the newest there is.").format(version=__version__)
            )

    # ---- text ----------------------------------------------------------------------

    def retranslate(self) -> None:
        """Every visible string, re-read from the catalogue that is installed right now."""
        self._hotkeys_card.set_heading(_("Shortcuts"))
        self._ptt_row.set_texts(_("Dictate (hold)"), _("hold it, speak, let go"))
        self._meeting_row.set_texts(
            _("Meeting (toggle)"), _("press to start, press again to stop")
        )
        self._grab_row.set_texts(
            _("Swallow the key"), _("keeps it from reaching the text box underneath")
        )

        self._audio_card.set_heading(_("Microphone"))
        self._device_row.set_texts(
            _("Input"),
            _("kept by name, not by index: the index moves when a USB device comes or goes"),
        )
        self.device.set_options(_devices(self.cfg.audio.device or ""))
        self._sound_row.set_texts(_("Play a sound when the microphone stops picking up"))
        self._notify_row.set_texts(_("Show a system notification as well"))

        self._stt_card.set_heading(_("Transcription"))
        self._model_row.set_texts(
            _("Model"), _("changing the model downloads it on first use")
        )
        self.model.set_options(_models())
        self._paste_row.set_texts(_("Paste the text where the cursor is"))
        self._enter_row.set_texts(_("Press Enter after pasting"))
        self._unload_row.set_texts(
            _("Free the memory after"),
            _("0 keeps the model loaded. During a meeting it is never freed"),
        )
        self.unload.setSuffix(_(" min"))

        self._meeting_card.set_heading(
            _("Meeting"),
            _(
                "A meeting records until you stop it — there is no time limit. Dito does not "
                "summarise: the note comes out with the transcript and empty sections to fill in."
            ),
        )
        self._vault_row.set_texts(
            _("Obsidian vault"),
            _("if the folder does not exist Dito will NOT create it — the note stays in place"),
        )

        self._library_card.set_heading(
            _("Where the files go"),
            _("Only the text is kept. The audio is deleted as soon as it is transcribed."),
        )
        self._library_row.set_texts(_("Transcripts folder"))
        self._browse.set_text(_("Choose…"))

        self._update_card.set_heading(
            _("Updates"),
            _("You have Dito {version}.").format(version=__version__),
        )
        self._update_row.set_texts("")
        self._check.set_text(_("Check for updates"))

        self._appearance_card.set_heading(_("Appearance"))
        self._theme_row.set_texts(_("Theme"))
        self.theme.set_options(_themes())
        self._language_row.set_texts(_("Language"))
        self.language.set_options(_languages())

    # ---- persistence -----------------------------------------------------------------

    def _validate(self, key: str, owner: str) -> str | None:
        other = self._conflicts(key, owner)
        if other == "dictation":
            return _("that key is already the dictation one")
        if other:
            return _("that key is already the meeting one")
        return None

    def _reject(self, row: FormRow, message: str) -> None:
        row.set_error(message)
        self.notice.emit(message)

    def _set_key(self, field: str, key: str) -> None:
        self._ptt_row.set_error("")
        self._meeting_row.set_error("")
        setattr(self.cfg.hotkeys, field, key)
        self._persist()

    def _set(self, section: str, field: str, value) -> None:
        if self._loading:
            return
        setattr(getattr(self.cfg, section), field, value)
        self._persist()

    def _set_alert(self, field: str, value) -> None:
        setattr(self.cfg.audio.alerts, field, value)
        self._persist()

    def _set_obsidian(self, field: str, value) -> None:
        setattr(self.cfg.meeting.obsidian, field, value)
        self._persist()

    def _set_theme(self, value: str) -> None:
        """Applied to every window already open; nobody restarts an app to see a colour."""
        self._set("ui", "theme", value)
        if not self._loading:
            live.apply_theme(value)

    def _set_language(self, value: str) -> None:
        if self._loading:
            return
        self._set("ui", "language", value)
        live.apply_language(value)
        if not live.retranslates(self):
            self.notice.emit(_("the rest of the window changes language next time it opens"))

    def _persist(self) -> None:
        if self._loading:
            return
        cfgmod.save(self.cfg)
        self.changed.emit()

    def _pick_library(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, _("Transcripts folder"), self.library.text() or str(self.cfg.library_dir())
        )
        if chosen:
            self.library.setText(chosen)
            self._set("library", "folder", chosen)
