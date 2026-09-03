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
    # Filled only by a model that diarises as it transcribes. Everything else
    # leaves it None and the speaker arrives later, from the diariser.
    speaker: str | None = None


# Models that answer with speakers as well as words, and therefore make the
# separate diarisation stage unnecessary -- one request, one clustering, and no
# merging two services' timelines by overlap.
#
# A table rather than a capability probe, because there is nothing to probe:
# `diarized_json` is a format one model accepts and every other transcription
# endpoint rejects, so asking is a failed job. A model added to this list is a
# one-line release; a model missing from it still transcribes, and the diariser
# answers for the speakers as before.
DIARIZING_MODELS = ("gpt-4o-transcribe-diarize",)


def diarizes(model: str) -> bool:
    """Whether this model answers with speakers as well as words.

    Matched on the last path segment, so a gateway's
    `openai/gpt-4o-transcribe-diarize` is the same model as OpenAI's own, and
    by prefix, because the same model is published under suffixed names -- ask
    OpenAI for `gpt-4o-transcribe-diarize` and its own error messages call it
    `gpt-4o-transcribe-diarize-api-ev3`. An exact match would send the wrong
    format to every snapshot of a model it recognises the base name of.
    """
    name = model.rsplit("/", 1)[-1].strip().lower()
    return any(name.startswith(known) for known in DIARIZING_MODELS)


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
        # The format follows the model and nothing else. A diarising model
        # refuses `verbose_json` outright -- it answers in `json`, `text` or
        # `diarized_json`, and only the last of those carries timestamps -- so
        # asking it for anything else is a 400 whatever the job wanted. Whether
        # the speakers it reports are used is decided upstream; whether they
        # can be asked for is decided here, by the model.
        speaks = diarizes(model)
        data = {
            "model": model,
            "response_format": "diarized_json" if speaks else "verbose_json",
        }
        if speaks:
            # Required above thirty seconds. The model cuts the recording
            # itself and keeps one speaker the same speaker across its own
            # cuts, which is exactly what we cannot do from out here.
            data["chunking_strategy"] = "auto"
        if language:
            data["language"] = language
        # The diarising model refuses a prompt outright, and a job that carried
        # one would fail on a field nobody asked about.
        if prompt and not speaks:
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
            # Present only in `diarized_json`. The label is whatever the model
            # called the voice -- "A", "B", or the name it was given a
            # reference clip for -- and is kept verbatim.
            speaker=(item.get("speaker") or None),
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
