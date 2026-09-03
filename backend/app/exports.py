"""Turning a transcript into whatever a person wants to paste somewhere.

Every format is rendered on demand and nothing is stored: the provider's answer
is the only durable thing, and changing how a caption file looks must never mean
transcribing a recording again.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

FORMATS = ("txt", "md", "srt", "vtt", "json")

MEDIA_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "json": "application/json",
}

# Where one paragraph ends and the next begins. Long enough that a breath does
# not split a sentence, short enough that a change of subject does.
PARAGRAPH_GAP_SECONDS = 2.5


@dataclass(frozen=True)
class Line:
    start: float
    end: float
    text: str
    speaker: str | None = None


def lines_from(rows: Iterable[Any], names: Mapping[str, str] | None = None) -> list[Line]:
    """Segments as they should read: an edit wins over the original, always,
    and a speaker is called whatever someone renamed them to.

    Deliberately duck-typed rather than importing the model -- this module knows
    about text and time, and nothing about the database.
    """
    return [
        Line(
            start=row.start,
            end=row.end,
            text=(row.edited_text if row.edited_text is not None else row.text).strip(),
            speaker=(names or {}).get(row.speaker, row.speaker) if row.speaker else None,
        )
        for row in rows
    ]


@dataclass(frozen=True)
class Options:
    timestamps: bool = False
    speakers: bool = True


def render(
    fmt: str,
    lines: list[Line],
    *,
    title: str,
    language: str | None = None,
    duration_sec: float | None = None,
    source: str | None = None,
    options: Options | None = None,
) -> str:
    opts = options or Options()
    if fmt == "srt":
        return _subtitles(lines, opts, separator=",", header="")
    if fmt == "vtt":
        return _subtitles(lines, opts, separator=".", header="WEBVTT\n\n")
    if fmt == "md":
        return _markdown(lines, opts, title, language, duration_sec, source)
    return _plain(lines, opts)


def _prefix(line: Line, opts: Options) -> str:
    parts = []
    if opts.timestamps:
        parts.append(f"[{_clock(line.start)}]")
    if opts.speakers and line.speaker:
        parts.append(f"{line.speaker}:")
    return " ".join(parts)


def _per_segment(lines: list[Line], opts: Options) -> bool:
    """Whether every segment gets its own line.

    A timestamped or attributed export is for finding a moment, and merging
    segments into a paragraph is exactly what hides it.
    """
    return opts.timestamps or (opts.speakers and any(line.speaker for line in lines))


def _paragraphs(lines: list[Line], opts: Options) -> list[str]:
    """Group lines into paragraphs at the pauses."""
    if _per_segment(lines, opts):
        return [f"{_prefix(line, opts)} {line.text}".strip() for line in lines]

    blocks: list[list[str]] = []
    previous: Line | None = None
    for line in lines:
        if previous is None or line.start - previous.end > PARAGRAPH_GAP_SECONDS:
            blocks.append([])
        blocks[-1].append(line.text)
        previous = line
    return [" ".join(block) for block in blocks]


def _plain(lines: list[Line], opts: Options) -> str:
    blocks = _paragraphs(lines, opts)
    if not blocks:
        return ""
    joiner = "\n" if _per_segment(lines, opts) else "\n\n"
    return joiner.join(blocks) + "\n"


def _markdown(
    lines: list[Line],
    opts: Options,
    title: str,
    language: str | None,
    duration_sec: float | None,
    source: str | None,
) -> str:
    head = [f"# {title}", ""]
    facts = []
    if source:
        facts.append(f"- Source: {source}")
    if language:
        facts.append(f"- Language: {language}")
    if duration_sec is not None:
        facts.append(f"- Duration: {_clock(duration_sec)}")
    if facts:
        head.extend([*facts, ""])

    joiner = "\n" if _per_segment(lines, opts) else "\n\n"
    return "\n".join(head) + joiner.join(_paragraphs(lines, opts)) + "\n"


def _subtitles(lines: list[Line], opts: Options, *, separator: str, header: str) -> str:
    cues = []
    for index, line in enumerate(lines, start=1):
        text = line.text
        if opts.speakers and line.speaker:
            text = f"{line.speaker}: {text}"
        cues.append(
            f"{index}\n"
            f"{_timecode(line.start, separator)} --> {_timecode(line.end, separator)}\n"
            f"{text}\n"
        )
    return header + "\n".join(cues)


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _timecode(seconds: float, separator: str) -> str:
    milliseconds = round(seconds * 1000)
    return f"{_clock(milliseconds / 1000)}{separator}{milliseconds % 1000:03d}"
