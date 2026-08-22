import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.errors import ApiError

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Opus at 16 kHz mono, 32 kbps: roughly 14 MB per hour against 115 MB for WAV.
# The codec was designed for speech, costs nothing in recognition accuracy, and
# keeps a two-hour recording inside the 25 MB limit cloud endpoints impose.
TARGET_SAMPLE_RATE = 16_000
TARGET_BITRATE = "32k"

# A pause has to be quiet enough and long enough to be a sentence break rather
# than a breath. These are ffmpeg's silencedetect parameters, nothing learned.
SILENCE_NOISE_FLOOR = "-35dB"
SILENCE_MIN_DURATION = 0.4

SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


@dataclass(frozen=True)
class MediaInfo:
    duration_sec: float
    codec: str | None
    sample_rate: int | None
    channels: int | None

    @property
    def has_audio(self) -> bool:
        return self.codec is not None


async def run(program: str, *args: str) -> tuple[int, bytes, bytes]:
    """Run an external tool -- ffmpeg, ffprobe, yt-dlp -- and return its exit
    code, stdout and stderr.

    stderr is kept rather than discarded on both paths: ffmpeg's diagnostics are
    the only clue when a container is malformed, and silencedetect reports its
    findings there while exiting successfully.
    """
    process = await asyncio.create_subprocess_exec(
        program,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        # Cancelling the coroutine would otherwise leave ffmpeg running, which
        # is the whole reason a cancel button that only sets a flag is a lie.
        process.kill()
        await process.wait()
        raise
    return process.returncode or 0, stdout, stderr


async def probe(path: Path) -> MediaInfo:
    """Read what a file actually is. A pure reader: a media file with no audio
    track is a valid answer here, and the caller decides whether that is fatal."""
    code, output, _ = await run(
        FFPROBE,
        "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    )
    if code != 0:
        raise ApiError(
            415,
            "unsupported_media",
            "This file is not audio or video that ffmpeg can read.",
            filename=path.name,
        )

    payload = json.loads(output)
    streams = payload.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = payload.get("format", {}).get("duration")
    if duration is None and audio is not None:
        duration = audio.get("duration")

    return MediaInfo(
        duration_sec=float(duration or 0.0),
        codec=audio.get("codec_name") if audio else None,
        sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        channels=int(audio["channels"]) if audio and audio.get("channels") else None,
    )


async def extract_chunk(source: Path, target: Path, *, start: float, end: float) -> None:
    """Copy one span out of the normalised audio.

    Stream copy, not re-encode: the source is already the target format, so
    cutting a two-hour file into chunks costs seconds instead of minutes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await run(
        FFMPEG,
        "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{start:.3f}",
        "-i", str(source),
        "-t", f"{end - start:.3f}",
        "-c", "copy",
        "-y", str(target),
    )
    if code != 0:
        target.unlink(missing_ok=True)
        raise ApiError(
            422,
            "chunking_failed",
            "ffmpeg could not cut this audio into chunks.",
            detail=stderr.decode(errors="replace").strip()[:500],
        )


async def detect_silences(path: Path) -> list[tuple[float, float]]:
    """Where the recording goes quiet, according to ffmpeg and nothing else.

    No model, no VAD: the only question is where a cut will not land mid-word,
    and an amplitude threshold answers it well enough for that.
    """
    duration = (await probe(path)).duration_sec

    _, _, stderr = await run(
        FFMPEG,
        "-hide_banner", "-nostdin",
        "-i", str(path),
        "-af", f"silencedetect=noise={SILENCE_NOISE_FLOOR}:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-",
    )

    report = stderr.decode(errors="replace")
    starts = [float(match) for match in SILENCE_START.findall(report)]
    ends = [float(match) for match in SILENCE_END.findall(report)]

    silences: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        # A file that ends mid-pause gets a start with no end. Closing it at the
        # duration keeps a legitimate cut point instead of discarding it.
        end = ends[index] if index < len(ends) else duration
        silences.append((max(start, 0.0), min(end, duration)))

    return [(start, end) for start, end in silences if end > start]


async def normalize_to_opus(source: Path, target: Path) -> MediaInfo:
    """Extract audio and re-encode it to the one format the rest of the
    pipeline knows about. Returns the probe of the result."""
    info = await probe(source)
    if not info.has_audio:
        raise ApiError(
            422,
            "no_audio_stream",
            "This file has no audio track to transcribe.",
            filename=source.name,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await run(
        FFMPEG,
        "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(source),
        "-vn",
        "-map", "0:a:0",
        "-ac", "1",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-c:a", "libopus",
        "-b:a", TARGET_BITRATE,
        "-application", "voip",
        "-y", str(target),
    )
    if code != 0:
        target.unlink(missing_ok=True)
        raise ApiError(
            422,
            "normalisation_failed",
            "ffmpeg could not convert this file.",
            detail=stderr.decode(errors="replace").strip()[:500],
        )

    return await probe(target)


async def join_to_opus(sources: Sequence[Path], target: Path) -> MediaInfo:
    """Several files, in the order given, as one recording.

    The concat filter rather than the concat demuxer: the parts may have been
    recorded on different devices, and the filter decodes each of them before
    joining, so mismatched sample rates and codecs cost nothing but time. The
    demuxer would refuse them, or worse, produce a file whose timestamps drift.
    """
    if len(sources) == 1:
        return await normalize_to_opus(sources[0], target)

    for source in sources:
        if not (await probe(source)).has_audio:
            raise ApiError(
                422,
                "no_audio_stream",
                "This file has no audio track to transcribe.",
                filename=source.name,
            )

    inputs: list[str] = []
    for source in sources:
        inputs += ["-i", str(source)]
    streams = "".join(f"[{index}:a:0]" for index in range(len(sources)))

    target.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await run(
        FFMPEG,
        "-hide_banner", "-loglevel", "error", "-nostdin",
        *inputs,
        "-filter_complex", f"{streams}concat=n={len(sources)}:v=0:a=1[out]",
        "-map", "[out]",
        "-ac", "1",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-c:a", "libopus",
        "-b:a", TARGET_BITRATE,
        "-application", "voip",
        "-y", str(target),
    )
    if code != 0:
        target.unlink(missing_ok=True)
        raise ApiError(
            422,
            "normalisation_failed",
            "ffmpeg could not join these files.",
            detail=stderr.decode(errors="replace").strip()[:500],
        )

    return await probe(target)
