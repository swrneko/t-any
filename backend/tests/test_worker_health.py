import asyncio
import os
import time
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.secrets import load_or_create_secret
from app.worker import Worker, worker_is_alive
from tests.conftest import running_client
from tests.stubs import SttStub
from tests.test_worker import settings_with_stt, upload


def worker_for(settings: Settings, database: Database, stt: SttStub | None = None) -> Worker:
    # No API has started in these tests, so nobody has made the directories yet.
    settings.ensure_dirs()
    return Worker(
        settings,
        database,
        load_or_create_secret(settings.secret_key_path),
        stt_factory=None if stt is None else (lambda _provider: stt.http_client()),
    )


async def test_a_worker_that_has_not_started_is_not_alive(tmp_path: Path) -> None:
    """Compose starts the container and asks a second later; nothing has run
    yet, and saying otherwise would make the check meaningless."""
    settings = settings_with_stt(tmp_path)

    assert worker_is_alive(settings) is False


async def test_a_turn_of_the_claim_loop_says_the_worker_is_alive(tmp_path: Path) -> None:
    """An idle worker has no job to write a heartbeat onto, which is exactly the
    state a liveness check has to be able to tell from a dead one."""
    settings = settings_with_stt(tmp_path)
    database = Database(settings.db_path)

    async with running_client(settings):
        assert await worker_for(settings, database).run_once() is False, "nothing to claim"

    await database.dispose()
    assert worker_is_alive(settings) is True


async def test_a_worker_that_stopped_turning_reads_as_dead(tmp_path: Path) -> None:
    """The point of the check: a process still holding the container open while
    its loop has stopped is worse than one that exited, because nothing
    restarts it."""
    settings = settings_with_stt(tmp_path)
    database = Database(settings.db_path)

    async with running_client(settings):
        await worker_for(settings, database).run_once()

    await database.dispose()
    stopped = time.time() - settings.worker_stale_seconds - 1
    os.utime(settings.worker_liveness_path, (stopped, stopped))

    assert worker_is_alive(settings) is False


async def test_a_worker_busy_with_one_long_job_is_still_alive(
    tmp_path: Path, sample_audio: Path
) -> None:
    """A two-hour recording is one turn of the loop. Liveness that only ticks
    between jobs would call the busiest worker on the instance dead."""
    settings = settings_with_stt(tmp_path).model_copy(update={"cancel_poll_seconds": 0.05})
    hold = asyncio.Event()
    stub = SttStub(hold=hold)
    database = Database(settings.db_path)
    worker = worker_for(settings, database, stub)

    async with running_client(settings) as client:
        await upload(client, sample_audio)

        working = asyncio.create_task(worker.run_once())
        await asyncio.wait_for(stub.received.wait(), timeout=5)

        # Older than the loop ever turns, so only the running job can refresh it.
        stale = time.time() - settings.worker_stale_seconds - 1
        os.utime(settings.worker_liveness_path, (stale, stale))
        await asyncio.sleep(settings.cancel_poll_seconds * 3)
        busy = worker_is_alive(settings)

        hold.set()
        await asyncio.wait_for(working, timeout=10)

    await database.dispose()
    assert busy is True
