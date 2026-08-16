"""The settings tab: every change applies and saves at once, atomically, with no Save button."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config as cfgmod
from ..audio import devices
from .keycapture import KeyCapture
from .theme import Palette, Space, Type

MODELS = [
    ("tiny", "tiny — o mais rápido, erra mais"),
    ("base", "base"),
    ("small", "small — equilíbrio (padrão)"),
    ("medium", "medium — melhor, ~3× mais lento na CPU"),
    ("large-v3", "large-v3 — o melhor, pesado"),
]


def _section(title: str, p: Palette) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setProperty("role", "card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(Space.XL, Space.LG, Space.XL, Space.LG)
    outer.setSpacing(Space.MD)

    heading = QLabel(title)
    heading.setProperty("role", "title")
    outer.addWidget(heading)
    return card, outer


def _row(label: str, widget: QWidget, hint: str = "") -> QWidget:
    """Label, hint, control: the gap inside a field must stay smaller than the gap between."""
    holder = QWidget()
    box = QVBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(Space.XS)

    caption = QLabel(label)
    box.addWidget(caption)
    if hint:
        note = QLabel(hint)
        note.setProperty("role", "hint")
        note.setWordWrap(True)
        box.addWidget(note)
    box.addWidget(widget)
    return holder


class SettingsPage(QWidget):
    changed = Signal()
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

        root.addWidget(self._hotkeys_section())
        root.addWidget(self._audio_section())
        root.addWidget(self._stt_section())
        root.addWidget(self._meeting_section())
        root.addWidget(self._library_section())
        root.addStretch(1)

        self._loading = False

    # ---- sections --------------------------------------------------------------------

    def _hotkeys_section(self) -> QFrame:
        card, box = _section("Atalhos", self._palette)

        self.ptt = KeyCapture(
            self.cfg.hotkeys.push_to_talk,
            self._palette,
            validate=lambda k: self._validate(k, "push_to_talk"),
            on_capture_start=self._pause,
            on_capture_end=self._resume,
        )
        self.ptt.captured.connect(lambda k: self._set_key("push_to_talk", k))
        self.ptt.rejected.connect(self.notice.emit)

        self.meeting = KeyCapture(
            self.cfg.hotkeys.meeting_toggle,
            self._palette,
            validate=lambda k: self._validate(k, "meeting_toggle"),
            on_capture_start=self._pause,
            on_capture_end=self._resume,
        )
        self.meeting.captured.connect(lambda k: self._set_key("meeting_toggle", k))
        self.meeting.rejected.connect(self.notice.emit)

        row = QHBoxLayout()
        row.setSpacing(Space.LG)
        row.addWidget(_row("Ditar (segurar)", self.ptt, "segure, fale, solte"), 1)
        row.addWidget(
            _row("Reunião (alternar)", self.meeting, "aperta para começar, aperta para parar"), 1
        )
        holder = QWidget()
        holder.setLayout(row)
        box.addWidget(holder)

        self.grab = QCheckBox("Consumir a tecla (não deixa vazar para o campo de texto)")
        self.grab.setChecked(self.cfg.hotkeys.grab)
        self.grab.toggled.connect(lambda v: self._set("hotkeys", "grab", v))
        box.addWidget(self.grab)
        return card

    def _audio_section(self) -> QFrame:
        card, box = _section("Microfone", self._palette)

        self.device = QComboBox()
        self.device.addItem("Padrão do sistema", "")
        for d in devices.list_inputs():
            self.device.addItem(d.name, d.name)
        current = self.cfg.audio.device
        index = self.device.findData(current) if current else 0
        self.device.setCurrentIndex(index if index >= 0 else 0)
        self.device.currentIndexChanged.connect(
            lambda: self._set("audio", "device", self.device.currentData())
        )
        box.addWidget(
            _row(
                "Entrada",
                self.device,
                "guardado pelo nome, não pelo índice: o índice muda quando um USB entra ou sai",
            )
        )

        self.alarm_sound = QCheckBox("Tocar um som quando o microfone parar de captar")
        self.alarm_sound.setChecked(self.cfg.audio.alerts.sound)
        self.alarm_sound.toggled.connect(lambda v: self._set_alert("sound", v))
        box.addWidget(self.alarm_sound)

        self.alarm_notify = QCheckBox("Mostrar notificação do sistema junto")
        self.alarm_notify.setChecked(self.cfg.audio.alerts.notify)
        self.alarm_notify.toggled.connect(lambda v: self._set_alert("notify", v))
        box.addWidget(self.alarm_notify)
        return card

    def _stt_section(self) -> QFrame:
        card, box = _section("Transcrição", self._palette)

        self.model = QComboBox()
        for value, label in MODELS:
            self.model.addItem(label, value)
        idx = self.model.findData(self.cfg.stt.model)
        self.model.setCurrentIndex(idx if idx >= 0 else 2)
        self.model.currentIndexChanged.connect(
            lambda: self._set("stt", "model", self.model.currentData())
        )
        box.addWidget(
            _row("Modelo", self.model, "trocar de modelo baixa os arquivos no primeiro uso")
        )

        self.paste = QCheckBox("Colar o texto onde o cursor estiver")
        self.paste.setChecked(self.cfg.output.paste)
        self.paste.toggled.connect(lambda v: self._set("output", "paste", v))
        box.addWidget(self.paste)

        self.enter = QCheckBox("Dar Enter depois de colar")
        self.enter.setChecked(self.cfg.output.enter)
        self.enter.toggled.connect(lambda v: self._set("output", "enter", v))
        box.addWidget(self.enter)

        self.unload = QDoubleSpinBox()
        self.unload.setRange(0, 240)
        self.unload.setSuffix(" min")
        self.unload.setValue(self.cfg.stt.idle_unload_min)
        self.unload.valueChanged.connect(lambda v: self._set("stt", "idle_unload_min", float(v)))
        box.addWidget(
            _row(
                "Liberar a memória depois de",
                self.unload,
                "0 mantém o modelo carregado. Durante uma reunião ele nunca é liberado",
            )
        )
        return card

    def _meeting_section(self) -> QFrame:
        card, box = _section("Reunião", self._palette)

        note = QLabel(
            "A reunião grava até você mandar parar — não há limite de tempo. "
            "O Dito não resume: a nota sai com a transcrição e as seções prontas para preencher."
        )
        note.setProperty("role", "hint")
        note.setWordWrap(True)
        box.addWidget(note)

        self.vault = QLineEdit(self.cfg.meeting.obsidian.vault)
        self.vault.editingFinished.connect(
            lambda: self._set_obsidian("vault", self.vault.text().strip())
        )
        box.addWidget(
            _row(
                "Cofre do Obsidian",
                self.vault,
                "se a pasta não existir, o Dito NÃO a cria — a nota fica na pasta da sessão",
            )
        )

        self.save_audio = QCheckBox("Guardar o áudio da reunião")
        self.save_audio.setChecked(self.cfg.meeting.save_audio)
        self.save_audio.toggled.connect(lambda v: self._set("meeting", "save_audio", v))
        box.addWidget(self.save_audio)

        self.compress = QCheckBox("Comprimir para Opus quando terminar (3 h ≈ 32 MB)")
        self.compress.setChecked(self.cfg.meeting.compress_audio)
        self.compress.toggled.connect(lambda v: self._set("meeting", "compress_audio", v))
        box.addWidget(self.compress)

        self.copy_audio = QCheckBox("Copiar o áudio para dentro do cofre")
        self.copy_audio.setChecked(self.cfg.meeting.obsidian.copy_audio)
        self.copy_audio.setToolTip(
            "Desligado por padrão: o cofre é repositório git com auto-commit, e dezenas de MB "
            "commitados por engano são caros de tirar do histórico."
        )
        self.copy_audio.toggled.connect(lambda v: self._set_obsidian("copy_audio", v))
        box.addWidget(self.copy_audio)
        return card

    def _library_section(self) -> QFrame:
        card, box = _section("Onde ficam os arquivos", self._palette)

        row = QHBoxLayout()
        row.setSpacing(Space.SM)
        self.library = QLineEdit(self.cfg.library.folder)
        self.library.editingFinished.connect(
            lambda: self._set("library", "folder", self.library.text().strip())
        )
        browse = QPushButton("Escolher…")
        browse.clicked.connect(self._pick_library)
        row.addWidget(self.library, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        box.addWidget(_row("Pasta das transcrições", holder))

        self.theme = QComboBox()
        for value, label in (("auto", "Seguir o sistema"), ("light", "Claro"), ("dark", "Escuro")):
            self.theme.addItem(label, value)
        idx = self.theme.findData(self.cfg.ui.theme)
        self.theme.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme.currentIndexChanged.connect(
            lambda: self._set("ui", "theme", self.theme.currentData())
        )
        box.addWidget(_row("Tema", self.theme))

        self.autostart = QCheckBox("Iniciar junto com o sistema (sem abrir janela)")
        self.autostart.setChecked(self.cfg.ui.autostart)
        self.autostart.toggled.connect(lambda v: self._set("ui", "autostart", v))
        box.addWidget(self.autostart)
        return card

    # ---- persistence -----------------------------------------------------------------

    def _validate(self, key: str, owner: str) -> str | None:
        other = self._conflicts(key, owner)
        if other:
            nome = "ditar" if other == "dictation" else "reunião"
            return f"essa tecla já é a de {nome}"
        return None

    def _set_key(self, field: str, key: str) -> None:
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

    def _persist(self) -> None:
        if self._loading:
            return
        cfgmod.save(self.cfg)
        self.changed.emit()

    def _pick_library(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Pasta das transcrições", self.library.text() or str(self.cfg.library_dir())
        )
        if chosen:
            self.library.setText(chosen)
            self._set("library", "folder", chosen)


def apply_hint_style(widget: QWidget, palette: Palette) -> None:
    widget.setStyleSheet(f"color: {palette.text_muted}; font-size: {Type.CAPTION}px;")
    widget.setAlignment(Qt.AlignmentFlag.AlignLeft)
