import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^[a-zA-Z0-9._-]+$"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    is_admin: bool


class ProviderOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    base_url: str
    default_model: str | None
    context_tokens: int | None
    is_default: bool
    # Always masked. The full key leaves this process only towards the provider.
    api_key: str | None


class ProviderIn(BaseModel):
    kind: Literal["stt", "llm"]
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1)
    api_key: str | None = None
    default_model: str | None = None
    context_tokens: int | None = Field(default=None, gt=0)
    is_default: bool = False


class ProviderPatch(BaseModel):
    """Everything optional, and the key follows its own rule.

    Absent leaves the stored key alone, an empty string clears it, and anything
    else replaces it. The mask this API hands out is never accepted back, or a
    round trip through the edit form would overwrite the key with its own
    disguise.
    """

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=1)
    api_key: str | None = None
    default_model: str | None = None
    context_tokens: int | None = Field(default=None, gt=0)
    is_default: bool | None = None


class ProviderProbeIn(BaseModel):
    """A saved provider, or a draft nobody has committed to yet."""

    provider_id: uuid.UUID | None = None
    base_url: str | None = None
    api_key: str | None = None


class ProviderProbeOut(BaseModel):
    reachable: bool
    status: int | None = None
    latency_ms: int | None = None
    models: list[str] = []
    # A failed probe is a successful request: the verdict travels in the body.
    error_code: str | None = None


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    # The upload's filename or the link that was submitted.
    source_ref: str
    # What the extractor knew: a channel and a calendar day, both absent for an
    # upload. `has_thumbnail` says whether /jobs/{id}/thumbnail has anything.
    author: str | None
    published_on: str | None
    has_thumbnail: bool
    # What the recording still costs on disk, and null once it is only words.
    audio_bytes: int | None
    diarize: bool
    status: str
    progress: float
    language: str | None
    duration_sec: float | None
    # A code the UI translates, plus the values to interpolate into it.
    error_code: str | None
    error_params: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


class Retention(BaseModel):
    """How long things are kept. Null means forever, and that is the default.

    Two policies rather than one, because the expensive half and the valuable
    half are not the same half: dropping audio frees nearly all of the space
    and loses nearly none of the content, while dropping the recording entirely
    is a real loss and has to be asked for separately.
    """

    audio_days: int | None = Field(default=None, ge=1)
    job_days: int | None = Field(default=None, ge=1)


class WebhookIn(BaseModel):
    """The address to announce a finished job to.

    The secret follows the same rule as a provider key: absent leaves the
    stored one alone, an empty string clears it, anything else replaces it.
    """

    url: str | None = None
    secret: str | None = None


class WebhookOut(BaseModel):
    url: str | None
    # Masked, always. The full secret leaves this process only towards the
    # receiver that is meant to check it.
    secret: str | None


class WebhookTestOut(BaseModel):
    delivered: bool
    status: int | None = None
    # A receiver that is down is an answer, not a failed request.
    error_code: str | None = None


class StorageOut(BaseModel):
    audio_bytes: int
    # Thumbnails, and whatever else a recording keeps beside its audio.
    other_bytes: int
    recordings: int


class JobsDeleteIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    # The audio alone: an hour of it is tens of megabytes, the words are tens
    # of kilobytes, and only one of the two is worth keeping forever.
    audio_only: bool = False


class JobsDeleteOut(BaseModel):
    deleted: int
    # Said out loud rather than folded into the count: a recording still being
    # worked on is left alone, and silence about that reads as success.
    skipped: int


class SegmentOut(BaseModel):
    idx: int
    start: float
    end: float
    # What it should read as: the correction if there is one, else what the
    # provider heard. `edited` says which, so a correction can be undone.
    text: str
    edited: bool = False
    # The label the diariser gave, never the name a person typed over it: the
    # label is the identity, and renaming must not rewrite every segment.
    speaker: str | None


class SegmentIn(BaseModel):
    # Blank restores the provider's own words, which is the only way to undo a
    # correction -- and the reason the original is never overwritten.
    text: str = Field(max_length=5000)


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    display_name: str | None


class SpeakerIn(BaseModel):
    # Blank puts the label back, which is the only way to undo a rename.
    display_name: str = Field(max_length=128)


class TranscriptOut(BaseModel):
    job_id: uuid.UUID
    language: str | None
    # Derived from the segments, never stored: exports and edits are layers on
    # top of the immutable raw response.
    text: str
    segments: list[SegmentOut]
    speakers: list[SpeakerOut]


class ApiTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ApiTokenCreated(ApiTokenOut):
    # Present exactly once, in the response that created it.
    token: str


class ShareIn(BaseModel):
    # Null means the link lives until it is revoked, which is what most people
    # want and what the button does without asking.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    job_id: uuid.UUID
    created_at: datetime
    expires_at: datetime | None


class PublicTranscriptOut(BaseModel):
    """What someone holding a link gets. No owner, no source, no job status:
    a shared transcript is a document, not a window into the instance."""

    job_id: uuid.UUID
    title: str
    author: str | None
    published_on: str | None
    language: str | None
    duration_sec: float | None
    has_audio: bool
    text: str
    segments: list["SegmentOut"]
    # Names without ids: a reader may see who spoke and may not rename them.
    speakers: list["PublicSpeakerOut"]


class PublicSpeakerOut(BaseModel):
    label: str
    display_name: str | None


class SearchHit(BaseModel):
    job_id: uuid.UUID
    job_title: str
    idx: int
    start: float
    # The matching words are wrapped in \x02 and \x03 rather than in markup:
    # the surrounding text is whatever someone said, and may contain anything.
    excerpt: str


class PresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    system_prompt: str
    user_template: str
    model_override: str | None
    provider_id: uuid.UUID | None
    temperature: float | None
    output_format: str
    is_builtin: bool
    # Set only on builtins; the UI shows a translation of this, not `name`.
    builtin_key: str | None


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    system_prompt: str = Field(min_length=1, max_length=8000)
    user_template: str = Field(min_length=1, max_length=8000)
    model_override: str | None = None
    provider_id: uuid.UUID | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    output_format: str = "markdown"


class SummaryOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    preset_id: uuid.UUID | None
    # Copied at creation: a deleted preset must not erase the label on a result
    # someone already read.
    preset_name: str
    status: str
    progress: float
    content: str
    partials_json: str | None
    model_used: str | None
    error_code: str | None
    error_params: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


class JobUrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    diarize: bool = False


class SummaryIn(BaseModel):
    preset_id: uuid.UUID


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class UserCreateIn(Credentials):
    is_admin: bool = False


class UserPatch(BaseModel):
    """Both fields are an administrator's doing: a promotion, or a password
    handed out because somebody forgot theirs."""

    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRowOut(UserOut):
    # What deleting this person would take with them.
    jobs: int


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
