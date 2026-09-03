import uuid

from fastapi import APIRouter
from sqlalchemy import or_, select

from app import presets as catalogue
from app.deps import CurrentUserDep, SessionDep
from app.errors import ApiError
from app.models import Preset, User
from app.schemas import PresetIn, PresetOut

router = APIRouter(prefix="/presets", tags=["presets"])

TRANSCRIPT_PLACEHOLDER = "{transcript}"


def _validate(payload: PresetIn) -> None:
    if TRANSCRIPT_PLACEHOLDER not in payload.user_template:
        # Without it the model is handed an instruction and no transcript, and
        # answers anyway -- confidently, about nothing.
        raise ApiError(
            422,
            "template_without_transcript",
            "The template must contain {transcript}.",
        )


async def _editable_preset(session: SessionDep, user: User, preset_id: uuid.UUID) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None or (preset.owner_id not in (None, user.id)):
        raise ApiError(404, "preset_not_found", "No such preset.")
    if preset.is_builtin:
        raise ApiError(
            409,
            "preset_is_builtin",
            "Built-in presets cannot be changed. Copy it and edit the copy.",
        )
    return preset


@router.get("")
async def list_presets(user: CurrentUserDep, session: SessionDep) -> list[PresetOut]:
    presets = await session.scalars(
        select(Preset).where(or_(Preset.owner_id == user.id, Preset.owner_id.is_(None)))
    )

    # The built-ins are ordered by the catalogue and the rest by age. Ordering
    # all of them by `created_at` would put a preset added in a later release
    # at the bottom of an installation that has been running a while and beside
    # its relatives on a fresh one -- the same release offering two different
    # lists. The catalogue is read here rather than bound at import so that a
    # release which reorders it needs no other change.
    rank = {preset.key: index for index, preset in enumerate(catalogue.BUILTIN_PRESETS)}
    rows = sorted(
        presets,
        key=lambda preset: (
            not preset.is_builtin,
            rank.get(preset.builtin_key or "", len(rank)),
            preset.created_at,
        ),
    )
    return [PresetOut.model_validate(preset) for preset in rows]


@router.post("", status_code=201)
async def create_preset(
    payload: PresetIn, user: CurrentUserDep, session: SessionDep
) -> PresetOut:
    _validate(payload)

    preset = Preset(owner_id=user.id, is_builtin=False, **payload.model_dump())
    session.add(preset)
    await session.commit()
    return PresetOut.model_validate(preset)


@router.put("/{preset_id}")
async def update_preset(
    preset_id: uuid.UUID, payload: PresetIn, user: CurrentUserDep, session: SessionDep
) -> PresetOut:
    _validate(payload)

    preset = await _editable_preset(session, user, preset_id)
    for field, value in payload.model_dump().items():
        setattr(preset, field, value)

    await session.commit()
    return PresetOut.model_validate(preset)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> None:
    preset = await _editable_preset(session, user, preset_id)
    await session.delete(preset)
    await session.commit()
