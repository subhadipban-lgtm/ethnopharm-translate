"""Deterministic validation gates applied to every machine translation.

Gates (no LLM-in-the-loop judgement here — validation must be reproducible):
  G1 json          — response parses and has the required keys
  G2 non_empty     — translation is non-empty and not a copy of the source
  G3 glossary      — every matched glossary rendering appears in the output
  G4 untranslated  — residual source script in the output (untranslated spans)
  G5 hallucination — binomials not attested in the glossary or a validator-
                     supplied registry are rejected
  G6 numbers       — digits/dosages in the source are preserved
  G7 length        — output/source length ratio within plausible bounds

Segment status after gates: auto_pass | needs_review | failed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dictionary import Glossary

_INCHIKEY_RE = re.compile(r"\b[A-Z]{14}-[A-Z]{10}-[A-Z]\b")
_BINOMIAL_RE = re.compile(r"\b[A-Z][a-z]{3,}\s+[a-z][a-z-]{2,}\b")

# Capitalised English words that are legitimate sentence starts, not genera.
_STOPWORDS = {
    "The", "This", "These", "Those", "When", "Where", "Which", "While", "After",
    "Before", "During", "In", "On", "At", "For", "With", "Without", "From", "To",
    "It", "Its", "If", "As", "By", "Or", "And", "But", "Not", "No", "Yes", "Take",
    "Use", "Used", "Add", "Mix", "Boil", "Decoct", "Grind", "Dry", "Dried", "Fresh",
    "Traditional", "Chinese", "Medicine", "Ayurveda", "Ayurvedic", "Dose", "Dosage",
    "Treatment", "Patient", "Patients", "Chapter", "Section", "Note", "Notes",
    "According", "However", "Therefore", "Thus", "Hence", "Also", "Then", "There",
}


@dataclass
class GateResult:
    gate: str
    passed: bool
    severity: str  # error | warning | info
    detail: str = ""


@dataclass
class ValidationReport:
    segment_id: str
    results: list[GateResult] = field(default_factory=list)

    @property
    def errors(self) -> list[GateResult]:
        return [r for r in self.results if not r.passed and r.severity == "error"]

    @property
    def warnings(self) -> list[GateResult]:
        return [r for r in self.results if not r.passed and r.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        if self.warnings:
            return "needs_review"
        return "auto_pass"

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "status": self.status,
            "results": [vars(r) for r in self.results],
        }


_CJK_RANGES = (
    ("\u4e00", "\u9fff"),
    ("\u3040", "\u30ff"),
)
_INDIC_RANGES = (
    ("\u0900", "\u097f"),  # Devanagari
    ("\u0980", "\u09ff"),  # Bengali
    ("\u0b80", "\u0bff"),  # Tamil
    ("\u0e00", "\u0e7f"),  # Thai
    ("\u0e80", "\u0eff"),  # Lao
    ("\u1000", "\u109f"),  # Myanmar
    ("\u1780", "\u17ff"),  # Khmer
)


def _residual_script_ratio(text: str, source_lang: str) -> float:
    if not text:
        return 0.0
    ranges = _CJK_RANGES if source_lang in ("zh", "lzh", "ja") else _INDIC_RANGES
    if source_lang in ("vi", "id", "ms", "tl"):
        return 0.0  # Latin-script sources can't be detected this way
    count = sum(1 for c in text if any(lo <= c <= hi for lo, hi in ranges))
    return count / max(1, len(text))


def _known_binomials(glossary: Glossary, registry: set[str] | None) -> set[str]:
    known = {e.binomial for e in glossary.entries.values() if e.binomial}
    if registry:
        known |= registry
    return {b.strip() for b in known}


def validate_segment(
    segment_id: str,
    source_text: str,
    translation: str,
    terms: list[dict],
    expected_glossary: list,
    source_lang: str,
    glossary: Glossary,
    registry: set[str] | None = None,
) -> ValidationReport:
    report = ValidationReport(segment_id=segment_id)

    # G2 non-empty / not a copy
    empty = not translation.strip()
    copied = translation.strip() == source_text.strip()
    report.results.append(
        GateResult("non_empty", not (empty or copied), "error",
                   "empty translation" if empty else ("translation identical to source" if copied else ""))
    )

    # G3 glossary compliance: every expected rendering must appear verbatim
    missing = []
    for entry in expected_glossary:
        if entry.english and entry.english.lower() not in translation.lower():
            missing.append(f"{entry.source_form} -> {entry.english}")
    report.results.append(
        GateResult("glossary", not missing, "error",
                   "glossary renderings missing: " + "; ".join(missing[:6]) if missing else "")
    )

    # G4 residual untranslated source script
    ratio = _residual_script_ratio(translation, source_lang)
    report.results.append(
        GateResult("untranslated", ratio < 0.05, "warning" if ratio < 0.25 else "error",
                   f"residual source-script ratio {ratio:.2%}" if ratio >= 0.05 else "")
    )

    # G5 binomial hallucination: any Latin binomial in the output that is not
    # attested in the glossary or registry is rejected.
    known = _known_binomials(glossary, registry)
    hallucinated = []
    for m in _BINOMIAL_RE.finditer(translation):
        candidate = m.group(0)
        if any(part in _STOPWORDS for part in candidate.split()):
            continue
        # Accept exact matches and matches that begin a longer attested name
        # (e.g. a subspecies), but never partial/unknown genera.
        if candidate not in known and not any(
            k.startswith(candidate + " ") for k in known
        ):
            hallucinated.append(candidate)
    report.results.append(
        GateResult("hallucination", not hallucinated, "error",
                   "unattested binomials: " + "; ".join(sorted(set(hallucinated))[:6]) if hallucinated else "")
    )

    # G6 numbers preserved
    src_nums = re.findall(r"\d+(?:\.\d+)?", source_text)
    tgt_nums = set(re.findall(r"\d+(?:\.\d+)?", translation))
    lost = [n for n in src_nums if n not in tgt_nums]
    report.results.append(
        GateResult("numbers", not lost, "warning",
                   "source numbers missing in translation: " + ", ".join(lost[:8]) if lost else "")
    )

    # G7 length plausibility
    if translation.strip():
        ratio_len = len(translation) / max(1, len(source_text))
        plausible = 0.15 <= ratio_len <= 8.0
        report.results.append(
            GateResult("length", plausible, "warning",
                       f"length ratio {ratio_len:.2f} outside [0.15, 8.0]" if not plausible else "")
        )

    # Info gate: unmatched terms register (drives review queue and dictionary growth)
    unmatched = [t for t in terms if t.get("status") == "unmatched"]
    report.results.append(
        GateResult("term_register", not unmatched, "info",
                   f"{len(unmatched)} unmatched term(s) for dictionary review" if unmatched else "")
    )

    return report
