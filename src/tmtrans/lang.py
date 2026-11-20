"""Source-language metadata and classical/modern stage decisions for traditional
medicine corpora."""

from __future__ import annotations

import re
from dataclasses import dataclass

import langcodes


@dataclass(frozen=True)
class LangProfile:
    code: str
    name: str
    script: str
    classical_stage_available: bool


# Traditional-medicine languages plus common regional languages. The
# classical_stage_available flag marks traditions where an intermediate
# "classical -> modern vernacular" rewrite is meaningful before translation.
_PROFILES = {
    "zh": LangProfile("zh", "Chinese", "Hans", True),
    "lzh": LangProfile("lzh", "Literary/Classical Chinese", "Hani", True),
    "sa": LangProfile("sa", "Sanskrit", "Deva", True),
    "pi": LangProfile("pi", "Pali", "Deva", True),
    "hi": LangProfile("hi", "Hindi", "Deva", True),
    "ta": LangProfile("ta", "Tamil", "Taml", True),
    "th": LangProfile("th", "Thai", "Thai", True),
    "km": LangProfile("km", "Khmer", "Khmr", True),
    "lo": LangProfile("lo", "Lao", "Laoo", True),
    "my": LangProfile("my", "Burmese", "Mymr", True),
    "vi": LangProfile("vi", "Vietnamese", "Latn", True),
    "id": LangProfile("id", "Indonesian", "Latn", False),
    "ms": LangProfile("ms", "Malay", "Latn", False),
    "tl": LangProfile("tl", "Tagalog", "Latn", False),
    "en": LangProfile("en", "English", "Latn", False),
}


def profile(code: str) -> LangProfile:
    return _PROFILES.get(code, LangProfile(code, code, "", False))


def supported_source_codes() -> list[str]:
    return [c for c in _PROFILES if c != "en"]


def requires_classical_stage(code: str, variant: str | None = None) -> bool:
    """Whether to insert a classical -> modern stage before translating."""
    if variant == "classical":
        return profile(code).classical_stage_available
    if variant == "modern":
        return False
    return code == "lzh"


def _strip_diacritics(s: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def normalize_form(text: str) -> str:
    """Canonical key for dictionary matching: lowercase, diacritic-free,
    whitespace-collapsed. Diacritics matter for Sanskrit IAST matching, so the
    raw form is always kept alongside."""
    return re.sub(r"\s+", " ", _strip_diacritics(text).lower()).strip()
