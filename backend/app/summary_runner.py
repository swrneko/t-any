import json
import time
from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.llm import LlmClient
from app.models import Preset, Provider, Segment, Summary, Transcript
from app.summarize import estimate_tokens, input_budget, split_for_budget

LlmFactory = Callable[[Provider], httpx.AsyncClient]

REDUCE_SYSTEM = (
    "You are combining partial summaries of one recording into a single answer. "
    "The parts are in order and overlap in style, not in content. Merge them "
    "faithfully, drop nothing, and write in the same language as the parts."
)


class SummaryRunner:
    """Produces one summary, in one pass or in stages.

    Which one is not a setting: the transcript is measured against the
    provider's context window and split only when it has to be.
    """

    def __init__(
        self, settings: Settings, session: AsyncSession, llm_factory: LlmFactory
    ) -> None:
        self.settings = settings
        self.session = session
        self._llm_factory = llm_factory

    async def run(self, summary: Summary) -> None:
        preset = await self._preset(summary)
        segments = await self._segments(summary)
        provider, model, context_tokens = await self._resolve_llm(preset)

        summary.model_used = model

        prompt_tokens = estimate_tokens(preset.system_prompt + preset.user_template)
        budget = input_budget(context_tokens, prompt_tokens=prompt_tokens)
        parts = split_for_budget(segments, budget_tokens=budget)

        async with self._llm_factory(provider) as http:
            client = LlmClient(http)

            if len(parts) == 1:
                await self._stream_into(
                    client,
                    summary,
                    model=model,
                    system=preset.system_prompt,
                    user=preset.user_template.replace("{transcript}", parts[0]),
                    temperature=preset.temperature,
                )
                return

            partials = _kept_partials(summary, len(parts))
            for index, part in enumerate(parts):
                if index < len(partials):
                    # Already answered by an attempt that failed later on.
                    continue
                partials.append(
                    await client.complete(
                        model=model,
                        system=preset.system_prompt,
                        user=preset.user_template.replace("{transcript}", part),
                        temperature=preset.temperature,
                    )
                )
                # Written down as they arrive: reduce fails often enough that
                # redoing seventeen parts to retry the last step is not on.
                summary.partials_json = json.dumps(partials)
                summary.progress = (index + 1) / (len(parts) + 1)
                await self.session.commit()

            joined = "\n\n".join(
                f"Part {index + 1}:\n{text}" for index, text in enumerate(partials)
            )
            await self._stream_into(
                client,
                summary,
                model=model,
                system=REDUCE_SYSTEM,
                user=preset.user_template.replace("{transcript}", joined),
                temperature=preset.temperature,
            )

    async def _stream_into(
        self,
        client: LlmClient,
        summary: Summary,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float | None,
    ) -> None:
        """Accumulate the answer in the row so the browser can watch it grow."""
        buffer: list[str] = []
        last_flush = time.monotonic()

        async for piece in client.stream(
            model=model, system=system, user=user, temperature=temperature
        ):
            buffer.append(piece)
            if time.monotonic() - last_flush >= self.settings.summary_flush_seconds:
                summary.content = "".join(buffer)
                await self.session.commit()
                last_flush = time.monotonic()

        summary.content = "".join(buffer).strip()
        summary.progress = 1.0

    async def _preset(self, summary: Summary) -> Preset:
        preset = await self.session.get(Preset, summary.preset_id) if summary.preset_id else None
        if preset is None:
            raise ApiError(410, "preset_gone", "The preset used for this summary was deleted.")
        return preset

    async def _segments(self, summary: Summary) -> list[str]:
        transcript = await self.session.scalar(
            select(Transcript).where(Transcript.job_id == summary.job_id)
        )
        if transcript is None:
            raise ApiError(409, "transcript_not_ready", "This job has no transcript.")

        rows = await self.session.scalars(
            select(Segment).where(Segment.transcript_id == transcript.id).order_by(Segment.idx)
        )
        texts = [(row.edited_text if row.edited_text is not None else row.text) for row in rows]
        return [text for text in texts if text]

    async def _resolve_llm(self, preset: Preset) -> tuple[Provider, str, int]:
        provider = None
        if preset.provider_id:
            provider = await self.session.get(Provider, preset.provider_id)
        if provider is None:
            provider = await self.session.scalar(
                select(Provider)
                .where(Provider.kind == "llm")
                .order_by(Provider.is_default.desc(), Provider.created_at)
                .limit(1)
            )
        if provider is None:
            raise ApiError(503, "no_llm_provider", "No language model provider is configured.")

        model = preset.model_override or provider.default_model
        if not model:
            raise ApiError(
                503,
                "no_llm_model",
                f"No model is set for provider {provider.name}.",
                provider=provider.name,
            )

        return provider, model, provider.context_tokens or self.settings.llm_context_tokens


def _kept_partials(summary: Summary, expected: int) -> list[str]:
    """Map results a previous attempt got back, when they still apply.

    Retrying a summary that died in the reduce step should not re-ask the model
    about seventeen parts it has already read. More parts than the plan now has
    means the transcript changed underneath, and the lot is thrown away.
    """
    if not summary.partials_json:
        return []
    try:
        stored = json.loads(summary.partials_json)
    except ValueError:
        return []
    if not isinstance(stored, list) or len(stored) > expected:
        return []
    return [str(item) for item in stored]
