from pathlib import Path

import httpx
import pytest

from httpx import AsyncClient

from app.config import Settings
from app.db import Database
from app.diarize import DiarizerClient, Turn, assign_speakers
from app.errors import ApiError
from app.secrets import load_or_create_secret
from app.stt import SttClient
from app.worker import Worker
from tests.conftest import ADMIN_CREDENTIALS, running_client
from tests.stubs import DiarizerStub, SttStub

TWO_VOICES = [
    {"start": 0.0, "end": 1.4, "speaker": "SPEAKER_00"},
    {"start": 1.4, "end": 3.0, "speaker": "SPEAKER_01"},
]


def settings_with_diarizer(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "data_dir": tmp_path,
        "stt_base_url": "http://speaches.test/v1",
        "stt_model": "Systran/faster-whisper-small",
        "diarizer_url": "http://diarizer.test",
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


async def run_worker_once(
    settings: Settings, stt: SttStub, diarizer: DiarizerStub | None = None
) -> bool:
    database = Database(settings.db_path)
    worker = Worker(
        settings,
        database,
        load_or_create_secret(settings.secret_key_path),
        stt_factory=lambda _provider: stt.http_client(),
        diarizer_factory=(lambda: diarizer.http_client()) if diarizer else None,
    )
    try:
        return await worker.run_once()
    finally:
        await database.dispose()


async def upload(client: AsyncClient, sample_audio: Path, *, diarize: bool = False) -> dict:
    await client.post("/api/setup", json=ADMIN_CREDENTIALS)
    await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    with sample_audio.open("rb") as handle:
        response = await client.post(
            "/api/jobs",
            files={"file": ("meeting.wav", handle, "audio/wav")},
            data={"diarize": str(diarize).lower()},
        )
    assert response.status_code == 201, response.text
    return response.json()


DIARIZED_JSON = {
    "task": "transcribe",
    "duration": 3.0,
    "text": "Hello there. General Kenobi.",
    "segments": [
        {
            "type": "transcript.text.segment",
            "id": "seg_0",
            "start": 0.0,
            "end": 1.4,
            "text": "Hello there.",
            "speaker": "A",
        },
        {
            "type": "transcript.text.segment",
            "id": "seg_1",
            "start": 1.4,
            "end": 3.0,
            "text": "General Kenobi.",
            "speaker": "B",
        },
    ],
}


async def test_a_model_that_diarises_is_asked_for_the_speakers_with_the_words(
    sample_audio: Path,
) -> None:
    """One request, one model, and the speakers arrive attached to the text.

    Nothing here is merged afterwards: the segments come back already
    attributed, which is the whole difference from asking two services and
    lining their answers up by overlap.
    """
    stub = SttStub(DIARIZED_JSON)

    async with stub.http_client() as http:
        result = await SttClient(http).transcribe(
            sample_audio, model="gpt-4o-transcribe-diarize"
        )

    assert stub.calls[0].fields["response_format"] == "diarized_json"
    # Required above thirty seconds, and a meeting is always above thirty
    # seconds. Sending it always is one fewer thing to be wrong about.
    assert stub.calls[0].fields["chunking_strategy"] == "auto"
    assert [segment.speaker for segment in result.segments] == ["A", "B"]
    assert result.text == "Hello there. General Kenobi."


async def test_a_model_that_cannot_answer_in_verbose_json_is_never_asked_to(
    sample_audio: Path,
) -> None:
    """The format follows the model, not what the job wanted.

    Reported as "STT-сервер ответил 400" on a recording nobody asked to
    diarise: the provider was pointed at the diarising model, the job carried
    no request for speakers, and so the old wording asked it for `verbose_json`
    -- which is the one format it refuses. Whether the speakers are used is the
    worker's business; whether they can be asked for at all is the model's.
    """
    stub = SttStub(DIARIZED_JSON)

    async with stub.http_client() as http:
        await SttClient(http).transcribe(sample_audio, model="gpt-4o-transcribe-diarize")

    assert stub.calls[0].fields["response_format"] == "diarized_json"


async def test_a_dated_snapshot_of_a_diarising_model_is_the_same_model(
    sample_audio: Path,
) -> None:
    """Providers publish the same model under suffixed names -- OpenAI's own
    error messages call this one `gpt-4o-transcribe-diarize-api-ev3` -- and a
    name matched exactly would send the wrong format to every one of them."""
    stub = SttStub(DIARIZED_JSON)

    async with stub.http_client() as http:
        await SttClient(http).transcribe(sample_audio, model="gpt-4o-transcribe-diarize-api-ev3")

    assert stub.calls[0].fields["response_format"] == "diarized_json"


async def test_an_ordinary_transcription_asks_for_nothing_of_the_sort(
    sample_audio: Path,
) -> None:
    stub = SttStub()

    async with stub.http_client() as http:
        result = await SttClient(http).transcribe(sample_audio, model="whisper-1")

    assert stub.calls[0].fields["response_format"] == "verbose_json"
    assert "chunking_strategy" not in stub.calls[0].fields
    assert [segment.speaker for segment in result.segments] == [None, None]


def test_a_segment_takes_the_speaker_it_overlaps_most() -> None:
    turns = [Turn(0.0, 5.0, "SPEAKER_00"), Turn(5.0, 10.0, "SPEAKER_01")]

    assigned = assign_speakers([(0.0, 4.0), (4.0, 9.0), (9.5, 10.0)], turns)

    assert assigned == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_01"]


def test_a_segment_nobody_was_speaking_over_gets_no_speaker() -> None:
    turns = [Turn(10.0, 20.0, "SPEAKER_00")]

    assert assign_speakers([(0.0, 5.0)], turns) == [None]


def test_without_turns_nothing_is_attributed() -> None:
    assert assign_speakers([(0.0, 5.0), (5.0, 9.0)], []) == [None, None]


def test_overlapping_turns_do_not_confuse_the_count() -> None:
    """Diarisers emit crosstalk as two turns covering the same moment."""
    turns = [Turn(0.0, 6.0, "SPEAKER_00"), Turn(4.0, 10.0, "SPEAKER_01")]

    assert assign_speakers([(3.0, 5.5), (5.0, 8.0)], turns) == ["SPEAKER_00", "SPEAKER_01"]


async def test_the_audio_reaches_the_diariser_and_turns_come_back(sample_audio: Path) -> None:
    stub = DiarizerStub(
        [
            {"start": 0.0, "end": 1.4, "speaker": "SPEAKER_00"},
            {"start": 1.4, "end": 3.0, "speaker": "SPEAKER_01"},
        ]
    )

    async with stub.http_client() as http:
        turns = await DiarizerClient(http).diarize(sample_audio)

    assert turns == [Turn(0.0, 1.4, "SPEAKER_00"), Turn(1.4, 3.0, "SPEAKER_01")]
    assert stub.calls[0].file_size == sample_audio.stat().st_size


async def test_a_bare_list_is_read_as_well_as_an_envelope(sample_audio: Path) -> None:
    """Half the wrappers people put in front of pyannote answer with a list."""
    stub = DiarizerStub([{"start": 0.0, "end": 2.0, "speaker": "A"}], envelope=False)

    async with stub.http_client() as http:
        assert await DiarizerClient(http).diarize(sample_audio) == [Turn(0.0, 2.0, "A")]


async def test_a_broken_diariser_reports_a_translatable_code(sample_audio: Path) -> None:
    stub = DiarizerStub(status=500)

    with pytest.raises(ApiError) as raised:
        async with stub.http_client() as http:
            await DiarizerClient(http).diarize(sample_audio)

    assert raised.value.code == "diarizer_failed"
    assert raised.value.params["status"] == 500


async def test_a_diariser_that_is_not_running_is_told_apart_from_one_that_refused(
    sample_audio: Path,
) -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:1") as http:
        with pytest.raises(ApiError) as raised:
            await DiarizerClient(http).diarize(sample_audio)

    assert raised.value.code == "diarizer_unreachable"


async def test_the_ui_is_told_whether_diarisation_is_on_offer(tmp_path: Path) -> None:
    """A checkbox for a container nobody started is worse than no checkbox."""
    async with running_client(settings_with_diarizer(tmp_path)) as client:
        assert (await client.get("/api/setup/status")).json()["has_diarizer"] is True

    async with running_client(settings_with_diarizer(tmp_path, diarizer_url=None)) as client:
        assert (await client.get("/api/setup/status")).json()["has_diarizer"] is False


async def test_a_diarised_job_attributes_every_segment(tmp_path: Path, sample_audio: Path) -> None:
    settings = settings_with_diarizer(tmp_path)
    diarizer = DiarizerStub(TWO_VOICES)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)

        await run_worker_once(settings, SttStub(), diarizer)

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert [segment["speaker"] for segment in transcript["segments"]] == [
            "SPEAKER_00",
            "SPEAKER_01",
        ]
        # The labels are listed once, so the UI has something to rename.
        assert [speaker["label"] for speaker in transcript["speakers"]] == [
            "SPEAKER_00",
            "SPEAKER_01",
        ]
        assert transcript["speakers"][0]["display_name"] is None
        assert len(diarizer.calls) == 1


