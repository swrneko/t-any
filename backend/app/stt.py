from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.errors import ApiError
from app.languages import normalize_language

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=900.0, write=300.0, pool=10.0)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcription:
    language: str | None
    text: str
    segments: list[Segment]
    raw: dict[str, Any]


def stt_http_client(base_url: str, api_key: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )


class SttClient:
    """Speech to text over the OpenAI transcription protocol.

    Deliberately not sharing an abstraction with the LLM client: different
    endpoint, different payload, different failure modes. A common "AI provider"
    interface would be a false generalisation.
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def transcribe(
        self,
        audio: Path,
        *,
        model: str,
        language: str | None = None,
        prompt: str | None = None,
    ) -> Transcription:
        data = {"model": model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt

        with audio.open("rb") as handle:
            try:
                response = await self._http.post(
                    "/audio/transcriptions",
                    data=data,
                    files={"file": (audio.name, handle, "application/octet-stream")},
                )
            except httpx.RequestError as cause:
                raise ApiError(
                    502,
                    "stt_unreachable",
                    f"Cannot reach the speech-to-text server at {self._http.base_url}.",
                    base_url=str(self._http.base_url),
                ) from cause

        if response.status_code >= 500:
            # The server is unwell rather than the request malformed: worth
            # sending again after a pause.
            raise ApiError(
                502,
                "stt_server_error",
                f"The speech-to-text server answered {response.status_code}.",
                status=response.status_code,
                detail=response.text[:500],
            )

        if response.status_code >= 400:
            raise ApiError(
                502,
                "stt_rejected_request",
                f"The speech-to-text server answered {response.status_code}.",
                status=response.status_code,
                detail=response.text[:500],
            )

        return _parse(response.json())


def _parse(payload: dict[str, Any]) -> Transcription:
    text = (payload.get("text") or "").strip()
    raw_segments = payload.get("segments") or []

    segments = [
        Segment(
            start=float(item.get("start", 0.0)),
            end=float(item.get("end", 0.0)),
            text=(item.get("text") or "").strip(),
        )
        for item in raw_segments
    ]

    if not segments and text:
        # Some servers advertise verbose_json but return only a flat string.
        # One segment spanning the file keeps every consumer downstream working.
        segments = [Segment(start=0.0, end=float(payload.get("duration") or 0.0), text=text)]

    return Transcription(
        # Normalised here rather than where it is used: this is the boundary the
        # provider's wording arrives at, and `raw` keeps it verbatim anyway.
        language=normalize_language(payload.get("language")),
        text=text,
        segments=segments,
        raw=payload,
    )
