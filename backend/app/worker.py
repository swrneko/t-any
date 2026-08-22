import asyncio
import json
import logging
import os
import socket
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import Chunk, plan_chunks
from app.config import Settings
from app.crypto import decrypt_secret
from app.db import Database
from app.diarize import DiarizerClient, assign_speakers, diarizer_http_client
from app.errors import ApiError
from app.llm import llm_http_client
from app.media import detect_silences, extract_chunk, normalize_to_opus, probe
from app.models import Job, Provider, Segment, Speaker, Summary, Transcript, utcnow
from app.retention import sweep as sweep_expired
from app.webhooks import read_webhook
from app.sources import download_media, ensure_allowed_host, fetch_with_ytdlp
from app.summary_runner import LlmFactory, SummaryRunner
from app.stt import SttClient
from app.stt import Segment as SttSegment
from app.stt import Transcription, stt_http_client

log = logging.getLogger("worker")

SttFactory = Callable[[Provider], httpx.AsyncClient]
DownloadFactory = Callable[[], httpx.AsyncClient]

IDLE_POLL_SECONDS = 2.0

# Failures worth repeating: the connection, not the request.
RETRYABLE_CODES = frozenset({"stt_unreachable", "stt_server_error"})


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def worker_is_alive(settings: Settings) -> bool:
    """Whether the worker in this container has shown a sign of life lately.

    It serves no port, so there is nothing to curl: the question is whether its
    loop is still turning, and the answer is a file it touches as it goes. A
    process that is still holding the container open with a loop that has
    stopped is worse than one that exited -- nothing restarts the first.
    """
    try:
        beat = settings.worker_liveness_path.stat().st_mtime
    except OSError:
        return False
    return time.time() - beat <= settings.worker_stale_seconds