def settings_with_diarizing_stt(tmp_path: Path, **overrides: object) -> Settings:
    """A transcription model that answers with speakers, and no diariser at all.

    This is the whole point of the arrangement: the container with the model
    weights in it does not have to exist.
    """
    return settings_with_diarizer(
        tmp_path,
        diarizer_url=None,
        stt_model="gpt-4o-transcribe-diarize",
        **overrides,
    )


async def test_a_transcribing_model_that_diarises_replaces_the_diariser(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizing_stt(tmp_path)
    diarizer = DiarizerStub(TWO_VOICES)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)

        await run_worker_once(settings, SttStub(DIARIZED_JSON), diarizer)

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert [segment["speaker"] for segment in transcript["segments"]] == ["A", "B"]
        # Renaming works the same way it does for the diariser's own labels.
        assert [speaker["label"] for speaker in transcript["speakers"]] == ["A", "B"]
        assert diarizer.calls == []
        assert (await client.get(f"/api/jobs/{job['id']}")).json()["error_code"] is None


async def test_the_offer_of_speakers_follows_the_model_as_well_as_the_container(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Two ways to answer the same question, and the UI asks one thing.

    A checkbox that appeared only when a container was running would be missing
    on an installation whose transcription model does the job by itself.
    """
    settings = settings_with_diarizing_stt(tmp_path)

    async with running_client(settings) as client:
        assert (await client.get("/api/setup/status")).json()["has_diarizer"] is True
        # And the submission gate agrees with the status it just reported.
        job = await upload(client, sample_audio, diarize=True)
        assert job["diarize"] is True


async def test_asking_a_diarising_model_afterwards_transcribes_the_recording_again(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The only way to ask this model who spoke is to ask it for the words too.

    With a diariser of our own the transcript is read back and left alone,
    because the two halves are separate requests to separate services. Here
    they are one request, so wanting the speakers after the fact means paying
    for the transcription a second time -- which is worth doing quietly rather
    than refusing, since the alternative is a recording that can never have
    speakers at all.
    """
    settings = settings_with_diarizing_stt(tmp_path)
    stt = SttStub(DIARIZED_JSON)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, SttStub())

        assert (await client.post(f"/api/jobs/{job['id']}/diarize")).status_code == 200
        await run_worker_once(settings, stt)

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert [segment["speaker"] for segment in transcript["segments"]] == ["A", "B"]
        assert (await client.get(f"/api/jobs/{job['id']}")).json()["error_code"] is None
        assert stt.calls[0].fields["response_format"] == "diarized_json"


