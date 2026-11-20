"""Translation orchestration: segment -> RAG -> (optional classical stage) ->
LLM -> validation -> review queue.

The pipeline is synchronous by design for the local server; documents are
processed as background jobs by the web layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from . import lang as langmod
from .backend import BackendError, LLMBackend
from .dictionary import Glossary
from .prompts import (
    build_classical_prompt,
    build_translation_prompt,
    parse_translation_response,
)
from .rag import RetrievedContext, TranslationMemoryIndex, retrieve
from .segment import Segment
from .validate import ValidationReport, validate_segment


@dataclass
class SegmentResult:
    segment: Segment
    translation: str
    terms: list[dict]
    notes: str
    modern_text: str | None  # classical-stage intermediate, if any
    context: RetrievedContext
    report: ValidationReport
    status: str
    error: str | None = None
    attempts: int = 1


@dataclass
class Translator:
    backend: LLMBackend
    glossary: Glossary
    memory: TranslationMemoryIndex = field(default_factory=TranslationMemoryIndex)
    registry: set[str] | None = None  # accepted binomials (e.g. LOTUS InChIKey sidecar)
    max_retries: int = 2

    def translate_segment(
        self,
        segment: Segment,
        source_lang: str,
        variant: str | None = None,
        document_id: str = "",
    ) -> SegmentResult:
        segment_id = f"{document_id or 'doc'}-{segment.index:05d}-{uuid.uuid4().hex[:6]}"
        modern_text = None
        source_for_translation = segment.text

        if langmod.requires_classical_stage(source_lang, variant):
            modern_lang = "zh" if source_lang in ("zh", "lzh") else source_lang
            modern_text = self._classical_stage(segment.text, modern_lang)
            if modern_text:
                source_for_translation = modern_text

        ctx = retrieve(self.glossary, self.memory, source_for_translation, source_lang)
        messages = build_translation_prompt(source_for_translation, source_lang, ctx)

        raw = None
        parsed = None
        error = None
        attempts = 0
        for attempts in range(1, self.max_retries + 2):
            try:
                raw = self.backend.complete(messages)
                parsed = parse_translation_response(raw)
                error = None
                break
            except (BackendError, ValueError) as exc:
                error = str(exc)
                # Feed the parse error back for a self-repair attempt.
                messages = messages + [
                    {"role": "assistant", "content": raw or ""},
                    {
                        "role": "user",
                        "content": f"Your previous response was invalid: {error}. "
                        "Return only the corrected JSON object.",
                    },
                ]
                time.sleep(0.2)

        if parsed is None:
            report = ValidationReport(segment_id=segment_id)
            from .validate import GateResult

            report.results.append(GateResult("json", False, "error", error or "no response"))
            return SegmentResult(
                segment=segment,
                translation="",
                terms=[],
                notes="",
                modern_text=modern_text,
                context=ctx,
                report=report,
                status="failed",
                error=error,
                attempts=attempts,
            )

        report = validate_segment(
            segment_id=segment_id,
            source_text=source_for_translation,
            translation=parsed["translation"],
            terms=parsed["terms"],
            expected_glossary=ctx.glossary,
            source_lang=source_lang,
            glossary=self.glossary,
            registry=self.registry,
        )
        return SegmentResult(
            segment=segment,
            translation=parsed["translation"],
            terms=parsed["terms"],
            notes=parsed["notes"],
            modern_text=modern_text,
            context=ctx,
            report=report,
            status=report.status,
            attempts=attempts,
        )

    def _classical_stage(self, text: str, modern_lang: str) -> str | None:
        try:
            raw = self.backend.complete(build_classical_prompt(text, modern_lang))
            import json

            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                obj = json.loads(raw[start : end + 1])
                return obj.get("modern") or None
        except Exception:
            return None
        return None

    def translate_document(
        self,
        segments: list[Segment],
        source_lang: str,
        variant: str | None = None,
        document_id: str = "",
        progress: Callable[[int, int, SegmentResult], None] | None = None,
    ) -> list[SegmentResult]:
        results: list[SegmentResult] = []
        for i, seg in enumerate(segments):
            res = self.translate_segment(seg, source_lang, variant, document_id)
            results.append(res)
            if progress:
                progress(i + 1, len(segments), res)
        return results
