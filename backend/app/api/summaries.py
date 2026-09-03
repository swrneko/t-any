import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select

from app.deps import CurrentUserDep, SessionDep, SettingsDep
from app.errors import ApiError
from app.models import Job, Preset, Summary, Transcript, User, utcnow
from app.schemas import SummaryIn, SummaryOut

router = APIRouter(tags=["summaries"])

TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


def _present(summary: Summary) -> SummaryOut:
    return SummaryOut(
        id=summary.id,
        job_id=summary.job_id,
        preset_id=summary.preset_id,
        preset_name=summary.preset_name,
        status=summary.status,
        progress=summary.progress,
        content=summary.content,
        partials_json=summary.partials_json,
        model_used=summary.model_used,
        error_code=summary.error_code,
        error_params=json.loads(summary.error_params) if summary.error_params else {},
        created_at=summary.created_at,
        finished_at=summary.finished_at,
    )


async def _owned_job(session: SessionDep, user: User, job_id: uuid.UUID) -> Job:
    job = await session.scalar(select(Job).where(Job.id == job_id, Job.owner_id == user.id))
    if job is None:
        raise ApiError(404, "job_not_found", "No such job.")
    return job


async def _owned_summary(
    session: SessionDep, user: User, summary_id: uuid.UUID
) -> Summary:
    summary = await session.scalar(
        select(Summary).join(Job, Job.id == Summary.job_id).where(
            Summary.id == summary_id, Job.owner_id == user.id
        )
    )
    if summary is None:
        raise ApiError(404, "summary_not_found", "No such summary.")
    return summary


@router.get("/jobs/{job_id}/summaries")
async def list_summaries(
    job_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> list[SummaryOut]:
    job = await _owned_job(session, user, job_id)
    summaries = await session.scalars(
        select(Summary).where(Summary.job_id == job.id).order_by(Summary.created_at)
    )
    return [_present(summary) for summary in summaries]


@router.post("/jobs/{job_id}/summaries", status_code=201)
async def create_summary(
    job_id: uuid.UUID, payload: SummaryIn, user: CurrentUserDep, session: SessionDep
) -> SummaryOut:
    """Queue a summary. It is its own unit of work, not part of the job.

    That is what makes "try it again with another preset" cheap: the
    transcription is already done and is never touched again.
    """
    job = await _owned_job(session, user, job_id)

    transcript = await session.scalar(select(Transcript).where(Transcript.job_id == job.id))
    if transcript is None:
        raise ApiError(409, "transcript_not_ready", "This job has no transcript yet.")

    preset = await session.scalar(
        select(Preset).where(
            Preset.id == payload.preset_id,
            or_(Preset.owner_id == user.id, Preset.owner_id.is_(None)),
        )
    )
    if preset is None:
        raise ApiError(404, "preset_not_found", "No such preset.")

    summary = Summary(job_id=job.id, preset_id=preset.id, preset_name=preset.name)
    session.add(summary)
    await session.commit()
    return _present(summary)


@router.get("/summaries/{summary_id}")
async def read_summary(
    summary_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> SummaryOut:
    return _present(await _owned_summary(session, user, summary_id))


@router.get("/summaries/{summary_id}/events")
async def summary_events(
    summary_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Watch a summary being written.

    The worker owns the model connection, so the text reaches the browser by way
    of the row it accumulates in -- one hop later than a direct pipe, and worth
    it to keep inference out of the request loop.
    """
    await _owned_summary(session, user, summary_id)
    factory = request.app.state.db.session_factory

    async def stream() -> AsyncIterator[str]:
        previous: str | None = None
        while True:
            async with factory() as poll_session:
                summary = await poll_session.get(Summary, summary_id)
            if summary is None:
                return

            payload = _present(summary).model_dump_json()
            if payload != previous:
                previous = payload
                yield f"data: {payload}\n\n"

            if summary.status in TERMINAL_STATUSES:
                return

            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/summaries/{summary_id}", status_code=204)
async def delete_summary(
    summary_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> None:
    summary = await _owned_summary(session, user, summary_id)
    await session.delete(summary)
    await session.commit()


@router.post("/summaries/{summary_id}/cancel")
async def cancel_summary(
    summary_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> SummaryOut:
    """The stop button the transcription path has had since milestone 2."""
    summary = await _owned_summary(session, user, summary_id)

    if summary.status == "queued":
        summary.status = "cancelled"
        summary.finished_at = utcnow()
    elif summary.status == "running":
        # The worker owns the request in flight; it polls for this and drops it.
        summary.status = "cancelling"
    else:
        raise ApiError(
            409,
            "summary_not_cancellable",
            f"A summary that is {summary.status} cannot be cancelled.",
            status=summary.status,
        )

    await session.commit()
    return _present(summary)


@router.post("/summaries/{summary_id}/retry")
async def retry_summary(
    summary_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> SummaryOut:
    """Run the same preset again, in place.

    Only for a summary that failed or was stopped: a finished one is a result
    worth keeping, and asking for another is asking for another row.
    """
    summary = await _owned_summary(session, user, summary_id)

    if summary.status not in ("failed", "cancelled"):
        raise ApiError(
            409,
            "summary_not_retryable",
            f"A summary that is {summary.status} is not retried.",
            status=summary.status,
        )

    summary.status = "queued"
    summary.progress = 0.0
    summary.content = ""
    summary.error_code = None
    summary.error_params = None
    summary.error_message = None
    summary.worker_id = None
    summary.heartbeat_at = None
    summary.finished_at = None
    # partials_json is deliberately kept: reduce is where a local model chokes,
    # and the parts that already came back are the expensive half.

    await session.commit()
    return _present(summary)