async def test_a_recording_too_long_to_send_whole_says_so(
    tmp_path: Path, sample_audio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cutting it is not an option here, so the cap on a request is a cap on
    the recording -- and it has to be said in those words.

    The real number is 1400 seconds, which the endpoint reports as a sentence
    at 1500 and as "the file might be corrupted" at 5000. Neither is something
    to hand to somebody who uploaded a meeting.
    """
    monkeypatch.setattr("app.worker.DIARIZED_MAX_SECONDS", 1.0)
    settings = settings_with_diarizing_stt(tmp_path)
    stt = SttStub(DIARIZED_JSON)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)

        await run_worker_once(settings, stt)

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "failed"
        assert finished["error_code"] == "diarized_too_long"
        assert stt.calls == []


async def test_a_job_nobody_asked_to_diarise_never_reaches_the_diariser(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizer(tmp_path)
    diarizer = DiarizerStub(TWO_VOICES)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)

        await run_worker_once(settings, SttStub(), diarizer)

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert [segment["speaker"] for segment in transcript["segments"]] == [None, None]
        assert transcript["speakers"] == []
        assert diarizer.calls == []


async def test_asking_for_diarisation_without_a_diariser_is_refused_immediately(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Told at submission, not twenty minutes later when the job fails."""
    settings = settings_with_diarizer(tmp_path, diarizer_url=None)

    async with running_client(settings) as client:
        await client.post("/api/setup", json=ADMIN_CREDENTIALS)
        await client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
        with sample_audio.open("rb") as handle:
            response = await client.post(
                "/api/jobs",
                files={"file": ("meeting.wav", handle, "audio/wav")},
                data={"diarize": "true"},
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "no_diarizer"


async def test_a_diariser_that_fails_does_not_cost_the_transcript(
    tmp_path: Path, sample_audio: Path
) -> None:
    """The text is the product; who said it is a bonus that cannot outrank it."""
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)

        await run_worker_once(settings, SttStub(), DiarizerStub(status=500))

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        assert finished["status"] == "done"
        assert finished["error_code"] == "diarizer_failed"

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert transcript["text"] == "Hello there. General Kenobi."
        assert transcript["speakers"] == []


async def test_a_finished_recording_can_be_diarised_afterwards(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Deciding after reading it that you want to know who said what used to
    mean handing the whole recording in again."""
    settings = settings_with_diarizer(tmp_path)
    stt = SttStub()

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, stt, DiarizerStub(TWO_VOICES))

        asked = await client.post(f"/api/jobs/{job['id']}/diarize")
        assert asked.status_code == 200, asked.text
        assert asked.json()["status"] == "queued"
        assert asked.json()["diarize"] is True

        await run_worker_once(settings, stt, DiarizerStub(TWO_VOICES))

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()

    assert finished["status"] == "done"
    assert [segment["speaker"] for segment in transcript["segments"]] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    assert [speaker["label"] for speaker in transcript["speakers"]] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    # The expensive half was already done, and the words are unchanged.
    assert len(stt.calls) == 1
    assert transcript["text"] == "Hello there. General Kenobi."


async def test_diarisation_cannot_be_asked_for_once_the_audio_is_gone(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Keeping only the words is a choice the archive offers; it costs the
    ability to ask the diariser anything, because there is nothing to send."""
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))
        await client.delete(f"/api/jobs/{job['id']}/audio")

        refused = await client.post(f"/api/jobs/{job['id']}/diarize")

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "audio_gone"


