"""Prompt construction with hard glossary constraints.

The glossary is injected as a binding constraint block rather than a suggestion:
the model must reproduce the given English term verbatim and must never invent
a binomial for an unmatched herb. Unmatched terms are kept as source-script
transliterations and surfaced in the term register for validation/review.
"""

from __future__ import annotations

import json

from .lang import profile
from .rag import RetrievedContext

SYSTEM_PROMPT = """You are a specialist translator of traditional medicine literature \
(Traditional Chinese Medicine, Ayurveda, and Southeast Asian ethnopharmacology).

Rules you must follow:
1. Translate faithfully and literally; do not summarise, expand, or omit.
2. GLOSSARY TERMS ARE BINDING. For every term listed in the glossary block, \
use the exact English rendering given. Never substitute a synonym.
3. NEVER invent a scientific binomial. If a plant, mineral, formula or disease \
name is not in the glossary, keep the source term (romanised if the target \
language uses Latin script) and mark it as untranslated.
4. Do not add medical advice, dosages, or commentary that is not in the source.
5. Preserve numbers, measurements and dosage quantities exactly.
6. Output JSON only, with no markdown fences and no extra keys."""

USER_TEMPLATE = """Translate the following {source_name} passage into English.

{glossary_block}{memory_block}Source passage:
\"\"\"
{source_text}
\"\"\"

Return a JSON object with exactly these keys:
- "translation": the English translation (string)
- "terms": a list of objects, one per traditional-medicine term you translated or \
encountered, each with keys:
    "source": the term exactly as it appears in the source passage
    "english": the English rendering you used (glossary rendering if listed)
    "binomial": scientific name, or "" if not established by the glossary
    "entry_id": the glossary entry id if listed there, else ""
    "status": "matched" if from the glossary, "unmatched" otherwise
- "notes": one short sentence about any ambiguity, or ""
"""

CLASSICAL_SYSTEM = """You are a philologist specialising in classical medical Chinese (文言文) \
and classical Indic medical Sanskrit. Rewrite the classical passage into clear, \
faithful modern {modern_name}. Do not translate into English. Do not add, omit or \
interpret beyond the source. Output JSON only: {{"modern": "..."}}."""

CLASSICAL_USER = """Rewrite this classical passage into modern {modern_name}:

\"\"\"
{source_text}
\"\"\""""


def build_glossary_block(ctx: RetrievedContext) -> str:
    if not ctx.glossary:
        return ""
    lines = ["GLOSSARY (binding — use these exact English renderings):"]
    for e in ctx.glossary:
        parts = [f"- id={e.entry_id}", f"category={e.category}", f'"{e.source_form}"']
        if e.english:
            parts.append(f'-> "{e.english}"')
        if e.binomial:
            parts.append(f"binomial: {e.binomial}")
        if e.pharmacopoeia:
            parts.append(f"pharmacopoeia: {e.pharmacopoeia}")
        lines.append(" | ".join(parts))
    return "\n".join(lines) + "\n\n"


def build_memory_block(ctx: RetrievedContext) -> str:
    if not ctx.memory:
        return ""
    lines = ["REFERENCE TRANSLATIONS (approved examples for style, not binding):"]
    for h in ctx.memory:
        lines.append(f'- source: "{h.source_text}"\n  approved: "{h.target_text}"')
    return "\n".join(lines) + "\n\n"


def build_translation_prompt(
    source_text: str, source_lang: str, ctx: RetrievedContext
) -> list[dict]:
    user = USER_TEMPLATE.format(
        source_name=profile(source_lang).name,
        glossary_block=build_glossary_block(ctx),
        memory_block=build_memory_block(ctx),
        source_text=source_text,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_classical_prompt(source_text: str, modern_lang: str) -> list[dict]:
    return [
        {"role": "system", "content": CLASSICAL_SYSTEM.format(modern_name=profile(modern_lang).name)},
        {
            "role": "user",
            "content": CLASSICAL_USER.format(
                modern_name=profile(modern_lang).name, source_text=source_text
            ),
        },
    ]


def parse_translation_response(raw: str) -> dict:
    """Tolerant JSON extraction: strips code fences, finds the outermost object."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object in model response: {raw[:200]!r}")
    obj = json.loads(text[start : end + 1])
    if "translation" not in obj or not isinstance(obj["translation"], str):
        raise ValueError("Response JSON missing 'translation' string")
    obj.setdefault("terms", [])
    obj.setdefault("notes", "")
    if not isinstance(obj["terms"], list):
        obj["terms"] = []
    return obj
