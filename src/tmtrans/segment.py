"""Text segmentation with CJK / Indic / Thai awareness.

Segmentation operates on source character offsets so every segment can be
traced back to its exact location in the source document for provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sentence terminators: CJK 。！？, Indic danda । ॥, full stops, plus the
# interrobang family. Classical Chinese often lacks punctuation entirely, in
# which case segmentation falls back to line breaks and length caps.
_SENT_END = "。！？!?।॥"
_SENT_RE = re.compile(r"[^" + re.escape(_SENT_END + ".") + r"]*[" + re.escape(_SENT_END + ".") + r"]+\s*|[^" + re.escape(_SENT_END + ".") + r"]+$", re.M)

_MAX_CHARS = 900


@dataclass
class Segment:
    index: int
    text: str
    start: int
    end: int
    page: int | None = None


def _split_long(text: str, start: int) -> list[tuple[str, int, int]]:
    """Hard-wrap over-long sentences at clause boundaries (，、；,:;) or whitespace."""
    out: list[tuple[str, int, int]] = []
    while len(text) > _MAX_CHARS:
        cut = text[:_MAX_CHARS]
        pos = max(
            cut.rfind("，"),
            cut.rfind("、"),
            cut.rfind("；"),
            cut.rfind(";"),
            cut.rfind(","),
            cut.rfind(" "),
        )
        if pos < _MAX_CHARS // 3:
            pos = _MAX_CHARS
        out.append((cut[: pos + 1].strip(), start, start + pos + 1))
        start += pos + 1
        text = text[pos + 1 :].lstrip()
    if text.strip():
        out.append((text.strip(), start, start + len(text)))
    return out


def segment_text(text: str, page: int | None = None) -> list[Segment]:
    """Split a document into sentence/clause segments with source offsets."""
    segments: list[Segment] = []
    for para in re.split(r"\n\s*\n", text):
        base = text.find(para) if para else 0
        if base < 0:
            base = 0
        for m in _SENT_RE.finditer(para):
            s = m.group(0)
            if not s.strip():
                continue
            local_start = base + m.start()
            if len(s) > _MAX_CHARS:
                pieces = _split_long(s, local_start)
            else:
                pieces = [(s.strip(), local_start, local_start + len(s))]
            for piece, st, en in pieces:
                segments.append(
                    Segment(index=len(segments), text=piece, start=st, end=en, page=page)
                )
    # Renumber with contiguous indices
    for i, seg in enumerate(segments):
        seg.index = i
    return segments


def ingest_file(path: str) -> list[Segment]:
    """Ingest a plain-text / markdown / html / pdf / ocr-jsonl file into segments."""
    from pathlib import Path

    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _ingest_pdf(p)
    if suffix == ".jsonl":
        from .ocr import segments_from_jsonl

        return segments_from_jsonl(p)
    raw = p.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
        raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S)
        raw = re.sub(r"<[^>]+>", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
    return segment_text(raw)


def _ingest_pdf(path) -> list[Segment]:
    try:
        import fitz  # pymupdf, optional dependency
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF ingestion requires the optional dependency: pip install tmtrans[pdf]"
        ) from exc
    segments: list[Segment] = []
    with fitz.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            for seg in segment_text(page.get_text(), page=page_no):
                seg.index = len(segments)
                segments.append(seg)
    return segments
