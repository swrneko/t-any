import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

WHISPER_VERBOSE_JSON: dict[str, Any] = {
    "task": "transcribe",
    "language": "en",
    "duration": 3.0,
    "text": "Hello there. General Kenobi.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 1.4, "text": " Hello there."},
        {"id": 1, "start": 1.4, "end": 3.0, "text": " General Kenobi."},
    ],
}


@dataclass
class RecordedRequest:
    fields: dict[str, str] = field(default_factory=dict)
    filename: str | None = None
    file_size: int = 0
    authorization: str | None = None


class SttStub:
    """A stand-in for an OpenAI-compatible transcription endpoint.

    A stub rather than a patch, so the multipart body is really encoded by httpx
    and really parsed on the far side. A patch would only prove that we called
    our own function.
    """

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        status: int = 200,
        payload_for: Callable[[int], dict[str, Any]] | None = None,
        status_for: Callable[[int], int] | None = None,
        hold: asyncio.Event | None = None,
    ) -> None:
        fixed = WHISPER_VERBOSE_JSON if payload is None else payload
        self._payload_for = payload_for or (lambda _index: fixed)
        self._status_for = status_for or (lambda _index: status)
        # When set, the handler blocks until released -- lets a test act while a
        # request is genuinely in flight.
        self._hold = hold
        self.received = asyncio.Event()
        self.calls: list[RecordedRequest] = []
        self.app = FastAPI()

        @self.app.post("/v1/audio/transcriptions")
        async def transcriptions(request: Request) -> JSONResponse:
            index = len(self.calls)
            async with request.form() as form:
                upload = form.get("file")
                recorded = RecordedRequest(
                    fields={k: v for k, v in form.items() if isinstance(v, str)},
                    authorization=request.headers.get("Authorization"),
                )
                if upload is not None and not isinstance(upload, str):
                    recorded.filename = upload.filename
                    recorded.file_size = len(await upload.read())
            self.calls.append(recorded)
            self.received.set()
            if self._hold is not None:
                await self._hold.wait()
            return JSONResponse(self._payload_for(index), status_code=self._status_for(index))

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://stt.test/v1",
            headers={"Authorization": "Bearer sk-test"},
        )


FAKE_YTDLP = '''#!/usr/bin/env python3
"""A yt-dlp that never leaves the machine.

It honours the parts of the contract the worker depends on -- the output
template, the info json beside the media, the thumbnail, the printed path --
and nothing else. The real binary is a boundary; this proves we speak to it
correctly, not that it works.
"""
import json
import shutil
import sys
from pathlib import Path

argv = sys.argv[1:]
template = Path(argv[argv.index("-o") + 1])
base = template.with_name(template.name.removesuffix(".%(ext)s"))
base.parent.mkdir(parents=True, exist_ok=True)

if EXIT_CODE:
    sys.stderr.write("ERROR: [youtube] video unavailable\\n")
    sys.exit(EXIT_CODE)

media = base.with_suffix(".m4a")
shutil.copyfile(AUDIO, media)
base.with_suffix(".info.json").write_text(json.dumps(INFO), encoding="utf-8")
base.with_suffix(".jpg").write_bytes(b"\\xff\\xd8\\xff\\xdb thumbnail")
print(media)
'''


