"""Removing a recording, by hand or by policy.

The API and the worker do the same thing here, so they do it through the same
functions: a recording deleted from the archive page and one swept away by a
policy have to leave the database in the same state, or one of the two paths
grows a bug the other does not have.

Both policies are off by default. A self-hosted archive that quietly eats its
own contents is the worst surprise this service could spring, so the sweeper
does nothing at all until somebody sets a number.
"""

import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import InstanceSetting, Job, Segment, Transcript, utcnow
from app.schemas import Retention, StorageOut

AUDIO_NAME = "audio.ogg"
POLICY_KEY = "retention"


async def read_policy(session: AsyncSession) -> Retention:
    row = await session.get(InstanceSetting, POLICY_KEY)
    return Retention.model_validate_json(row.value) if row is not None else Retention()


async def write_policy(session: AsyncSession, policy: Retention) -> Retention:
    row = await session.get(InstanceSetting, POLICY_KEY)
    if row is None:
        session.add(InstanceSetting(key=POLICY_KEY, value=policy.model_dump_json()))
    else:
        row.value = policy.model_dump_json()
    await session.commit()
    return policy


def audio_path(settings: Settings, job_id: uuid.UUID) -> Path:
    return settings.media_dir / str(job_id) / AUDIO_NAME


def remove_media(settings: Settings, job_id: uuid.UUID) -> None:
    shutil.rmtree(settings.media_dir / str(job_id), ignore_errors=True)


def remove_audio(settings: Settings, job_id: uuid.UUID) -> bool:
    audio = audio_path(settings, job_id)
    if not audio.is_file():
        return False
    audio.unlink(missing_ok=True)
    return True


async def forget_job(session: AsyncSession, job: Job) -> None:
    """Drop the rows. Everything else falls with them by cascade."""
    # Segments go explicitly: the search index is kept by triggers on that
    # table, and SQLite does not fire them for rows removed by a foreign key
    # cascade. A recording that still answered searches would look deleted
    # without being deleted.
    await session.execute(
        delete(Segment).where(
            Segment.transcript_id.in_(select(Transcript.id).where(Transcript.job_id == job.id))
        )
    )
    await session.delete(job)


async def sweep(session: AsyncSession, settings: Settings) -> tuple[int, int]:
    """Apply both policies. Returns how much audio went, and how many recordings.

    A job with no `finished_at` is never touched: it is queued or running, and
    reading a missing timestamp as "infinitely old" would delete the recording
    somebody is waiting for.
    """
    policy = await read_policy(session)
    freed = removed = 0

    if policy.job_days:
        doomed = list(await session.scalars(_older_than(policy.job_days)))
        for job in doomed:
            await forget_job(session, job)
        await session.commit()
        for job in doomed:
            remove_media(settings, job.id)
        removed = len(doomed)

    if policy.audio_days:
        for job in await session.scalars(_older_than(policy.audio_days)):
            if remove_audio(settings, job.id):
                freed += 1

    return freed, removed


def _older_than(days: int):  # type: ignore[no-untyped-def]
    cutoff = utcnow() - timedelta(days=days)
    return select(Job).where(Job.finished_at.is_not(None), Job.finished_at <= cutoff)


def usage(settings: Settings) -> StorageOut:
    """What the recordings cost, split the way the policies are split."""
    audio = other = recordings = 0
    if not settings.media_dir.is_dir():
        return StorageOut(audio_bytes=0, other_bytes=0, recordings=0)

    for directory in settings.media_dir.iterdir():
        if not directory.is_dir():
            continue
        recordings += 1
        for entry in directory.iterdir():
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if entry.name == AUDIO_NAME:
                audio += size
            else:
                other += size

    return StorageOut(audio_bytes=audio, other_bytes=other, recordings=recordings)
