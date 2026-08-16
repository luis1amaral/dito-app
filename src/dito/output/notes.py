"""The meeting note in the `reuniao` skill's shape — see docs/armadilhas.md 10.2 and 10.3."""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..core.library import AUDIO_FILES

# Leaves room for the date prefix and a `-12` collision suffix on every filesystem.
SLUG_MAX = 60

# Marks the note as machine-created, so one search finds every meeting nobody filled in yet.
DEFAULT_TAGS = ("dito",)

FALLBACK_SLUG = "reuniao"


@dataclass(frozen=True)
class MeetingNote:
    """Only `folder`, `text` and `started` come from the recording; the rest a human adds."""

    folder: Path
    text: str
    seconds: float
    started: datetime
    subject: str = ""
    participants: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    links: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WrittenNote:
    path: Path
    in_vault: bool
    # Why the note did not reach the vault, in pt-BR and ready to show. `None` when it did.
    reason: str | None = None


def slugify(text: str, *, fallback: str = FALLBACK_SLUG, max_len: int = SLUG_MAX) -> str:
    """`Reunião: Orçamento` -> `reuniao-orcamento`, and armadilhas 10.6: also the `../` barrier."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", without_accents.lower()).strip("-")
    return slug[:max_len].strip("-") or fallback


def write_meeting_note(note: MeetingNote, cfg: Config) -> WrittenNote:
    """Write the note and return where it landed. Never overwrites an existing file."""
    stem = f"{note.started:%Y-%m-%d}-{slugify(note.subject)}"

    folder, reason = _vault_folder(cfg)
    if folder is not None:
        try:
            return WrittenNote(_write(folder, stem, note, cfg), in_vault=True)
        except OSError as exc:
            reason = f"não consegui escrever em {folder}: {exc}"

    note.folder.mkdir(parents=True, exist_ok=True)
    return WrittenNote(_write(note.folder, stem, note, cfg), in_vault=False, reason=reason)


def _vault_folder(cfg: Config) -> tuple[Path | None, str | None]:
    vault = cfg.vault_dir()
    if not vault.is_dir():
        return None, f"o cofre {vault} não existe — a nota ficou junto da gravação"

    folder = vault / cfg.meeting.obsidian.folder
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"não consegui criar {folder}: {exc}"
    return folder, None


def _write(folder: Path, stem: str, note: MeetingNote, cfg: Config) -> Path:
    """Claim the filename first: the body names the audio beside it, suffix and all."""
    path = _claim(folder, stem)
    try:
        audio = _copy_audio(note, path, cfg)
        path.write_text(_render(note, audio), encoding="utf-8")
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return path


def _claim(folder: Path, stem: str) -> Path:
    """Exclusive create, never `exists()` then write — armadilhas 10.5: that race overwrites."""
    attempt = 1
    while True:
        suffix = "" if attempt == 1 else f"-{attempt}"
        path = folder / f"{stem}{suffix}.md"
        try:
            path.touch(exist_ok=False)
        except FileExistsError:
            attempt += 1
            continue
        return path


def _copy_audio(note: MeetingNote, path: Path, cfg: Config) -> str | None:
    """Off by default, and that default matters — see docs/armadilhas.md 10.4 (Obsidian Git)."""
    if not cfg.meeting.obsidian.copy_audio:
        return None

    source = next((note.folder / name for name in AUDIO_FILES if (note.folder / name).is_file()),
                  None)
    if source is None:
        return None

    target = path.with_suffix(source.suffix)
    try:
        shutil.copy2(source, target)
    except OSError:
        return None
    return target.name


def _render(note: MeetingNote, audio_name: str | None) -> str:
    tags = list(DEFAULT_TAGS) + [t for t in note.tags if t not in DEFAULT_TAGS]
    duration = hms(note.seconds)

    lines = [
        "---",
        f"data: {note.started:%Y-%m-%d}",
        "tipo: reuniao",
        f"participantes: [{', '.join(note.participants)}]",
        f"tags: [{', '.join(tags)}]",
        f"duracao: {duration}",
        "---",
        "",
        f"# Reunião — {note.subject.strip()}" if note.subject.strip() else "# Reunião",
        "",
        f"Gravada pelo Dito em {note.started:%d/%m/%Y às %H:%M} · {duration}.",
        f"Áudio e transcrição: [{note.folder.name}]({_uri(note.folder)})",
    ]
    if audio_name:
        lines.append(f"![[{audio_name}]]")

    # Empty on purpose — see docs/armadilhas.md 10.3: Dito heard the meeting, it was not in it.
    lines += ["", "## Decidido", "", "## Pendências", "", "## Discutido, sem decisão", ""]

    lines.append("## Ligações")
    lines.append("")
    lines += [f"[[{link}]]" for link in note.links]
    if note.links:
        lines.append("")

    # A pasted transcript is not the note: folded at the end, readable, still the source above.
    lines += [
        "<details>",
        "<summary>Transcrição bruta</summary>",
        "",
        note.text.strip() or "(nada foi transcrito)",
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def hms(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _uri(folder: Path) -> str:
    """`as_uri` percent-encodes spaces, which is what a markdown `file://` link needs."""
    try:
        return folder.resolve().as_uri()
    except ValueError:
        return str(folder)