def write_fake_ytdlp(
    path: Path, *, audio: Path | None = None, info: dict[str, Any] | None = None, exit_code: int = 0
) -> Path:
    """Put a stand-in yt-dlp on disk and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = (
        FAKE_YTDLP.replace("AUDIO", repr(str(audio)))
        .replace("INFO", repr(info or {}))
        .replace("EXIT_CODE", str(exit_code))
    )
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


class MediaStub:
    """A stand-in for whatever web server a direct link points at.

    A real server rather than a patched client: the worker streams the body in
    chunks, and only an actual response proves the loop terminates and the
    bytes arrive in order.
    """

    def __init__(self, files: dict[str, bytes], redirects: dict[str, str] | None = None) -> None:
        self.requested: list[str] = []
        self.app = FastAPI()

        @self.app.get("/{path:path}")
        async def serve(path: str) -> Response:
            self.requested.append(f"/{path}")
            elsewhere = (redirects or {}).get(f"/{path}")
            if elsewhere is not None:
                return Response(status_code=302, headers={"Location": elsewhere})
            body = files.get(f"/{path}")
            if body is None:
                return JSONResponse({"detail": "gone"}, status_code=404)
            return Response(body, media_type="application/octet-stream")

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app))


class DiarizerStub:
    """A stand-in for the diariser container.

    Its contract is ours, not OpenAI's, which is exactly why it is worth a real
    server: nothing outside this repository will tell us if the field names
    drift.
    """

    def __init__(
        self,
        turns: list[dict[str, Any]] | None = None,
        status: int = 200,
        envelope: bool = True,
    ) -> None:
        one_voice = [{"start": 0.0, "end": 1.4, "speaker": "SPEAKER_00"}]
        self._turns = one_voice if turns is None else turns
        self._status = status
        self._envelope = envelope
        self.calls: list[RecordedRequest] = []
        self.app = FastAPI()

        @self.app.post("/diarize")
        async def diarize(request: Request) -> JSONResponse:
            async with request.form() as form:
                upload = form.get("file")
                recorded = RecordedRequest(
                    fields={k: v for k, v in form.items() if isinstance(v, str)},
                    authorization=request.headers.get("Authorization"),
                )
                if upload is not None and not isinstance(upload, str):
                    recorded.filename = upload.filename
                    recorded.file_size = len(await upload.read())
            self.calls.append(recorded)

            if self._status >= 400:
                return JSONResponse({"detail": "no model loaded"}, status_code=self._status)
            body = {"segments": self._turns} if self._envelope else self._turns
            return JSONResponse(body)

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://diarizer.test",
        )


@dataclass
class RecordedCompletion:
    model: str
    system: str
    user: str
    temperature: float | None
    stream: bool


class LlmStub:
    """A stand-in for an OpenAI-compatible chat endpoint.

    Answers both the plain and the streaming shape, because the worker uses the
    stream and any regression in the SSE framing is invisible otherwise.
    """

    def __init__(
        self,
        reply_for: Callable[[int], str] | None = None,
        status: int = 200,
        models: list[str] | None = None,
    ) -> None:
        self._reply_for = reply_for or (lambda index: f"summary {index}")
        self.status = status
        self.calls: list[RecordedCompletion] = []
        self.app = FastAPI()

        @self.app.get("/v1/models")
        async def list_models() -> dict[str, Any]:
            return {"data": [{"id": name, "object": "model"} for name in (models or ["stub-llm"])]}

        @self.app.post("/v1/chat/completions")
        async def completions(request: Request) -> Response:
            body = await request.json()
            index = len(self.calls)
            messages = {message["role"]: message["content"] for message in body["messages"]}
            self.calls.append(
                RecordedCompletion(
                    model=body["model"],
                    system=messages.get("system", ""),
                    user=messages.get("user", ""),
                    temperature=body.get("temperature"),
                    stream=bool(body.get("stream")),
                )
            )

            if self.status >= 400:
                return JSONResponse({"error": "nope"}, status_code=self.status)

            reply = self._reply_for(index)
            if not body.get("stream"):
                return JSONResponse(
                    {"choices": [{"message": {"role": "assistant", "content": reply}}]}
                )

            async def sse() -> AsyncIterator[str]:
                for word in reply.split(" "):
                    piece = json.dumps({"choices": [{"delta": {"content": word + " "}}]})
                    yield f"data: {piece}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse(), media_type="text/event-stream")

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://llm.test/v1",
            headers={"Authorization": "Bearer sk-test"},
        )