class Worker:
    """Runs in its own container, sharing only the volume with the API.

    Not in-process: an API restart would kill live jobs, ffmpeg would fight the
    request loop for CPU, and --reload in development would murder every run.
    Not Celery either -- this is dozens of jobs a day, and a broker would be a
    tax on complexity paid for nothing.
    """

    def __init__(
        self,
        settings: Settings,
        database: Database,
        secret: bytes,
        *,
        stt_factory: SttFactory | None = None,
        llm_factory: LlmFactory | None = None,
        download_factory: DownloadFactory | None = None,
        webhook_factory: DownloadFactory | None = None,
        diarizer_factory: DownloadFactory | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.secret = secret
        self.identity = worker_identity()
        self._stt_factory = stt_factory or self._default_stt_client
        self._llm_factory = llm_factory or self._default_llm_client
        self._download_factory = download_factory or self._default_download_client
        self._webhook_factory = webhook_factory or (lambda: httpx.AsyncClient())
        self._diarizer_factory = diarizer_factory or self._default_diarizer_client

    def _api_key(self, provider: Provider) -> str | None:
        if not provider.api_key_encrypted:
            return None
        return decrypt_secret(provider.api_key_encrypted, self.secret)

    def _default_stt_client(self, provider: Provider) -> httpx.AsyncClient:
        return stt_http_client(provider.base_url, self._api_key(provider))

    def _default_llm_client(self, provider: Provider) -> httpx.AsyncClient:
        return llm_http_client(provider.base_url, self._api_key(provider))

    def _default_diarizer_client(self) -> httpx.AsyncClient:
        return diarizer_http_client(self.settings.diarizer_url or "")

    def _default_download_client(self) -> httpx.AsyncClient:
        # No read timeout: the body of a two-hour recording legitimately takes
        # longer to arrive than any sane per-read deadline.
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(self.settings.download_connect_seconds, read=None),
        )

    async def recover_stale_jobs(self) -> int:
        """Requeue whatever the previous worker was holding when it died.

        A crashed process leaves a job marked running forever: the claim query
        only looks at queued rows, so nothing will ever pick it up again and it
        sits there looking busy until a human reads the database.
        """
        cutoff = utcnow() - timedelta(seconds=self.settings.heartbeat_stale_seconds)
        stale = or_(Job.heartbeat_at.is_(None), Job.heartbeat_at <= cutoff)

        async with self.database.session_factory() as session:
            requeued = await session.execute(
                update(Job)
                .where(Job.status == "running", stale)
                .values(
                    status="queued",
                    worker_id=None,
                    started_at=None,
                    heartbeat_at=None,
                    stage=None,
                    progress=0.0,
                )
            )
            # A job whose cancellation was already asked for should not come
            # back to life just because the worker handling it went away.
            await session.execute(
                update(Job)
                .where(Job.status == "cancelling", stale)
                .values(status="cancelled", finished_at=utcnow())
            )
            await session.commit()

        count = requeued.rowcount or 0
        if count:
            log.info("requeued %d job(s) left behind by a previous worker", count)
        return count

    async def run_forever(self) -> None:
        await self.recover_stale_jobs()
        due = 0.0
        while True:
            # The claim loop is already awake every few seconds, so retention
            # rides along on it rather than bringing a scheduler with it.
            if time.monotonic() >= due:
                due = time.monotonic() + self.settings.retention_sweep_seconds
                freed, removed = await self.sweep()
                if freed or removed:
                    log.info("retention freed %d recording(s) and removed %d", freed, removed)

            if not await self.run_once():
                await asyncio.sleep(IDLE_POLL_SECONDS)

    async def sweep(self) -> tuple[int, int]:
        """Apply the retention policies. Does nothing at all until one is set."""
        async with self.database.session_factory() as session:
            return await sweep_expired(session, self.settings)

    async def run_once(self) -> bool:
        self._pulse()
        # Transcription first: a summary is worthless until its transcript
        # exists, and a queue of summaries must not starve new recordings.
        return await self._run_transcription() or await self._run_summary()

    def _pulse(self) -> None:
        """Leave a mark saying the loop came round.

        Every turn, and again from the supervisor while a job is being worked:
        a two-hour recording is a single turn of the loop, and liveness that
        only ticked between jobs would call the busiest worker dead.
        """
        path = self.settings.worker_liveness_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    async def _run_summary(self) -> bool:
        summary_id = await self._claim_summary()
        if summary_id is None:
            return False

        async with self.database.session_factory() as session:
            summary = await session.get(Summary, summary_id)
            assert summary is not None
            working = asyncio.create_task(
                SummaryRunner(self.settings, session, self._llm_factory).run(summary)
            )
            watcher = asyncio.create_task(self._watch_summary(summary_id, working))
            try:
                await working
                summary.status = "done"
            except asyncio.CancelledError:
                # Stopped from the UI. The session was interrupted mid-request,
                # so the row is finished with a plain UPDATE rather than through
                # an instance the rollback has expired.
                watcher.cancel()
                await session.rollback()
                await session.execute(
                    update(Summary)
                    .where(Summary.id == summary_id)
                    .values(status="cancelled", finished_at=utcnow(), worker_id=None)
                )
                await session.commit()
                return True
            except ApiError as failure:
                log.warning("summary %s failed: %s", summary.id, failure.message)
                summary.status = "failed"
                summary.error_code = failure.code
                summary.error_message = failure.message
                summary.error_params = json.dumps(failure.params)
            finally:
                watcher.cancel()
            summary.finished_at = utcnow()
            await session.commit()

        return True

    async def _watch_summary(self, summary_id: object, working: asyncio.Task[None]) -> None:
        """Keep the heartbeat fresh, and drop the request when a stop arrives."""
        while True:
            await asyncio.sleep(self.settings.cancel_poll_seconds)
            self._pulse()
            async with self.database.session_factory() as session:
                status = await session.scalar(
                    select(Summary.status).where(Summary.id == summary_id)
                )
                if status == "cancelling":
                    working.cancel()
                    return
                await session.execute(
                    update(Summary).where(Summary.id == summary_id).values(heartbeat_at=utcnow())
                )
                await session.commit()

    async def _claim_summary(self) -> object | None:
        now = utcnow()
        oldest = (
            select(Summary.id)
            .where(Summary.status == "queued")
            .order_by(Summary.created_at)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(Summary)
            .where(Summary.id == oldest)
            .values(status="running", worker_id=self.identity, heartbeat_at=now)
            .returning(Summary.id)
        )

        async with self.database.session_factory() as session:
            claimed = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return claimed

    async def _run_transcription(self) -> bool:
        job_id = await self._claim()
        if job_id is None:
            return False

        cancelled_by_user = False

        def request_stop() -> None:
            nonlocal cancelled_by_user
            cancelled_by_user = True

        working = asyncio.create_task(self._execute(job_id))
        supervisor = asyncio.create_task(self._supervise(job_id, working, request_stop))
        try:
            await working
        except asyncio.CancelledError:
            if not cancelled_by_user:
                # The process itself is going away. Leave the job and its
                # workspace exactly as they are so a successor can resume;
                # marking it cancelled would tell the user they stopped
                # something they never touched.
                supervisor.cancel()
                raise
            await self._finish(job_id, status="cancelled")

        supervisor.cancel()
        self._clear_workspace(job_id)
        return True

    async def _execute(self, job_id: object) -> None:
        async with self.database.session_factory() as session:
            job = await session.get(Job, job_id)
            assert job is not None
            try:
                await self._process(session, job)
                job.status = "done"
                job.progress = 1.0
            except ApiError as failure:
                log.warning("job %s failed: %s", job.id, failure.message)
                job.status = "failed"
                job.error_code = failure.code
                job.error_message = failure.message
                job.error_params = json.dumps(failure.params)

            # Nothing is being done to it any more, either way.
            job.stage = None
            job.finished_at = utcnow()
            await session.commit()
            await self._notify(session, job)

    async def _notify(self, session: AsyncSession, job: Job) -> None:
        """Tell whoever asked to be told, once.

        No retries and no queue: this is a courtesy call, not a delivery
        guarantee, and the API is still there to be polled. A receiver that is
        down must never cost us a transcript that already exists.
        """
        if job.status not in ("done", "failed"):
            return
        # Read per job rather than at start-up: the address is edited in the UI
        # while this process is running, and a stale one would be silent.
        hook = await read_webhook(session, self.secret)
        if not hook.url:
            return

        payload: dict[str, object] = {
            "event": f"job.{job.status}",
            "job": {
                "id": str(job.id),
                "title": job.title,
                "source_type": job.source_type,
                "source_ref": job.source_ref,
                "status": job.status,
                "language": job.language,
                "duration_sec": job.duration_sec,
                "error_code": job.error_code,
                # English, and deliberately so: a webhook has no translation
                # bundle, which is what `message` exists for.
                "error_message": job.error_message,
                "created_at": job.created_at.isoformat(),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            },
        }
        if job.status == "done":
            payload["text"] = await self._transcript_text(session, job)

        headers = {}
        if hook.secret:
            headers["Authorization"] = f"Bearer {hook.secret}"

        try:
            async with self._webhook_factory() as http:
                await http.post(
                    hook.url,
                    json=payload,
                    headers=headers,
                    timeout=self.settings.webhook_timeout_seconds,
                )
        except Exception as failure:  # noqa: BLE001 -- a hook must not fail a job
            log.warning("webhook for job %s was not delivered: %s", job.id, failure)

    async def _transcript_text(self, session: AsyncSession, job: Job) -> str:
        transcript = await session.scalar(select(Transcript).where(Transcript.job_id == job.id))
        if transcript is None:
            return ""
        rows = await session.scalars(
            select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
        )
        return " ".join(
            (row.edited_text if row.edited_text is not None else row.text).strip() for row in rows
        ).strip()

    async def _supervise(
        self,
        job_id: object,
        working: asyncio.Task[None],
        request_stop: Callable[[], None],
    ) -> None:
        """Keep the heartbeat fresh and stop the work when a cancel arrives.

        The API cannot reach into this process, so the cancel request travels
        through the database and lands here as a task cancellation -- which
        kills ffmpeg and drops the HTTP request to the provider.
        """
        while True:
            await asyncio.sleep(self.settings.cancel_poll_seconds)
            self._pulse()
            async with self.database.session_factory() as session:
                status = await session.scalar(select(Job.status).where(Job.id == job_id))
                if status == "cancelling":
                    request_stop()
                    working.cancel()
                    return
                await session.execute(
                    update(Job).where(Job.id == job_id).values(heartbeat_at=utcnow())
                )
                await session.commit()

    async def _finish(self, job_id: object, *, status: str) -> None:
        async with self.database.session_factory() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=status, stage=None, finished_at=utcnow())
            )
            await session.commit()

    async def _claim(self) -> object | None:
        """Take the oldest queued job in a single statement.

        Two workers running this concurrently cannot both win: the UPDATE holds
        the write lock, and the loser's subquery finds nothing.
        """
        now = utcnow()
        oldest = (
            select(Job.id)
            .where(Job.status == "queued")
            .order_by(Job.created_at)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(Job)
            .where(Job.id == oldest)
            .values(
                status="running",
                worker_id=self.identity,
                started_at=now,
                heartbeat_at=now,
            )
            .returning(Job.id)
        )

        async with self.database.session_factory() as session:
            claimed = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return claimed

    async def _process(self, session: AsyncSession, job: Job) -> None:
        workspace = self.settings.tmp_dir / str(job.id)
        audio = self.settings.media_dir / str(job.id) / "audio.ogg"

        # Queued with a stage already on it: somebody asked for that part alone.
        # Recovery clears the stage when it requeues, so a crash cannot leave a
        # job claiming the work is nearly done when it has not started.
        if job.stage == "diarizing":
            await self._rediarize(session, job, audio)
            return

        # Normalised audio is the checkpoint: a job resumed after a crash skips
        # straight past ffmpeg, and the original upload is already gone by then.
        if audio.is_file():
            info = await probe(audio)
        else:
            source = await self._acquire_source(session, job)
            # ffmpeg reports its own progress on stderr and we do not read it;
            # what the stage buys here is the difference between "stuck" and
            # "converting a two-hour video", which is most of the question.
            await self._enter(session, job, "converting")
            info = await normalize_to_opus(source, audio)
            # The original goes the moment we no longer need it. Keeping video
            # around fills a home server's disk inside a week.
            source.unlink(missing_ok=True)

        job.duration_sec = info.duration_sec

        # A crash between writing the transcript and finishing the job would
        # otherwise collide with the unique constraint on the second attempt.
        await session.execute(delete(Transcript).where(Transcript.job_id == job.id))

        provider, model = await self._resolve_stt(session, job)
        job.stt_provider_id = provider.id
        job.stt_model = model
        await session.commit()

        await self._enter(session, job, "transcribing")
        chunks = await self._plan_chunks(audio, info.duration_sec)
        language = job.language
        collected: list[SttSegment] = []
        raw_parts: list[dict[str, object]] = []

        async with self._stt_factory(provider) as http:
            client = SttClient(http)
            for chunk in chunks:
                piece = audio
                if len(chunks) > 1:
                    piece = workspace / f"chunk-{chunk.index:04d}.ogg"
                    await extract_chunk(audio, piece, start=chunk.start, end=chunk.end)

                result = await self._transcribe_with_retries(
                    client, piece, model=model, language=language, prompt=job.prompt
                )
                # Detected once, then forced. Otherwise chunks of one recording
                # come back in different languages and the result still reads
                # plausibly enough that nobody notices.
                language = language or result.language

                collected.extend(
                    SttSegment(
                        start=segment.start + chunk.start,
                        end=segment.end + chunk.start,
                        text=segment.text,
                    )
                    for segment in result.segments
                )
                raw_parts.append(result.raw)

                if piece is not audio:
                    piece.unlink(missing_ok=True)

                job.progress = (chunk.index + 1) / len(chunks)
                job.heartbeat_at = utcnow()
                await session.commit()

        job.language = language

        raw = raw_parts[0] if len(raw_parts) == 1 else {"chunks": raw_parts}
        transcript = Transcript(job_id=job.id, raw_json=json.dumps(raw), language=language)
        session.add(transcript)
        await session.flush()

        speakers: list[str | None] = [None] * len(collected)
        if job.diarize:
            # The diariser reports nothing until it is done, so this stage has a
            # name and no number -- which is still more than a bar that stops.
            await self._enter(session, job, "diarizing")
            attributed = await self._diarize(session, job, audio, collected)
            if attributed is not None:
                speakers = attributed

        session.add_all(
            Segment(
                transcript_id=transcript.id,
                idx=index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker=speakers[index],
            )
            for index, segment in enumerate(collected)
        )

    async def _rediarize(self, session: AsyncSession, job: Job, audio: Path) -> None:
        """Attribute words that are already written down.

        Asked for from the archive, on a recording whose transcript exists: the
        text is the expensive half and the one thing this must not touch, so it
        is read back rather than fetched again.
        """
        if not audio.is_file():
            raise ApiError(
                410,
                "audio_gone",
                "The recording is no longer on disk, and the diariser needs it.",
            )

        transcript_id = await session.scalar(
            select(Transcript.id).where(Transcript.job_id == job.id)
        )
        if transcript_id is None:
            raise ApiError(409, "no_transcript", "This recording has no transcript to attribute.")

        stored = (
            await session.scalars(
                select(Segment).where(Segment.transcript_id == transcript_id).order_by(Segment.idx)
            )
        ).all()
        collected = [SttSegment(start=row.start, end=row.end, text=row.text) for row in stored]

        speakers = await self._diarize(session, job, audio, collected)
        if speakers is None:
            # The failure is on the job. Whatever attribution was there before
            # is still true, and wiping it would be the second loss in a row.
            return

        for row, speaker in zip(stored, speakers, strict=True):
            row.speaker = speaker

    async def _diarize(
        self,
        session: AsyncSession,
        job: Job,
        audio: Path,
        collected: list[SttSegment],
    ) -> list[str | None] | None:
        """Find out who was speaking, and never let the answer cost the text.

        A diariser that is down, slow or wrong must not fail a job whose
        transcript already exists: the recording would have to be sent through
        speech-to-text a second time to get back what we are holding. So the
        failure is recorded on the job, the job still finishes, and None says
        the question went unanswered rather than answered with nobody.
        """
        try:
            if not self.settings.diarizer_url:
                raise ApiError(503, "no_diarizer", "No diariser is configured.")
            async with self._diarizer_factory() as http:
                turns = await DiarizerClient(http).diarize(audio)
        except ApiError as failure:
            log.warning("diarisation of job %s failed: %s", job.id, failure.message)
            job.error_code = failure.code
            job.error_message = failure.message
            job.error_params = json.dumps(failure.params)
            return None

        labels = assign_speakers([(item.start, item.end) for item in collected], turns)

        # A re-run after a crash finds the previous attempt's names here.
        await session.execute(delete(Speaker).where(Speaker.job_id == job.id))
        session.add_all(
            Speaker(job_id=job.id, label=label)
            for label in dict.fromkeys(label for label in labels if label)
        )
        return labels

    async def _transcribe_with_retries(
        self,
        client: SttClient,
        audio: Path,
        *,
        model: str,
        language: str | None,
        prompt: str | None,
    ) -> Transcription:
        """Retry a single chunk, never the whole recording.

        Only transport-shaped failures are worth repeating: a refused
        connection, a timeout, a 5xx from an inference server that fell over
        under load. A 4xx means the request itself is wrong -- resending it
        wastes time and, on a metered API, money.
        """
        attempts = max(1, self.settings.stt_retry_attempts)
        last: ApiError | None = None

        for attempt in range(attempts):
            try:
                return await client.transcribe(
                    audio, model=model, language=language, prompt=prompt
                )
            except ApiError as failure:
                if failure.code not in RETRYABLE_CODES:
                    raise
                last = failure
                if attempt < attempts - 1:
                    await asyncio.sleep(self.settings.stt_retry_backoff_seconds * 2**attempt)

        assert last is not None
        raise ApiError(
            503,
            "stt_unavailable",
            f"The speech-to-text server failed {attempts} times in a row.",
            attempts=attempts,
            **last.params,
        )

    async def _plan_chunks(self, audio: Path, duration: float) -> list[Chunk]:
        mode = self.settings.stt_chunking
        if mode == "never" or duration <= 0:
            return [Chunk(index=0, start=0.0, end=max(duration, 0.0))]

        if mode == "auto" and duration <= self.settings.chunk_max_seconds:
            return [Chunk(index=0, start=0.0, end=duration)]

        return plan_chunks(
            duration=duration,
            silences=await detect_silences(audio),
            target=self.settings.chunk_target_seconds,
            hard_max=self.settings.chunk_max_seconds,
        )

    async def _enter(self, session: AsyncSession, job: Job, stage: str) -> None:
        """Say what is being done now, and start counting that part from zero."""
        job.stage = stage
        job.progress = 0.0
        job.heartbeat_at = utcnow()
        await session.commit()

    def _downloaded(
        self, session: AsyncSession, job: Job
    ) -> Callable[[int, int | None], Awaitable[None]]:
        """Turn bytes arriving into a number somebody is watching.

        Written at most once per percentage point: a gigabyte at a megabyte a
        chunk is a thousand chunks, and a thousand commits to move a bar a
        thousandth of the way is a database write nobody asked for. A server
        that declares no length leaves the stage saying what is happening with
        no number attached, which is the honest answer.
        """
        last = -1

        async def report(written: int, declared: int | None) -> None:
            nonlocal last
            if not declared:
                return
            point = int(min(written / declared, 1.0) * 100)
            if point == last:
                return
            last = point
            job.progress = point / 100
            job.heartbeat_at = utcnow()
            await session.commit()

        return report

    async def _acquire_source(self, session: AsyncSession, job: Job) -> Path:
        """Put the original media on disk, whatever it took to get there.

        An upload is already here; a link is not. Fetching happens in the worker
        and never in the request: a two-hour recording would keep an HTTP
        connection open for the length of the download and lose the job with it.
        """
        if job.source_type == "upload":
            return self._find_source(job)

        await self._enter(session, job, "fetching")
        workspace = self.settings.tmp_dir / str(job.id)
        # A crash mid-download leaves a truncated file that looks complete.
        # Uploads are safe to resume this way; a download is not.
        for leftover in sorted(workspace.glob("source*")) if workspace.is_dir() else []:
            leftover.unlink(missing_ok=True)

        allow_private = self.settings.allow_private_network_urls

        if job.source_type == "remote_url":
            async with self._download_factory() as http:
                return await download_media(
                    http,
                    job.source_ref,
                    workspace,
                    self.settings.max_upload_size,
                    allow_private=allow_private,
                    on_progress=self._downloaded(session, job),
                )

        # Checked again here, not only at submission: the answer a name gives can
        # change between the two, and the worker is the one that opens the socket.
        await ensure_allowed_host(job.source_ref, allow_private=allow_private)
        fetched = await fetch_with_ytdlp(
            self.settings.ytdlp_bin, job.source_ref, workspace, self.settings.max_upload_size
        )
        # The link was standing in for a name until now.
        job.title = fetched.title or job.title
        job.author = fetched.author
        job.published_on = fetched.published_on
        if fetched.thumbnail is not None:
            keep = self.settings.media_dir / str(job.id) / "thumbnail.jpg"
            keep.parent.mkdir(parents=True, exist_ok=True)
            # A rename, not a copy: tmp and media are two directories on the
            # one volume the container mounts.
            fetched.thumbnail.replace(keep)
            job.has_thumbnail = True
        return fetched.path

    def _find_source(self, job: Job) -> Path:
        workspace = self.settings.tmp_dir / str(job.id)
        candidates = sorted(workspace.glob("source*")) if workspace.is_dir() else []
        if not candidates:
            raise ApiError(
                410,
                "source_missing",
                "The uploaded file is no longer on disk.",
                job_id=str(job.id),
            )
        return candidates[0]

    async def _resolve_stt(self, session: AsyncSession, job: Job) -> tuple[Provider, str]:
        provider = await session.scalar(
            select(Provider)
            .where(Provider.kind == "stt")
            .order_by(Provider.is_default.desc(), Provider.created_at)
            .limit(1)
        )
        if provider is None:
            raise ApiError(
                503,
                "no_stt_provider",
                "No speech-to-text provider is configured.",
            )

        model = job.stt_model or provider.default_model
        if not model:
            raise ApiError(
                503,
                "no_stt_model",
                f"No model is set for provider {provider.name}.",
                provider=provider.name,
            )
        return provider, model

    def _clear_workspace(self, job_id: object) -> None:
        workspace = self.settings.tmp_dir / str(job_id)
        if not workspace.is_dir():
            return
        for leftover in workspace.iterdir():
            leftover.unlink(missing_ok=True)
        workspace.rmdir()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    settings.ensure_dirs()

    from app.secrets import load_or_create_secret

    database = Database(settings.db_path)
    worker = Worker(settings, database, load_or_create_secret(settings.secret_key_path))
    log.info("worker %s waiting for jobs", worker.identity)
    try:
        await worker.run_forever()
    finally:
        await database.dispose()


if __name__ == "__main__":
    # `python -m app.worker --health` is the container's own liveness probe: the
    # same module, so it reads the same settings the worker is running under.
    if "--health" in sys.argv[1:]:
        raise SystemExit(0 if worker_is_alive(Settings()) else 1)
    asyncio.run(main())
