"""Bilingual terminology store: herbs, formulas, diseases, concepts.

The dictionary is the backbone of validated translation: matches are injected
into the prompt as hard constraints, and every emitted term is checked against
the same store during validation. Unmatched terms are flagged for review, never
auto-resolved to a model-invented binomial.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .lang import normalize_form

CATEGORY_LABELS = {
    "herb": "herb / materia medica",
    "formula": "classical formula",
    "disease": "disease / syndrome",
    "concept": "medical concept",
    "species": "accepted species",
}


@dataclass
class DictEntry:
    entry_id: str
    category: str  # herb | formula | disease | concept | species
    source_lang: str  # ISO 639 code of the canonical form
    source_form: str  # canonical vernacular form (Hanzi, Devanagari, IAST, ...)
    variants: list[str] = field(default_factory=list)  # alternate spellings / synonyms
    english: str = ""  # preferred English rendering
    binomial: str = ""  # accepted scientific name (herb/species)
    inchikey: str = ""  # optional chemical identifier for downstream linkage
    family: str = ""
    tradition: str = ""  # tcm | ayurveda | se-asian | ...
    pharmacopoeia: str = ""  # e.g. ChP 2020, API, Ayurvedic Pharmacopoeia of India
    notes: str = ""

    @property
    def all_forms(self) -> list[str]:
        return [self.source_form, *self.variants]


class Glossary:
    """In-memory terminology index with exact and fuzzy matching."""

    def __init__(self) -> None:
        self.entries: dict[str, DictEntry] = {}
        self._exact: dict[str, DictEntry] = {}
        self._by_lang: dict[str, list[DictEntry]] = {}

    def add(self, entry: DictEntry) -> None:
        self.entries[entry.entry_id] = entry
        for form in entry.all_forms:
            if not form:
                continue
            self._exact[normalize_form(form)] = entry
            # CJK forms are matched by substring; also index without spaces.
            self._exact[re.sub(r"\s+", "", normalize_form(form))] = entry
        self._by_lang.setdefault(entry.source_lang, []).append(entry)

    def load_csv(self, path: str | Path) -> int:
        with open(path, encoding="utf-8-sig") as fh:
            return self.load_csv_text(fh.read())

    def load_csv_text(self, text: str) -> int:
        reader = csv.DictReader(io.StringIO(text))
        n = 0
        for row in reader:
            if not row.get("entry_id"):
                continue
            entry = DictEntry(
                entry_id=row["entry_id"].strip(),
                category=(row.get("category") or "herb").strip(),
                source_lang=(row.get("source_lang") or "zh").strip(),
                source_form=(row.get("source_form") or "").strip(),
                variants=[
                    v.strip() for v in (row.get("variants") or "").split("|") if v.strip()
                ],
                english=(row.get("english") or "").strip(),
                binomial=(row.get("binomial") or "").strip(),
                inchikey=(row.get("inchikey") or "").strip().upper(),
                family=(row.get("family") or "").strip(),
                tradition=(row.get("tradition") or "").strip(),
                pharmacopoeia=(row.get("pharmacopoeia") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
            self.add(entry)
            n += 1
        return n

    def exact(self, form: str) -> DictEntry | None:
        key = normalize_form(form)
        return self._exact.get(key) or self._exact.get(re.sub(r"\s+", "", key))

    def find_in_text(self, text: str, lang: str, max_fuzzy: int = 0) -> list[DictEntry]:
        """Return every entry whose canonical form or variant appears in text.

        CJK entries match by substring; Latin/Indic entries match on word
        boundaries (after diacritic folding) to avoid partial-word hits.
        """
        found: dict[str, DictEntry] = {}
        norm = normalize_form(text)
        compact = re.sub(r"\s+", "", norm)
        for entry in self._by_lang.get(lang, []):
            for form in entry.all_forms:
                if not form:
                    continue
                f = normalize_form(form)
                if not f:
                    continue
                if self._is_cjk(form):
                    if f in compact:
                        found[entry.entry_id] = entry
                        break
                else:
                    pattern = r"(?<![\w])" + re.escape(f) + r"(?![\w])"
                    if re.search(pattern, norm):
                        found[entry.entry_id] = entry
                        break
        results = list(found.values())
        if max_fuzzy > 0:
            results.extend(self._fuzzy_candidates(text, lang, exclude=set(found), limit=max_fuzzy))
        return results

    def _fuzzy_candidates(
        self, text: str, lang: str, exclude: set[str], limit: int
    ) -> list[DictEntry]:
        """Suggest near-matches for human review only (never auto-applied)."""
        from rapidfuzz import fuzz, process

        choices = {
            e.entry_id: e.source_form
            for e in self._by_lang.get(lang, [])
            if e.entry_id not in exclude and not self._is_cjk(e.source_form)
        }
        if not choices:
            return []
        tokens = [t for t in re.split(r"[^\w\u0900-\u097F]+", normalize_form(text)) if len(t) > 4]
        out: dict[str, DictEntry] = {}
        for token in tokens[:40]:
            for match, score, key in process.extract(
                token, choices, scorer=fuzz.ratio, limit=1, score_cutoff=88
            ):
                out[key] = self.entries[key]
                if len(out) >= limit:
                    return list(out.values())
        return list(out.values())

    @staticmethod
    def _is_cjk(form: str) -> bool:
        return any("\u4e00" <= c <= "\u9fff" for c in form)

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "entry_id",
                "category",
                "source_lang",
                "source_form",
                "variants",
                "english",
                "binomial",
                "inchikey",
                "family",
                "tradition",
                "pharmacopoeia",
                "notes",
            ]
        )
        for e in self.entries.values():
            writer.writerow(
                [
                    e.entry_id,
                    e.category,
                    e.source_lang,
                    e.source_form,
                    "|".join(e.variants),
                    e.english,
                    e.binomial,
                    e.inchikey,
                    e.family,
                    e.tradition,
                    e.pharmacopoeia,
                    e.notes,
                ]
            )
        return buf.getvalue()

    def stats(self) -> dict:
        by_lang: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for e in self.entries.values():
            by_lang[e.source_lang] = by_lang.get(e.source_lang, 0) + 1
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
        return {"entries": len(self.entries), "by_language": by_lang, "by_category": by_cat}


def strip_iast(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
