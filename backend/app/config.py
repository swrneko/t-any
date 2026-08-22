from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.chunking import HARD_MAX_SECONDS, TARGET_SECONDS
from app.summarize import DEFAULT_CONTEXT_TOKENS

AuthMode = Literal["builtin", "proxy", "disabled"]
ChunkingMode = Literal["auto", "always", "never"]


class Settings(BaseSettings):
    """Process configuration. Environment variables carry no prefix: AUTH_MODE, DATA_DIR, ..."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    data_dir: Path = Path("/data")
    frontend_dist: Path | None = None

    max_upload_size: int = 5 * 1024**3

    sse_poll_seconds: float = 1.0
    cancel_poll_seconds: float = 1.0
    heartbeat_stale_seconds: float = 120.0

    # How long to wait for a remote server to answer at all. The body itself is
    # given no deadline: a long recording takes as long as it takes.
    download_connect_seconds: float = 30.0

    # Off by default: an account on this instance must not become a way to read
    # the cloud metadata endpoint or the router's admin page. Turn it on when the
    # point of the instance is pulling recordings off your own NAS.
    allow_private_network_urls: bool = False

    # The extractor is a binary, not a library: it updates far more often than
    # this application does, and an operator has to be able to point at a newer
    # one without waiting for a release here.
    ytdlp_bin: str = "yt-dlp"

    # No OpenAI-compatible endpoint exists for diarisation, so this is not a
    # provider row: it is one URL, set by the operator, pointing at a container
    # that is off unless someone turned it on. Unset means the feature is not
    # offered rather than that it fails halfway through a job.
    diarizer_url: str | None = None

    stt_retry_attempts: int = 3
    stt_retry_backoff_seconds: float = 2.0

    stt_chunking: ChunkingMode = "auto"
    chunk_target_seconds: float = TARGET_SECONDS
    chunk_max_seconds: float = HARD_MAX_SECONDS

    # Bootstrap seed only. Once a provider row exists the database is the source
    # of truth, so changing a provider never means editing env and restarting.
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_context_tokens: int = DEFAULT_CONTEXT_TOKENS

    # How often the worker writes streamed summary text back to the database.
    # Every token would hammer SQLite; once a second is smooth enough to read.
    summary_flush_seconds: float = 0.5

    # Where to POST a job's result when it finishes. Set by the operator, never
    # by a user, which is why it is not subject to the private-address check:
    # an automation endpoint on the same LAN is the normal case.
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_timeout_seconds: float = 10.0

    auth_mode: AuthMode = "builtin"
    proxy_user_header: str = "X-Remote-User"
    session_cookie_name: str = "ta_session"
    session_max_age_days: int = 30
    # Turn on once the instance is behind TLS. Off by default because the
    # first thing everyone does is open http://localhost:8927, and a cookie
    # the browser silently drops looks exactly like a broken login.
    session_cookie_secure: bool = False

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def db_path(self) -> Path:
        return self.db_dir / "app.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret.key"

    def ensure_dirs(self) -> None:
        for directory in (self.db_dir, self.media_dir, self.tmp_dir):
            directory.mkdir(parents=True, exist_ok=True)
