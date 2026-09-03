import pytest

from app.languages import normalize_language


@pytest.mark.parametrize(
    ("answered", "expected"),
    [
        ("english", "en"),
        ("English", "en"),
        ("  Russian  ", "ru"),
        ("Mandarin", "zh"),  # an alias whisper accepts on the way in
        ("flemish", "nl"),
        ("ru", "ru"),
        ("RU", "ru"),
        ("en-US", "en"),  # the place is not something a transcriber has views on
        ("pt_BR", "pt"),
        ("zh-Hans", "zh"),
    ],
)
def test_what_a_provider_answers_becomes_what_it_accepts(answered: str, expected: str) -> None:
    assert normalize_language(answered) == expected


def test_an_unknown_language_is_left_exactly_as_it_came() -> None:
    """More likely a code we do not know than a mistake -- and dropping it would
    stop the forcing altogether, which is worse than passing it on."""
    assert normalize_language("klingon") == "klingon"


def test_nothing_answered_stays_nothing() -> None:
    assert normalize_language(None) is None
    assert normalize_language("   ") is None
