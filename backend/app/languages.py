"""What a provider calls a language, and what it accepts being told.

The transcription protocol is symmetric on paper -- `language` comes back in the
same field it goes out in -- and is not symmetric in practice. OpenAI answers
`english`, faster-whisper answers `en`, and only the second form is a valid
input. Since the language detected on the first chunk is forced on every chunk
after it, an answer that cannot be sent back turns the forcing into a no-op.

The table is whisper's own language list rather than ISO 639 at large: these are
whisper-compatible endpoints, and the codes they accept are the codes whisper
uses -- including the two it gets wrong (`jw`, `yue`), which are still the right
thing to send.
"""

CODE_NAMES: dict[str, str] = {
    "af": "afrikaans",
    "am": "amharic",
    "ar": "arabic",
    "as": "assamese",
    "az": "azerbaijani",
    "ba": "bashkir",
    "be": "belarusian",
    "bg": "bulgarian",
    "bn": "bengali",
    "bo": "tibetan",
    "br": "breton",
    "bs": "bosnian",
    "ca": "catalan",
    "cs": "czech",
    "cy": "welsh",
    "da": "danish",
    "de": "german",
    "el": "greek",
    "en": "english",
    "es": "spanish",
    "et": "estonian",
    "eu": "basque",
    "fa": "persian",
    "fi": "finnish",
    "fo": "faroese",
    "fr": "french",
    "gl": "galician",
    "gu": "gujarati",
    "ha": "hausa",
    "haw": "hawaiian",
    "he": "hebrew",
    "hi": "hindi",
    "hr": "croatian",
    "ht": "haitian creole",
    "hu": "hungarian",
    "hy": "armenian",
    "id": "indonesian",
    "is": "icelandic",
    "it": "italian",
    "ja": "japanese",
    "jw": "javanese",
    "ka": "georgian",
    "kk": "kazakh",
    "km": "khmer",
    "kn": "kannada",
    "ko": "korean",
    "la": "latin",
    "lb": "luxembourgish",
    "ln": "lingala",
    "lo": "lao",
    "lt": "lithuanian",
    "lv": "latvian",
    "mg": "malagasy",
    "mi": "maori",
    "mk": "macedonian",
    "ml": "malayalam",
    "mn": "mongolian",
    "mr": "marathi",
    "ms": "malay",
    "mt": "maltese",
    "my": "myanmar",
    "ne": "nepali",
    "nl": "dutch",
    "nn": "nynorsk",
    "no": "norwegian",
    "oc": "occitan",
    "pa": "punjabi",
    "pl": "polish",
    "ps": "pashto",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "sa": "sanskrit",
    "sd": "sindhi",
    "si": "sinhala",
    "sk": "slovak",
    "sl": "slovenian",
    "sn": "shona",
    "so": "somali",
    "sq": "albanian",
    "sr": "serbian",
    "su": "sundanese",
    "sv": "swedish",
    "sw": "swahili",
    "ta": "tamil",
    "te": "telugu",
    "tg": "tajik",
    "th": "thai",
    "tk": "turkmen",
    "tl": "tagalog",
    "tr": "turkish",
    "tt": "tatar",
    "uk": "ukrainian",
    "ur": "urdu",
    "uz": "uzbek",
    "vi": "vietnamese",
    "yi": "yiddish",
    "yo": "yoruba",
    "yue": "cantonese",
    "zh": "chinese",
}

# The other names a provider might answer with for a language already in the
# table above. Whisper accepts these on the way in, so somebody's server may
# well hand them back on the way out.
_ALIASES: dict[str, str] = {
    "burmese": "my",
    "castilian": "es",
    "flemish": "nl",
    "haitian": "ht",
    "letzeburgesch": "lb",
    "mandarin": "zh",
    "moldavian": "ro",
    "moldovan": "ro",
    "panjabi": "pa",
    "pushto": "ps",
    "sinhalese": "si",
    "valencian": "ca",
}

_BY_NAME: dict[str, str] = {name: code for code, name in CODE_NAMES.items()} | _ALIASES


def normalize_language(value: str | None) -> str | None:
    """Turn whatever a provider answered into something it would accept back.

    Anything unrecognised is returned as it came. A language we have never heard
    of is more likely a code we do not know than a mistake, and dropping it would
    silently stop forcing anything at all.
    """
    if value is None:
        return None

    cleaned = value.strip().lower().replace("_", "-")
    if not cleaned:
        return None

    if cleaned in CODE_NAMES:
        return cleaned
    if cleaned in _BY_NAME:
        return _BY_NAME[cleaned]

    # A regional tag: `en-US` is the language plus a place it is spoken in, and
    # the place is not something a transcription endpoint has an opinion about.
    base = cleaned.split("-", 1)[0]
    if base in CODE_NAMES:
        return base

    return value.strip()
