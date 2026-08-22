from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from tests.conftest import running_client
from tests.stubs import SttStub
from tests.test_worker import run_worker_once, upload

CHUNK_MAX = 1.2


def chunking_settings(tmp_path: Path) -> Settings:
    """Tiny chunks so a three-second fixture exercises the same code path a
    two-hour recording would."""
    return Settings(
        data_dir=tmp_path,
        stt_base_url="http://speaches.test/v1",
        stt_model="stub-whisper",
        chunk_target_seconds=1.0,
        chunk_max_seconds=CHUNK_MAX,
        _env_file=None,
    )


def one_segment_per_chunk(index: int) -> dict[str, Any]:
    """Every chunk answers with chunk-local timestamps, exactly as a real
    provider does. Turning those into recording-wide ones is the worker's job."""
    return {
        "language": "en",
        "text": f"chunk {index}",
        "segments": [{"start": 0.0, "end": 0.5, "text": f"chunk {index}"}],
    }


async def test_a_long_recording_is_split_and_timestamps_are_shifted(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = chunking_settings(tmp_path)
    stub = SttStub(payload_for=one_segment_per_chunk)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        await run_worker_once(settings, stub)

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done", finished

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()

    assert len(stub.calls) == 3, "three seconds at a 1.2 s maximum is three chunks"
    assert [segment["text"] for segment in transcript["segments"]] == [
        "chunk 0",
        "chunk 1",
        "chunk 2",
    ]
    # Each provider answer started at 0.0; only the offset makes them a timeline.
    starts = [segment["start"] for segment in transcript["segments"]]
    assert starts[0] == pytest.approx(0.0)
    assert starts[1] == pytest.approx(CHUNK_MAX, abs=0.01)
    assert starts[2] == pytest.approx(CHUNK_MAX * 2, abs=0.01)
    assert starts == sorted(starts), "timestamps must never go backwards"


async def test_the_language_from_the_first_chunk_is_forced_on_the_rest(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Left to themselves, chunks of one recording get recognised as different
    languages -- and the result reads plausibly enough that nobody notices."""
    settings = chunking_settings(tmp_path)
    stub = SttStub(payload_for=one_segment_per_chunk)

    async with running_client(settings) as client:
        await upload(client, sample_audio)
        await run_worker_once(settings, stub)

    assert "language" not in stub.calls[0].fields, "the first chunk detects it"
    assert [call.fields.get("language") for call in stub.calls[1:]] == ["en", "en"]


async def test_a_spelled_out_language_is_forced_as_a_code(
    tmp_path: Path, sample_audio: Path
) -> None:
    """A cloud endpoint answers `English`, which cannot be sent back as an
    input: forcing it would be forcing nothing, quietly."""
    settings = chunking_settings(tmp_path)

    def spelled_out(index: int) -> dict[str, Any]:
        return {**one_segment_per_chunk(index), "language": "English"}

    stub = SttStub(payload_for=spelled_out)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, stub)
        finished = (await client.get(f"/api/jobs/{job['id']}")).json()

    assert [call.fields.get("language") for call in stub.calls[1:]] == ["en", "en"]
    assert finished["language"] == "en"


async def test_chunking_can_be_switched_off(tmp_path: Path, sample_audio: Path) -> None:
    settings = chunking_settings(tmp_path).model_copy(update={"stt_chunking": "never"})
    stub = SttStub(payload_for=one_segment_per_chunk)

    async with running_client(settings) as client:
        await upload(client, sample_audio)
        await run_worker_once(settings, stub)

    assert len(stub.calls) == 1


async def test_progress_reaches_one_when_every_chunk_is_done(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = chunking_settings(tmp_path)
    stub = SttStub(payload_for=one_segment_per_chunk)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, stub)

        assert (await client.get(f"/api/jobs/{job['id']}")).json()["progress"] == 1.0
