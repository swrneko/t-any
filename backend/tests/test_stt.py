from pathlib import Path

from app.stt import SttClient
from tests.stubs import WHISPER_VERBOSE_JSON, SttStub


async def test_transcription_returns_segments_with_timestamps(sample_audio: Path) -> None:
    stub = SttStub()

    async with stub.http_client() as http:
        result = await SttClient(http).transcribe(sample_audio, model="whisper-1")

    assert result.language == "en"
    assert result.text == "Hello there. General Kenobi."
    assert [(s.start, s.end) for s in result.segments] == [(0.0, 1.4), (1.4, 3.0)]
    assert result.segments[1].text == "General Kenobi."


async def test_a_spelled_out_language_comes_back_as_a_code(sample_audio: Path) -> None:
    """OpenAI answers `english` where faster-whisper answers `en`, and only the
    second form is a valid input -- so the first would weaken the forcing on
    every chunk after the one that detected it."""
    stub = SttStub(payload={**WHISPER_VERBOSE_JSON, "language": "English"})

    async with stub.http_client() as http:
        result = await SttClient(http).transcribe(sample_audio, model="whisper-1")

    assert result.language == "en"
    assert result.raw["language"] == "English", "the provider's own answer is kept"


async def test_the_audio_and_options_actually_reach_the_endpoint(sample_audio: Path) -> None:
    stub = SttStub()

    async with stub.http_client() as http:
        await SttClient(http).transcribe(
            sample_audio, model="whisper-1", language="en", prompt="Kenobi"
        )

    call = stub.calls[0]
    assert call.file_size == sample_audio.stat().st_size
    assert call.fields["model"] == "whisper-1"
    assert call.fields["language"] == "en"
    assert call.fields["prompt"] == "Kenobi"
    # Without verbose_json there are no timestamps, and no timestamps means no
    # subtitles and no synchronised player -- the whole point of storing audio.
    assert call.fields["response_format"] == "verbose_json"
    assert call.authorization == "Bearer sk-test"
