"""Everything that costs money, answered locally.

One process standing in for the three remote services this application talks
to: an OpenAI-compatible transcription endpoint, an OpenAI-compatible chat
endpoint, and the diariser's own protocol. Point the providers at it and the
whole pipeline runs end to end -- upload, chunking, progress, summaries,
speakers, export -- without a single request leaving the machine.

    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d stub

It is not a mock of our own code: the application speaks real HTTP to it, so
multipart encoding, SSE framing and the response shapes are all genuinely
exercised. What it does not do is transcribe -- the words are invented. It asks
ffprobe how long the audio is and lays plausible sentences across that many
seconds, so timestamps line up with the player and a two-hour recording really
does produce a two-hour transcript.

Runs on the application's own image, which already carries ffmpeg, fastapi and
uvicorn; there is nothing here to build.
"""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import StreamingResponse

app = FastAPI(title="tany stub")

# How long a call pretends to take. Instant answers hide the whole point of the
# queue: the stages, the progress bar and the cancel button are only visible
# while something is in flight.
LATENCY_SECONDS = 1.5

# Roughly how long one invented line lasts. Whisper's own segments run four to
# eight seconds; anything shorter reads as subtitles rather than as a
# transcript.
SECONDS_PER_LINE = 6.0

LINES = [
    "Так, все слышат? Тогда начнём, у нас полчаса.",
    "По прошлой неделе: выкатили две задачи из трёх, третья висит на ревью.",
    "Основная проблема была с миграцией, она у нас падала на проде.",
    "Мы её починили, но пришлось откатить релиз и собрать заново.",
    "Дальше по планам на эту неделю.",
    "Первое — дописать импорт, там осталось поле с датой.",
    "Второе — посмотреть, почему очередь встаёт под нагрузкой.",
    "Я думаю, дело в том, что мы держим соединение слишком долго.",
    "Хорошо, тогда я возьму это на себя и посмотрю логи.",
    "Ещё был вопрос по документации, её никто не обновлял с марта.",
    "Давайте так: кто трогает модуль, тот и правит его описание.",
    "Согласен, иначе это всё равно никогда не случится.",
    "По срокам — думаю, к четвергу будет готово.",
    "Если не успеем, перенесём на следующий спринт, ничего страшного.",
    "Окей, тогда на этом закончим, спасибо всем.",
]


def duration_of(audio: Path) -> float:
    """How long the file is, according to ffprobe.

    A stub that guessed would produce a transcript whose timestamps run past
    the end of the recording, and the player would stop following it halfway
    down the page.
    """
    try:
        answer = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(audio),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return max(float(answer.stdout.strip()), 1.0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 30.0


def segments_for(seconds: float, offset: int = 0) -> list[dict[str, Any]]:
    """Lines laid end to end across the whole recording."""
    total = max(1, round(seconds / SECONDS_PER_LINE))
    step = seconds / total
    return [
        {
            "id": index,
            "start": round(index * step, 3),
            "end": round(min((index + 1) * step, seconds), 3),
            "text": " " + LINES[(index + offset) % len(LINES)],
        }
        for index in range(total)
    ]


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """What the connection test in Settings -> Providers asks for."""
    return {
        "object": "list",
        "data": [
            {"id": "stub-stt", "object": "model", "owned_by": "stub"},
            {"id": "stub-llm", "object": "model", "owned_by": "stub"},
        ],
    }


@app.post("/v1/audio/transcriptions")
async def transcriptions(request: Request) -> dict[str, Any]:
    async with request.form() as form:
        upload = form.get("file")
        payload = b"" if upload is None or isinstance(upload, str) else await upload.read()
        name = "audio.ogg" if upload is None or isinstance(upload, str) else (upload.filename or "")

    with tempfile.TemporaryDirectory() as workspace:
        audio = Path(workspace) / (Path(name).name or "audio")
        audio.write_bytes(payload)
        seconds = duration_of(audio)

    await asyncio.sleep(LATENCY_SECONDS)

    # Chunks of one recording arrive as separate requests, so the lines are
    # offset by where the chunk starts: two chunks in a row saying "Так, все
    # слышат?" is the one thing that would give the stub away immediately.
    segments = segments_for(seconds, offset=int(len(payload) / 4096) % len(LINES))
    return {
        "task": "transcribe",
        "language": "russian",
        "duration": round(seconds, 3),
        "text": "".join(segment["text"] for segment in segments).strip(),
        "segments": segments,
    }


def summary_for(user: str) -> str:
    """A summary that at least looks at what it was given.

    Not a real one -- but a canned paragraph identical for every recording
    makes the summaries screen impossible to test, because you cannot tell a
    stale one from a fresh one.
    """
    words = user.split()
    opening = " ".join(words[:14]) if words else "запись"
    return (
        "## О чём это было\n\n"
        f"Разговор начинается со слов «{opening}…» и дальше держится одной темы.\n\n"
        "## Главное\n\n"
        "- Две задачи из трёх закрыты, третья ждёт ревью.\n"
        "- Миграция падала на проде; релиз откатывали и собирали заново.\n"
        "- Очередь встаёт под нагрузкой — предполагают долгие соединения.\n\n"
        "## Договорились\n\n"
        "- Дописать импорт (поле с датой) — к четвергу.\n"
        "- Посмотреть логи очереди.\n"
        "- Кто трогает модуль, тот правит его описание.\n\n"
        f"_Сгенерировано заглушкой: {len(words)} слов на входе._"
    )


@app.post("/v1/chat/completions")
async def chat(request: Request) -> Any:
    body = await request.json()
    messages = body.get("messages") or []
    user = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    text = summary_for(user)

    if not body.get("stream"):
        await asyncio.sleep(LATENCY_SECONDS)
        return {
            "id": "stub",
            "object": "chat.completion",
            "model": body.get("model", "stub-llm"),
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": len(text) // 4},
        }

    # Word by word, with a pause between: the summary panel renders as it
    # arrives, and a stub that answered in one frame would never show that.
    async def stream():
        for piece in text.split(" "):
            chunk = {
                "id": "stub",
                "object": "chat.completion.chunk",
                "model": body.get("model", "stub-llm"),
                "choices": [{"index": 0, "delta": {"content": piece + " "}}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/diarize")
async def diarize(file: UploadFile) -> dict[str, list[dict[str, Any]]]:
    """The diariser's contract, without pyannote or the three gigabytes.

    Two speakers taking turns every other line, which is enough to exercise the
    merge, the speaker bar, renaming and every export that carries names.
    """
    with tempfile.TemporaryDirectory() as workspace:
        audio = Path(workspace) / (file.filename or "audio")
        audio.write_bytes(await file.read())
        seconds = duration_of(audio)

    await asyncio.sleep(LATENCY_SECONDS)

    return {
        "segments": [
            {
                "start": segment["start"],
                "end": segment["end"],
                "speaker": f"SPEAKER_{index % 2:02d}",
            }
            for index, segment in enumerate(segments_for(seconds))
        ]
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
