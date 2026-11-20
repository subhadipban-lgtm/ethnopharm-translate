"""Program-level validation against held-out reference datasets.

Three loader routes:
  1. `classical-zh`  — Gare/Classical_Chinese_to_Modern_Chinese via the HF
     datasets-server API. Validates the classical→modern stage directly
     (our modern rewrite scored against the 现代文 reference).
  2. `hf:<org>/<name>` — any HF dataset with parallel fields, e.g.
     jundai2003/medical-insights-en-zh (narrative_zh → narrative). Gated
     datasets work if you accepted their terms and set HF_TOKEN.
  3. `local <file>`  — your own gold pairs (JSONL with source/target keys or
     CSV). This is the recommended domain route: export human-approved
     segments from tmtrans itself, have an expert correct them, and you have
     a recurring regression gold set.

Metrics: corpus chrF++ and BLEU (zh tokenizer for Chinese) from sacrebleu,
plus the program's own safety statistics — validation-gate outcome
distribution, binomial-hallucination errors (must be ~0), reference-binomial
recall, and length-ratio sanity. Deterministic gates stay reproducible: same
input, same score.
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .lang import profile

DATASETS_SERVER = "https://datasets-server.huggingface.co/rows"
_ROWS_PAGE = 100

_BINOMIAL_RE = re.compile(r"\b[A-Z][a-z]{3,}\s+[a-z][a-z-]{2,}\b")


@dataclass
class EvalPair:
    source: str
    reference: str
    meta: dict = field(default_factory=dict)


@dataclass
class SegmentEval:
    source: str
    reference: str
    hypothesis: str
    status: str
    gate_failures: list  # [(gate, severity)]
    error: str | None = None


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------

def _hf_headers() -> dict:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _fetch_rows(dataset: str, config: str, split: str, limit: int) -> list[dict]:
    """Page through the datasets-server rows API (no `datasets` dependency)."""
    rows: list[dict] = []
    offset = 0
    with httpx.Client(timeout=60.0, headers=_hf_headers()) as client:
        while len(rows) < limit:
            length = min(_ROWS_PAGE, limit - len(rows))
            resp = client.get(
                DATASETS_SERVER,
                params={
                    "dataset": dataset, "config": config, "split": split,
                    "offset": offset, "length": length,
                },
            )
            if resp.status_code == 401:
                raise RuntimeError(
                    f"{dataset} is gated: accept its terms on the HF page and export HF_TOKEN"
                )
            resp.raise_for_status()
            batch = resp.json().get("rows", [])
            if not batch:
                break
            rows.extend(r["row"] for r in batch)
            offset += len(batch)
    return rows[:limit]


def parse_classical_rows(rows: list[dict]) -> list[EvalPair]:
    """Gare rows alternate 古文：/现代文： prefixes in a single `text` field."""
    pairs: list[EvalPair] = []
    pending_src = None
    for row in rows:
        text = (row.get("text") or "").strip()
        if text.startswith("古文：") or text.startswith("古文:"):
            pending_src = text.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif text.startswith("现代文：") or text.startswith("现代文:") and pending_src:
            ref = text.split("：", 1)[-1].split(":", 1)[-1].strip()
            pairs.append(EvalPair(source=pending_src, reference=ref, meta={"kind": "classical-zh"}))
            pending_src = None
    return pairs


def load_pairs_classical_zh(limit: int = 100) -> list[EvalPair]:
    rows = _fetch_rows("Gare/Classical_Chinese_to_Modern_Chinese", "default", "train", limit * 2 + 20)
    return parse_classical_rows(rows)[:limit]


def load_pairs_hf(
    dataset: str, config: str = "default", split: str = "train",
    source_field: str = "source", target_field: str = "target", limit: int = 100,
) -> list[EvalPair]:
    rows = _fetch_rows(dataset, config, split, limit)
    pairs = []
    for i, row in enumerate(rows):
        src = str(row.get(source_field) or "").strip()
        ref = str(row.get(target_field) or "").strip()
        if src and ref:
            pairs.append(EvalPair(source=src, reference=ref, meta={"row": i}))
    return pairs


def load_pairs_local(path: str | Path) -> list[EvalPair]:
    p = Path(path)
    pairs: list[EvalPair] = []
    if p.suffix.lower() == ".csv":
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for i, row in enumerate(csv.DictReader(fh)):
                if row.get("source") and row.get("target"):
                    pairs.append(EvalPair(row["source"].strip(), row["target"].strip(), {"row": i}))
    else:
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("source") and rec.get("target"):
                    pairs.append(EvalPair(rec["source"].strip(), rec["target"].strip(), {"row": i}))
    if not pairs:
        raise ValueError(f"no source/target pairs found in {p}")
    return pairs


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

def evaluate_pairs(
    pairs: list[EvalPair],
    translator,
    source_lang: str,
    variant: str | None = None,
    classical_mode: bool = False,
    progress=None,
) -> list[SegmentEval]:
    from .segment import Segment

    results: list[SegmentEval] = []
    for i, pair in enumerate(pairs, 1):
        seg = Segment(index=i - 1, text=pair.source, start=0, end=len(pair.source))
        if classical_mode:
            hyp = translator.modernize(pair.source, source_lang) or ""
            results.append(
                SegmentEval(pair.source, pair.reference, hyp, status="classical", gate_failures=[])
            )
        else:
            res = translator.translate_segment(seg, source_lang, variant, f"eval")
            failures = [
                (r.gate, r.severity) for r in res.report.results if not r.passed and r.severity != "info"
            ]
            results.append(
                SegmentEval(pair.source, pair.reference, res.translation, res.status, failures, res.error)
            )
        if progress:
            progress(i, len(pairs))
    return results


def reference_binomial_recall(results: list[SegmentEval]) -> float | None:
    """Of the Latin binomials present in references, the fraction preserved in
    the hypothesis — the domain-safety metric that matters most."""
    total = hit = 0
    for r in results:
        refs = set(_BINOMIAL_RE.findall(r.reference))
        for b in refs:
            total += 1
            if b in r.hypothesis:
                hit += 1
    return hit / total if total else None


def compute_metrics(results: list[SegmentEval], source_lang: str) -> dict:
    try:
        import sacrebleu
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("evaluation requires sacrebleu: pip install sacrebleu") from exc

    hyps = [r.hypothesis or "" for r in results]
    refs = [r.reference for r in results]
    zh = source_lang in ("zh", "lzh")
    chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
    bleu = sacrebleu.corpus_bleu(hyps, [refs], tokenize="zh" if zh else "13a").score

    n = len(results) or 1
    statuses: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    hallucination_errors = 0
    len_ratios = []
    for r in results:
        statuses[r.status] = statuses.get(r.status, 0) + 1
        for gate, severity in r.gate_failures:
            gate_counts[gate] = gate_counts.get(gate, 0) + 1
            if gate == "hallucination" and severity == "error":
                hallucination_errors += 1
        if r.hypothesis:
            len_ratios.append(len(r.hypothesis) / max(1, len(r.source)))

    return {
        "n_segments": len(results),
        "chrf": round(chrf, 2),
        "bleu": round(bleu, 2),
        "reference_binomial_recall": (
            None if reference_binomial_recall(results) is None
            else round(reference_binomial_recall(results), 4)
        ),
        "status_distribution": {k: round(v / n, 4) for k, v in statuses.items()},
        "gate_failure_counts": gate_counts,
        "binomial_hallucination_errors": hallucination_errors,
        "avg_length_ratio": round(sum(len_ratios) / max(1, len(len_ratios)), 3) if len_ratios else None,
        "errors": sum(1 for r in results if r.error),
    }


def format_report(metrics: dict, title: str) -> str:
    lines = [f"## Evaluation: {title}", ""]
    lines.append(f"- segments: {metrics['n_segments']}")
    lines.append(f"- chrF++: **{metrics['chrf']}**")
    lines.append(f"- BLEU: {metrics['bleu']}")
    if metrics.get("reference_binomial_recall") is not None:
        lines.append(f"- reference-binomial recall: {metrics['reference_binomial_recall']:.1%}")
    lines.append(f"- binomial hallucination errors (G5): **{metrics['binomial_hallucination_errors']}**"
                 "  ← must stay 0")
    lines.append(f"- status distribution: {metrics['status_distribution']}")
    if metrics["gate_failure_counts"]:
        lines.append(f"- gate failures: {metrics['gate_failure_counts']}")
    if metrics.get("avg_length_ratio") is not None:
        lines.append(f"- avg length ratio (hyp/src): {metrics['avg_length_ratio']}")
    if metrics["errors"]:
        lines.append(f"- pipeline errors: {metrics['errors']}")
    return "\n".join(lines)
