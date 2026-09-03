"""Who was speaking, and when.

No OpenAI-compatible endpoint exists for this, so the diariser is a service with
a contract of its own: POST an audio file to /diarize, get back turns. It is a
third HTTP client rather than a branch in the speech-to-text one, for the same
reason the LLM client is separate -- a shared "AI provider" would be a false
generalisation over three different protocols.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import Provider
from app.stt import diarizes

# Diarisation is slower than transcription and has no streaming form: an hour of
# audio on a CPU is minutes of waiting for one answer.
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=1800.0, write=300.0, pool=10.0)


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    speaker: str


async def speakers_can_be_found(session: AsyncSession, settings: Settings) -> bool:
    """Whether this instance can answer "who said that" at all, either way.

    Two arrangements answer it. A diariser of our own, which is a container
    with model weights in it and is off by default; or a transcription model
    that reports speakers along with the words, in which case there is nothing
    to install and nothing to merge. The UI asks one question and gets one
    answer, because from where somebody is standing it is one feature.

    The provider is looked up the same way the worker looks it up when it comes
    to run the job -- default first, oldest next -- so what is offered here is
    what will actually happen.
    """
    if settings.diarizer_url:
        return True

    provider = await session.scalar(
        select(Provider)
        .where(Provider.kind == "stt")
        .order_by(Provider.is_default.desc(), Provider.created_at)
        .limit(1)
    )
    return provider is not None and diarizes(provider.default_model or "")


def diarizer_http_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=DEFAULT_TIMEOUT)


class DiarizerClient:
    """POST an audio file, get the turns back."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def diarize(self, audio: Path) -> list[Turn]:
        with audio.open("rb") as handle:
            try:
                response = await self._http.post(
                    "/diarize",
                    files={"file": (audio.name, handle, "application/octet-stream")},
                )
            except httpx.RequestError as cause:
                raise ApiError(
                    502,
                    "diarizer_unreachable",
                    f"Cannot reach the diariser at {self._http.base_url}.",
                    base_url=str(self._http.base_url),
                ) from cause

        if response.status_code >= 400:
            raise ApiError(
                502,
                "diarizer_failed",
                f"The diariser answered {response.status_code}.",
                status=response.status_code,
                detail=response.text[:500],
            )

        return _parse(response.json())


def _parse(payload: Any) -> list[Turn]:
    # An envelope or a bare list: the contract is ours, but the thing people put
    # behind it is usually a wrapper somebody wrote in an afternoon.
    items = payload.get("segments", []) if isinstance(payload, dict) else payload
    return [
        Turn(
            start=float(item["start"]),
            end=float(item["end"]),
            speaker=str(item.get("speaker") or "SPEAKER_00"),
        )
        for item in items
    ]


def assign_speakers(
    spans: Iterable[tuple[float, float]], turns: Sequence[Turn]
) -> list[str | None]:
    """Attribute each transcript segment to the speaker it overlaps most.

    Two independent models cut the same recording in two different places, so
    the boundaries never line up: the merge has to be an overlap measure rather
    than a lookup. A segment nobody was speaking over -- silence, music, a
    diariser that gave up -- stays unattributed instead of borrowing whoever
    happened to be nearest.
    """
    assigned: list[str | None] = []

    for start, end in spans:
        best: str | None = None
        longest = 0.0
        for turn in turns:
            overlap = min(end, turn.end) - max(start, turn.start)
            if overlap > longest:
                best, longest = turn.speaker, overlap
        assigned.append(best)

    return assigned
