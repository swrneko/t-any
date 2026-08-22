import math

# Deliberately pessimistic. Cyrillic and other non-Latin scripts cost far more
# tokens per character than English does, and the failure this guards against is
# the quiet one: Ollama with a context of 8192 truncates the input without a
# word of complaint and returns a confident summary of the first third.
CHARS_PER_TOKEN = 3

# Room for the model's own answer. A budget that fills the context exactly
# leaves nothing to write into.
RESPONSE_RESERVE_TOKENS = 1024

# What a provider is assumed to have when nobody said. Low on purpose: guessing
# high produces silent truncation, guessing low produces an unnecessary
# map-reduce -- one is wrong, the other is merely slower.
DEFAULT_CONTEXT_TOKENS = 8192

MINIMUM_BUDGET_TOKENS = 256


def estimate_tokens(text: str | int) -> int:
    """How many tokens a string is assumed to cost. Takes a length directly as
    well, so a caller adding text up can measure without building it first."""
    length = text if isinstance(text, int) else len(text)
    return math.ceil(length / CHARS_PER_TOKEN)


def input_budget(context_tokens: int, *, prompt_tokens: int) -> int:
    """How much transcript may go into one request."""
    remaining = context_tokens - prompt_tokens - RESPONSE_RESERVE_TOKENS
    return max(remaining, MINIMUM_BUDGET_TOKENS)


def split_for_budget(segments: list[str], *, budget_tokens: int) -> list[str]:
    """Group segments into as few parts as each will fit into.

    Splitting happens on segment boundaries, never mid-sentence. A segment too
    large to fit anywhere is passed through alone rather than dropped: it cannot
    be made to fit, and discarding it would quietly remove part of the meeting.
    """
    parts: list[str] = []
    current: list[str] = []
    current_chars = 0

    for segment in segments:
        # Characters, not per-segment token estimates: the space that joins two
        # segments is a character too, and rounding each segment up separately
        # measures a string nobody ever sends.
        cost = len(segment) + (1 if current else 0)

        if current and estimate_tokens(current_chars + cost) > budget_tokens:
            parts.append(" ".join(current))
            current, current_chars = [], 0
            cost = len(segment)

        current.append(segment)
        current_chars += cost

    if current:
        parts.append(" ".join(current))

    return parts
