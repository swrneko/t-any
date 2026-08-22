import asyncio
import json
import secrets
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, select

from app.config import Settings
from app.deps import CurrentUserDep, SessionDep, SettingsDep
from app.errors import ApiError
from app.exports import FORMATS, MEDIA_TYPES, Options, lines_from, render
from app.models import Job, Segment, Share, Speaker, Transcript, User, utcnow
from app.retention import AUDIO_NAME, forget_job, remove_audio, remove_media
from app.schemas import (
    JobOut,
    JobsDeleteIn,
    JobsDeleteOut,
    JobUrlIn,
    SegmentIn,
    SegmentOut,
    ShareIn,
    ShareOut,
    SpeakerIn,
    SpeakerOut,
    TranscriptOut,
)
from app.sources import ensure_allowed_host, parse_source_url
from app.storage import save_upload

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _audio_bytes(settings: Settings, job_id: uuid.UUID) -> int | None:
    """One stat per job, like the file it describes: cheap enough for the SSE
    tick, and always the truth rather than a column that can drift from disk."""
    try:
        return (settings.media_dir / str(job_id) / AUDIO_NAME).stat().st_size
    except OSError:
        return None


def _present(job: Job, settings: Settings) -> JobOut:
    return JobOut(
        audio_bytes=_audio_bytes(settings, job.id),
        id=job.id,
        title=job.title,
        source_type=job.source_type,
        source_ref=job.source_ref,
        author=job.author,
        published_on=job.published_on,
        has_thumbnail=job.has_thumbnail,
        diarize=job.diarize,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        language=job.language,
        duration_sec=job.duration_sec,
        error_code=job.error_code,
        error_params=json.loads(job.error_params) if job.error_params else {},
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


async def _owned_job(session: SessionDep, user: User, job_id: uuid.UUID) -> Job:
    job = await session.scalar(
        select(Job).where(Job.id == job_id, Job.owner_id == user.id)
    )
    if job is None:
        # Not 403: whether a job exists at all is the owner's business.
        raise ApiError(404, "job_not_found", "No such job.")
    return job


def _check_diarizer(settings: Settings, diarize: bool) -> None:
    """Refuse now rather than half an hour into the job.

    Diarisation lives in a container that is off by default, and a request for
    it that nothing can serve is worth saying immediately -- the alternative is
    a recording that transcribes for twenty minutes and then reports a feature
    the operator never turned on.
    """
    if diarize and not settings.diarizer_url:
        raise ApiError(
            503,
            "no_diarizer",
            "No diariser is configured on this instance.",
        )


@router.post("", status_code=201)
async def create_job(
    file: UploadFile,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    diarize: bool = Form(False),
) -> JobOut:
    title = Path(file.filename or "upload").name
    _check_diarizer(settings, diarize)

    job = Job(
        owner_id=user.id,
        source_type="upload",
        source_ref=title,
        title=title,
        diarize=diarize,
    )
    session.add(job)
    await session.flush()

    source = settings.tmp_dir / str(job.id) / f"source{Path(title).suffix}"
    _, job.sha256 = await save_upload(file, source, settings.max_upload_size)

    await session.commit()
    return _present(job, settings)


@router.post("/url", status_code=201)
async def create_job_from_url(
    body: JobUrlIn,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> JobOut:
    """Queue a link. Nothing is fetched here.

    A two-hour recording cannot download inside a request, so the job is created
    empty and the worker resolves the source the same way it would an upload.
    """
    source_type, title = parse_source_url(body.url)
    _check_diarizer(settings, body.diarize)
    # Answered now so a refused link says so immediately; the worker asks again
    # before it opens the socket, which is the check that actually protects.
    await ensure_allowed_host(body.url, allow_private=settings.allow_private_network_urls)

    job = Job(
        owner_id=user.id,
        source_type=source_type,
        source_ref=body.url.strip(),
        title=title,
        diarize=body.diarize,
    )
    session.add(job)
    await session.commit()
    return _present(job, settings)


@router.get("")
async def list_jobs(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> list[JobOut]:
    jobs = await session.scalars(
        select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc())
    )
    return [_present(job, settings) for job in jobs]


TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


@router.get("/events")
async def job_list_events(
    request: Request,
    user: CurrentUserDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """One stream for the whole list.

    Ten queued files must not mean ten connections: browsers cap concurrent
    requests per origin, and the surplus would simply never open.
    """
    factory = request.app.state.db.session_factory
    owner_id = user.id

    async def stream() -> AsyncIterator[str]:
        previous: str | None = None
        while True:
            async with factory() as poll_session:
                jobs = (
                    await poll_session.scalars(
                        select(Job)
                        .where(Job.owner_id == owner_id)
                        .order_by(Job.created_at.desc())
                    )
                ).all()

            payload = json.dumps(
                [json.loads(_present(job, settings).model_dump_json()) for job in jobs]
            )
            if payload != previous:
                previous = payload
                yield _sse(payload)

            if all(job.status in TERMINAL_STATUSES for job in jobs):
                return

            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}")
async def read_job(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> JobOut:
    return _present(await _owned_job(session, user, job_id), settings)


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Server-sent events, not a websocket.

    The traffic only ever flows one way, browsers reconnect a dropped stream by
    themselves, any reverse proxy passes it through without a protocol upgrade,
    and it can be debugged with curl.
    """
    await _owned_job(session, user, job_id)
    factory = request.app.state.db.session_factory

    async def stream() -> AsyncIterator[str]:
        previous: str | None = None
        while True:
            async with factory() as poll_session:
                job = await poll_session.get(Job, job_id)
            if job is None:
                return

            payload = _present(job, settings).model_dump_json()
            if payload != previous:
                previous = payload
                yield _sse(payload)

            if job.status in TERMINAL_STATUSES:
                return

            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/audio")
async def job_audio(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    job = await _owned_job(session, user, job_id)

    audio = settings.media_dir / str(job.id) / AUDIO_NAME
    if not audio.is_file():
        raise ApiError(404, "audio_unavailable", "The audio for this job is gone.")

    return FileResponse(audio, media_type="audio/ogg", filename=f"{job.title}.ogg")


def export_response(
    job: Job,
    transcript: Transcript,
    rows: list[Segment],
    *,
    format: str,
    timestamps: bool,
    speakers: bool,
    download: bool,
    names: Mapping[str, str] | None = None,
) -> Response:
    """Render the transcript on the way out.

    Nothing is precomputed and nothing is cached: the raw response is the only
    stored form, and a new format is a function, not a migration. Shared with
    the public share endpoints, which export exactly the same way.
    """
    if format not in FORMATS:
        raise ApiError(
            400,
            "unsupported_format",
            f"{format} is not a format this exports to.",
            format=format,
            supported=list(FORMATS),
        )

    if format == "json":
        # The provider's answer, byte for byte. Re-serialising it here would
        # quietly make this a rendering of our reading of it.
        body = transcript.raw_json
    else:
        body = render(
            format,
            lines_from(rows, names),
            title=job.title,
            language=transcript.language,
            duration_sec=job.duration_sec,
            source=job.source_ref if job.source_type != "upload" else None,
            options=Options(timestamps=timestamps, speakers=speakers),
        )

    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{ascii_name(job.title)}.{format}"'
    return Response(body, media_type=MEDIA_TYPES[format], headers=headers)


@router.get("/{job_id}/export")
async def export_transcript(
    job_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    format: str = "txt",
    timestamps: bool = False,
    speakers: bool = True,
    download: bool = False,
) -> Response:
    job = await _owned_job(session, user, job_id)
    transcript, rows = await _transcript_of(session, job)
    return export_response(
        job,
        transcript,
        rows,
        format=format,
        timestamps=timestamps,
        speakers=speakers,
        download=download,
        names=await speaker_names(session, job),
    )


def ascii_name(title: str) -> str:
    """Content-Disposition is a header, and a header is latin-1."""
    cleaned = "".join(char if char.isalnum() or char in " ._-" else "_" for char in title)
    return cleaned.encode("ascii", "ignore").decode().strip() or "transcript"


@router.get("/{job_id}/thumbnail")
async def job_thumbnail(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> FileResponse:
    job = await _owned_job(session, user, job_id)

    thumbnail = settings.media_dir / str(job.id) / "thumbnail.jpg"
    if not thumbnail.is_file():
        raise ApiError(404, "thumbnail_unavailable", "This job has no cover image.")

    return FileResponse(thumbnail, media_type="image/jpeg")


@router.post("/{job_id}/share", status_code=201)
async def share_job(
    job_id: uuid.UUID, body: ShareIn, user: CurrentUserDep, session: SessionDep
) -> ShareOut:
    """Publish a read-only link, or hand back the one already published."""
    job = await _owned_job(session, user, job_id)

    share = await session.scalar(select(Share).where(Share.job_id == job.id))
    if share is None:
        share = Share(token=secrets.token_urlsafe(32), job_id=job.id)
        session.add(share)

    if body.expires_in_days is not None:
        share.expires_at = utcnow() + timedelta(days=body.expires_in_days)

    await session.commit()
    return ShareOut.model_validate(share)


@router.get("/{job_id}/share")
async def read_share(job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> ShareOut:
    job = await _owned_job(session, user, job_id)

    share = await session.scalar(select(Share).where(Share.job_id == job.id))
    if share is None:
        raise ApiError(404, "share_not_found", "This transcript is not shared.")
    return ShareOut.model_validate(share)


@router.delete("/{job_id}/share", status_code=204)
async def revoke_share(job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> None:
    job = await _owned_job(session, user, job_id)
    await session.execute(delete(Share).where(Share.job_id == job.id))
    await session.commit()


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> JobOut:
    job = await _owned_job(session, user, job_id)

    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = utcnow()
    elif job.status == "running":
        # The worker owns the process; it polls for this and stops the work.
        job.status = "cancelling"
    else:
        raise ApiError(
            409,
            "job_not_cancellable",
            f"A job that is {job.status} cannot be cancelled.",
            status=job.status,
        )

    await session.commit()
    return _present(job, settings)


def _require_finished(job: Job) -> None:
    """A recording still being worked on is not deleted, it is cancelled first.

    The worker owns the directory while it runs, and removing it underneath
    would leave ffmpeg writing into nothing and the job failing for a reason
    nobody could explain.
    """
    if job.status not in TERMINAL_STATUSES:
        raise ApiError(
            409,
            "job_not_finished",
            "Cancel it before deleting it.",
            status=job.status,
        )


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> None:
    job = await _owned_job(session, user, job_id)
    _require_finished(job)

    await forget_job(session, job)
    # Rows first, files second: a directory nobody points at is litter, while a
    # row pointing at files that are gone is a transcript that cannot play.
    await session.commit()
    remove_media(settings, job_id)


@router.delete("/{job_id}/audio", status_code=204)
async def delete_job_audio(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> None:
    """Free the expensive half and keep the valuable one."""
    job = await _owned_job(session, user, job_id)
    _require_finished(job)
    remove_audio(settings, job.id)


@router.post("/delete")
async def delete_jobs(
    body: JobsDeleteIn, user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> JobsDeleteOut:
    """The same two operations, over a selection.

    Deleting a hundred recordings one request at a time is not a thing anybody
    should be asked to wait through.
    """
    jobs = (
        await session.scalars(
            select(Job).where(Job.id.in_(body.ids), Job.owner_id == user.id)
        )
    ).all()

    doomed = [job for job in jobs if job.status in TERMINAL_STATUSES]
    skipped = len(body.ids) - len(doomed)

    if not body.audio_only:
        for job in doomed:
            await forget_job(session, job)
    await session.commit()

    for job in doomed:
        if body.audio_only:
            remove_audio(settings, job.id)
        else:
            remove_media(settings, job.id)

    return JobsDeleteOut(deleted=len(doomed), skipped=skipped)


async def speakers_of(session: SessionDep, job: Job) -> list[Speaker]:
    """Ordered by label, so a transcript lists its voices the same way twice."""
    rows = await session.scalars(
        select(Speaker).where(Speaker.job_id == job.id).order_by(Speaker.label)
    )
    return list(rows)


async def speaker_names(session: SessionDep, job: Job) -> dict[str, str]:
    return {
        speaker.label: speaker.display_name
        for speaker in await speakers_of(session, job)
        if speaker.display_name
    }


@router.patch("/{job_id}/speakers/{speaker_id}")
async def rename_speaker(
    job_id: uuid.UUID,
    speaker_id: uuid.UUID,
    body: SpeakerIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> SpeakerOut:
    """One row, and the transcript, its exports and its share link redraw."""
    job = await _owned_job(session, user, job_id)

    speaker = await session.scalar(
        select(Speaker).where(Speaker.id == speaker_id, Speaker.job_id == job.id)
    )
    if speaker is None:
        raise ApiError(404, "speaker_not_found", "No such speaker in this recording.")

    speaker.display_name = body.display_name.strip() or None
    await session.commit()
    return SpeakerOut.model_validate(speaker)


async def _transcript_of(session: SessionDep, job: Job) -> tuple[Transcript, list[Segment]]:
    transcript = await session.scalar(select(Transcript).where(Transcript.job_id == job.id))
    if transcript is None:
        raise ApiError(404, "transcript_not_ready", "This job has no transcript yet.")

    rows = await session.scalars(
        select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
    )
    return transcript, list(rows)


def present_segment(row: Segment) -> SegmentOut:
    return SegmentOut(
        idx=row.idx,
        start=row.start,
        end=row.end,
        text=row.edited_text if row.edited_text is not None else row.text,
        edited=row.edited_text is not None,
        speaker=row.speaker,
    )


@router.patch("/{job_id}/segments/{idx}")
async def correct_segment(
    job_id: uuid.UUID,
    idx: int,
    body: SegmentIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> SegmentOut:
    """Fix a word the model misheard.

    The correction lands beside the original rather than on top of it: the raw
    response stays the one durable thing, so a correction can be undone and a
    re-run with a better model does not silently discard it. The search index
    follows by trigger -- an archive that still finds what nobody said is worse
    than one that finds nothing.
    """
    job = await _owned_job(session, user, job_id)
    transcript, _rows = await _transcript_of(session, job)

    segment = await session.scalar(
        select(Segment).where(Segment.transcript_id == transcript.id, Segment.idx == idx)
    )
    if segment is None:
        raise ApiError(404, "segment_not_found", "No such segment in this transcript.", idx=idx)

    segment.edited_text = body.text.strip() or None
    await session.commit()
    return present_segment(segment)


@router.get("/{job_id}/transcript")
async def read_transcript(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> TranscriptOut:
    job = await _owned_job(session, user, job_id)
    transcript, rows = await _transcript_of(session, job)

    segments = [present_segment(row) for row in rows]

    return TranscriptOut(
        job_id=job.id,
        language=transcript.language,
        text=" ".join(segment.text for segment in segments).strip(),
        segments=segments,
        speakers=[SpeakerOut.model_validate(row) for row in await speakers_of(session, job)],
    )
