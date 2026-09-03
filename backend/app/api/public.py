"""Everything reachable without an account.

One key opens these doors: the token in the link. There is no session here, no
owner, and nothing that answers a question about the instance itself -- a leaked
token must expose one transcript and no more than that.
"""

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.jobs import export_response, present_segment, speaker_names, speakers_of
from app.deps import SessionDep, SettingsDep
from app.errors import ApiError
from app.models import Job, Segment, Share, Transcript, utcnow
from app.schemas import PublicSpeakerOut, PublicTranscriptOut

router = APIRouter(prefix="/public", tags=["public"])


async def _shared(session: SessionDep, token: str) -> tuple[Job, Transcript, list[Segment]]:
    share = await session.get(Share, token)
    if share is None:
        raise ApiError(404, "share_not_found", "This link does not exist.")
    if share.expires_at is not None and share.expires_at <= utcnow():
        # Said out loud rather than hidden behind "not found": the holder of an
        # expired link needs to know to ask for a new one.
        raise ApiError(404, "share_expired", "This link has expired.")

    job = await session.get(Job, share.job_id)
    transcript = (
        await session.scalar(select(Transcript).where(Transcript.job_id == share.job_id))
        if job is not None
        else None
    )
    if job is None or transcript is None:
        raise ApiError(404, "share_not_found", "This link does not exist.")

    rows = await session.scalars(
        select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
    )
    return job, transcript, list(rows)


@router.get("/shares/{token}")
async def read_shared_transcript(
    token: str, session: SessionDep, settings: SettingsDep
) -> PublicTranscriptOut:
    job, transcript, rows = await _shared(session, token)

    segments = [present_segment(row) for row in rows]

    return PublicTranscriptOut(
        job_id=job.id,
        title=job.title,
        author=job.author,
        published_on=job.published_on,
        language=transcript.language,
        duration_sec=job.duration_sec,
        has_audio=(settings.media_dir / str(job.id) / "audio.ogg").is_file(),
        text=" ".join(segment.text for segment in segments).strip(),
        segments=segments,
        speakers=[
            PublicSpeakerOut(label=row.label, display_name=row.display_name)
            for row in await speakers_of(session, job)
        ],
    )


@router.get("/shares/{token}/export")
async def export_shared_transcript(
    token: str,
    session: SessionDep,
    format: str = "txt",
    timestamps: bool = False,
    speakers: bool = True,
    download: bool = False,
) -> Response:
    job, transcript, rows = await _shared(session, token)
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


@router.get("/shares/{token}/audio")
async def shared_audio(token: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """The recording travels with the link: a transcript whose player cannot
    play anything is half a document."""
    job, _transcript, _rows = await _shared(session, token)

    audio = settings.media_dir / str(job.id) / "audio.ogg"
    if not audio.is_file():
        raise ApiError(404, "audio_unavailable", "The audio for this transcript is gone.")
    return FileResponse(audio, media_type="audio/ogg", filename=f"{job.title}.ogg")


@router.get("/shares/{token}/thumbnail")
async def shared_thumbnail(token: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    job, _transcript, _rows = await _shared(session, token)

    thumbnail = settings.media_dir / str(job.id) / "thumbnail.jpg"
    if not thumbnail.is_file():
        raise ApiError(404, "thumbnail_unavailable", "This transcript has no cover image.")
    return FileResponse(thumbnail, media_type="image/jpeg")
