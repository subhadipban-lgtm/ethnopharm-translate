"""Evaluation harness tests (offline: local fixtures + mock backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tmtrans.backend import MockBackend
from tmtrans.dictionary import Glossary
from tmtrans.evaluation import (
    EvalPair,
    SegmentEval,
    compute_metrics,
    evaluate_pairs,
    format_report,
    load_pairs_local,
    parse_classical_rows,
    reference_binomial_recall,
)
from tmtrans.rag import TranslationMemoryIndex
from tmtrans.translate import Translator

DATA = Path(__file__).parent.parent / "data" / "dictionary"


@pytest.fixture
def translator() -> Translator:
    g = Glossary()
    g.load_csv(DATA / "seed_tcm.csv")
    return Translator(backend=MockBackend(), glossary=g, memory=TranslationMemoryIndex())


# ---- classical-zh parser ----

def test_parse_classical_rows_pairs_interleaved():
    rows = [
        {"text": "古文：桂枝汤主治风寒。"},
        {"text": "现代文：桂枝汤用来治疗风寒。"},
        {"text": "古文：甘草二两。"},
        {"text": "现代文：甘草两钱。"},
    ]
    pairs = parse_classical_rows(rows)
    assert len(pairs) == 2
    assert pairs[0].source == "桂枝汤主治风寒。"
    assert pairs[1].reference == "甘草两钱。"


def test_parse_classical_rows_skips_orphans():
    rows = [{"text": "古文：孤句无对。"}, {"text": "无关行"}]
    assert parse_classical_rows(rows) == []


# ---- local loader ----

def test_load_pairs_local_jsonl(tmp_path):
    p = tmp_path / "gold.jsonl"
    p.write_text(
        '{"source": "桂枝汤主治风寒。", "target": "Cinnamon Twig Decoction treats wind-cold."}\n'
        '{"source": "甘草。", "target": "liquorice root."}\n'
        '{"source": "", "target": "skipped"}\n',
        encoding="utf-8",
    )
    pairs = load_pairs_local(p)
    assert len(pairs) == 2
    assert pairs[0].reference.startswith("Cinnamon")


def test_load_pairs_local_csv(tmp_path):
    p = tmp_path / "gold.csv"
    p.write_text("source,target\n麻黄汤,ephedra decoction\n", encoding="utf-8")
    pairs = load_pairs_local(p)
    assert pairs[0].source == "麻黄汤"


def test_load_pairs_local_rejects_empty(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"foo": 1}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_pairs_local(p)


# ---- runner + metrics (mock backend) ----

def test_evaluate_pairs_and_metrics(translator):
    pairs = [
        EvalPair("桂枝汤主治风寒。", "Cinnamon Twig Decoction treats wind-cold patterns."),
        EvalPair("甘草二两。", "liquorice root, two liang."),
    ]
    results = evaluate_pairs(pairs, translator, "zh")
    assert len(results) == 2
    assert all(r.hypothesis for r in results)
    metrics = compute_metrics(results, "zh")
    assert 0 <= metrics["chrf"] <= 100
    assert metrics["bleu"] >= 0
    assert metrics["n_segments"] == 2
    assert metrics["binomial_hallucination_errors"] == 0  # mock only emits glossary binomials
    assert metrics["status_distribution"]
    assert "chrF++" in format_report(metrics, "unit test")


def test_classical_mode_uses_modernize(translator):
    pairs = [EvalPair("桂枝汤主治風寒。", "桂枝汤用来治疗风寒。")]
    results = evaluate_pairs(pairs, translator, "lzh", classical_mode=True)
    assert results[0].status == "classical"
    assert "[modern]" in results[0].hypothesis  # mock marks the rewrite


def test_reference_binomial_recall():
    r1 = SegmentEval("src", "Use Curcuma longa and Glycyrrhiza glabra.", "Curcuma longa is used.", "auto_pass", [])
    r2 = SegmentEval("src", "Add Panax ginseng.", "no binomial here", "auto_pass", [])
    assert reference_binomial_recall([r1, r2]) == pytest.approx(1 / 3)
    assert reference_binomial_recall([SegmentEval("s", "no latin", "none", "auto_pass", [])]) is None


def test_format_report_highlights_hallucinations():
    metrics = {
        "n_segments": 1, "chrf": 50.0, "bleu": 10.0,
        "reference_binomial_recall": 0.5, "status_distribution": {"auto_pass": 1.0},
        "gate_failure_counts": {"hallucination": 2}, "binomial_hallucination_errors": 2,
        "avg_length_ratio": 1.2, "errors": 0,
    }
    report = format_report(metrics, "t")
    assert "chrF++" in report and "hallucination" in report
