import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(sa.types.TypeDecorator[datetime]):
    """Store naive UTC, hand back aware UTC.

    SQLite keeps no offset, so an aware value goes in and a naive one comes out.
    That breaks twice: comparing a bound aware timestamp against stored naive
    text gives nonsense, and a naive timestamp handed to a browser renders in
    whatever timezone the viewer happens to be sitting in.
    """

    impl = sa.DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    username: Mapped[str] = mapped_column(sa.String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class ApiToken(Base):
    """A bearer token, so everything the UI does is reachable from a script.

    Stored as a plain SHA-256 of a long random string, not as an argon2 hash:
    the secret has full entropy already, there is nothing to brute-force, and
    this one is checked on every single request.
    """

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(128))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class InstanceSetting(Base):
    """Configuration that outlives the environment.

    Set in the UI, kept here, read without a restart -- the same bargain as
    providers, for the handful of values that have nowhere else to live. The
    value is JSON so a policy can grow a field without a migration.
    """

    __tablename__ = "instance_settings"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[str] = mapped_column(sa.Text)


class Provider(Base):
    """An OpenAI-compatible endpoint.

    STT and LLM share this table but never share a client: the protocols differ
    (/v1/audio/transcriptions vs /v1/chat/completions) and so do their failures.
    """

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    kind: Mapped[str] = mapped_column(sa.String(8), index=True)  # stt | llm
    name: Mapped[str] = mapped_column(sa.String(128))
    base_url: Mapped[str] = mapped_column(sa.Text)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(sa.LargeBinary, nullable=True)
    default_model: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    context_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    extra_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    # One default per kind, said where it cannot be argued with: the API demotes
    # the previous one in the same transaction, and anything that does not is
    # refused by the database rather than left picking a row at random.
    __table_args__ = (
        sa.Index(
            "uq_providers_default_per_kind",
            "kind",
            unique=True,
            sqlite_where=sa.text("is_default"),
        ),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    source_type: Mapped[str] = mapped_column(sa.String(16))  # upload | remote_url | ytdlp
    source_ref: Mapped[str] = mapped_column(sa.Text)
    title: Mapped[str] = mapped_column(sa.Text)

    # What the extractor knew about the recording. A channel name and a day, not
    # an instant: yt-dlp reports the upload date with no time and no zone, and
    # storing it as a timestamp would move it across midnight for half the world.
    author: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    published_on: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    has_thumbnail: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    status: Mapped[str] = mapped_column(sa.String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(sa.Float, default=0.0)

    # Asked for per recording, not per instance: diarisation costs minutes of
    # someone's GPU, and most of what people transcribe has one voice in it.
    diarize: Mapped[bool] = mapped_column(sa.Boolean, default=False)

    language: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    prompt: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    stt_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    stt_model: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    sha256: Mapped[str | None] = mapped_column(sa.String(64), index=True, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    # An error code the UI can translate; message is the English fallback.
    error_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    error_params: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    worker_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    # The provider's answer, verbatim and never rewritten. Every export format
    # and every user edit is a layer computed on top of this.
    raw_json: Mapped[str] = mapped_column(sa.Text)
    language: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Preset(Base):
    """A named way of asking for a summary.

    Kept in the database with editing in the UI rather than in YAML or in code:
    being able to invent "bullets only, in Russian, for my Obsidian vault" on the
    spot is the main reason to host this instead of using a hosted service.
    """

    __tablename__ = "presets"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    # Null for the built-in presets: they belong to everyone.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )

    name: Mapped[str] = mapped_column(sa.String(128))
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(sa.Text)
    user_template: Mapped[str] = mapped_column(sa.Text)

    model_override: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    temperature: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    output_format: Mapped[str] = mapped_column(sa.String(16), default="markdown")

    is_builtin: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    # Stable identifier the UI translates. The name column holds the English
    # fallback for API consumers with no translation layer.
    builtin_key: Mapped[str | None] = mapped_column(sa.String(64), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Summary(Base):
    """One application of one preset to one transcript.

    A row per attempt, never an overwrite: applying three presets leaves three
    results to compare, and re-running with a different model does not destroy
    what the previous one said.
    """

    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    preset_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("presets.id", ondelete="SET NULL"), nullable=True
    )
    preset_name: Mapped[str] = mapped_column(sa.String(128))

    status: Mapped[str] = mapped_column(sa.String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(sa.Float, default=0.0)
    content: Mapped[str] = mapped_column(sa.Text, default="")
    # Map results are kept because reduce fails often -- local models love to
    # return something unparseable -- and redoing seventeen chunks is not on.
    partials_json: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    model_used: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    error_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    error_params: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    worker_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Share(Base):
    """A public, read-only link to one transcript.

    One live link per job, not a list of them: a second token is a second thing
    to remember to revoke, and nobody remembers. The token itself is the secret,
    so it is long enough not to be guessed and is never derived from the job id.
    """

    __tablename__ = "shares"

    token: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Speaker(Base):
    """One voice in one recording.

    The label the diariser invented is the identity and never changes; the name
    a person puts on it lives in one column, so renaming SPEAKER_01 to "Marina"
    is a single write and every segment, export and share redraws itself.
    """

    __tablename__ = "speakers"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(sa.String(64))
    display_name: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    __table_args__ = (sa.UniqueConstraint("job_id", "label", name="uq_speakers_job_label"),)


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid7)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(sa.Integer)
    start: Mapped[float] = mapped_column(sa.Float)
    end: Mapped[float] = mapped_column(sa.Float)
    text: Mapped[str] = mapped_column(sa.Text)
    # Edits live beside the original, never on top of it: this buys "reset my
    # edits" and "re-transcribe with another model, keep the edits to compare".
    edited_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    speaker: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