async def test_a_second_diarisation_that_fails_leaves_the_first_one_standing(
    tmp_path: Path, sample_audio: Path
) -> None:
    """Asking again is meant to be safe: a diariser that is down must not turn
    a transcript that knows its speakers into one that does not."""
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))

        await client.post(f"/api/jobs/{job['id']}/diarize")
        await run_worker_once(settings, SttStub(), DiarizerStub(status=500))

        finished = (await client.get(f"/api/jobs/{job['id']}")).json()
        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()

    assert finished["error_code"] == "diarizer_failed"
    assert [segment["speaker"] for segment in transcript["segments"]] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]


async def test_a_renamed_speaker_redraws_the_transcript_and_its_exports(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        speaker = transcript["speakers"][0]

        renamed = await client.patch(
            f"/api/jobs/{job['id']}/speakers/{speaker['id']}",
            json={"display_name": "Марина"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["display_name"] == "Марина"

        # The label on the segment does not move: it is the identity, and the
        # name is what is drawn over it.
        again = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        assert again["segments"][0]["speaker"] == "SPEAKER_00"
        assert again["speakers"][0]["display_name"] == "Марина"

        exported = await client.get(f"/api/jobs/{job['id']}/export?format=txt&speakers=true")
        assert exported.text.startswith("Марина: Hello there.")
        assert "SPEAKER_01: General Kenobi." in exported.text


async def test_an_empty_name_gives_the_speaker_its_label_back(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        speaker_id = transcript["speakers"][0]["id"]

        await client.patch(
            f"/api/jobs/{job['id']}/speakers/{speaker_id}", json={"display_name": "Марина"}
        )
        cleared = await client.patch(
            f"/api/jobs/{job['id']}/speakers/{speaker_id}", json={"display_name": "  "}
        )

        assert cleared.json()["display_name"] is None


async def test_a_reader_of_a_share_sees_the_names_but_no_way_to_change_them(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        job = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))

        transcript = (await client.get(f"/api/jobs/{job['id']}/transcript")).json()
        await client.patch(
            f"/api/jobs/{job['id']}/speakers/{transcript['speakers'][0]['id']}",
            json={"display_name": "Марина"},
        )
        token = (await client.post(f"/api/jobs/{job['id']}/share", json={})).json()["token"]

    async with running_client(settings) as reader:
        shared = (await reader.get(f"/api/public/shares/{token}")).json()
        exported = await reader.get(f"/api/public/shares/{token}/export?format=md")

    assert shared["speakers"] == [
        {"label": "SPEAKER_00", "display_name": "Марина"},
        {"label": "SPEAKER_01", "display_name": None},
    ]
    assert "Марина: Hello there." in exported.text


async def test_a_speaker_from_another_recording_cannot_be_renamed(
    tmp_path: Path, sample_audio: Path
) -> None:
    settings = settings_with_diarizer(tmp_path)

    async with running_client(settings) as client:
        first = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))
        second = await upload(client, sample_audio, diarize=True)
        await run_worker_once(settings, SttStub(), DiarizerStub(TWO_VOICES))

        transcript = (await client.get(f"/api/jobs/{first['id']}/transcript")).json()
        stranger = transcript["speakers"][0]["id"]

        response = await client.patch(
            f"/api/jobs/{second['id']}/speakers/{stranger}", json={"display_name": "nope"}
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "speaker_not_found"
