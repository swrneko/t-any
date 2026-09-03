"""The diariser service: audio in, speech turns out.

Deliberately the whole contract and nothing else. There is no OpenAI-compatible
endpoint for diarisation, so this defines one -- and keeping it this small is
what lets somebody replace it with their own wrapper around whatever model they
prefer, without touching the application.

    POST /diarize   multipart file  ->  {"segments": [{start, end, speaker}]}

This is the only place in the repository where a machine learning library is
installed, which is why it is a separate image behind a compose profile that is
off by default.
"""

import os
import tempfile
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException, UploadFile
from pyannote.audio import Pipeline

MODEL = os.environ.get("DIARIZER_MODEL", "pyannote/speaker-diarization-3.1")

app = FastAPI(title="tany diarizer")
_pipeline: Pipeline | None = None


def pipeline() -> Pipeline:
    """Loaded once, on the first request rather than at import.

    Startup would otherwise mean downloading several gigabytes before the
    container can answer a healthcheck, and an operator who mistyped their
    token would watch it fail with no way to ask why.
    """
    global _pipeline
    if _pipeline is None:
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise HTTPException(503, "HF_TOKEN is not set, so no model can be downloaded.")
        loaded = Pipeline.from_pretrained(MODEL, token=token)
        if loaded is None:
            raise HTTPException(
                503,
                f"{MODEL} could not be loaded. Its terms usually have to be "
                "accepted once on huggingface.co with the same account.",
            )
        _pipeline = loaded.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    return _pipeline


@app.get("/health")
def health() -> dict[str, str]:
    # Deliberately does not touch the model: this answers "is the container
    # up", and loading half a gigabyte to say so would defeat the purpose.
    return {"status": "ok"}


@app.post("/diarize")
async def diarize(file: UploadFile) -> dict[str, list[dict[str, object]]]:
    running = pipeline()

    with tempfile.TemporaryDirectory() as workspace:
        audio = Path(workspace) / (file.filename or "audio")
        audio.write_bytes(await file.read())
        output = running(str(audio))

    # Recent versions answer with a dataclass; older ones with the annotation
    # itself. The exclusive variant is the one meant for transcription: it has
    # no overlapping turns, so every moment belongs to one speaker.
    annotation = getattr(output, "exclusive_speaker_diarization", None)
    if annotation is None:
        annotation = getattr(output, "speaker_diarization", output)

    return {
        "segments": [
            {"start": round(turn.start, 3), "end": round(turn.end, 3), "speaker": speaker}
            for turn, _track, speaker in annotation.itertracks(yield_label=True)
        ]
    }
