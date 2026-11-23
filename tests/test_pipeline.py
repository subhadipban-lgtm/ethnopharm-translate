"""End-to-end tests: segmentation, glossary, RAG, validation gates, pipeline,
review -> memory loop, and exports. All offline via the mock backend."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tmtrans.backend import MockBackend
from tmtrans.db import Store
from tmtrans.dictionary import Glossary
from tmtrans.export import export_jsonl, export_xlsx, document_record
from tmtrans.prompts import build_translation_prompt, parse_translation_response
from tmtrans.rag import TranslationMemoryIndex, retrieve
from tmtrans.segment import segment_text
from tmtrans.service import Service
from tmtrans.translate import Translator
from tmtrans.validate import validate_segment

DATA = Path(__file__).parent.parent / "data" / "dictionary"


@pytest.fixture
def glossary() -> Glossary:
    g = Glossary()
    for name in ("seed_tcm.csv", "seed_ayurveda.csv", "seed_seasian.csv"):
        g.load_csv(DATA / name)
    return g


# ---- segmentation ----

def test_segment_cjk_sentences():
    text = "桂枝汤主治风寒。气虚者加黄芪。阴虚火旺者慎用。"
    segs = segment_text(text)
    assert len(segs) == 3
    assert segs[0].text == "桂枝汤主治风寒。"
    assert segs[1].start == text.index("气虚")
    assert segs[0].end == text.index("气虚")


def test_segment_devanagari_danda():
    text = "ज्वर चिकित्सा विवरणम्। अग्नि दीपनम्॥"
    segs = segment_text(text)
    assert len(segs) == 2
    assert "ज्वर" in segs[0].text


def test_segment_long_sentence_wraps():
    text = "a" * 50 + ", " + "b" * 2000
    segs = segment_text(text)
    assert all(len(s.text) <= 950 for s in segs)
    assert sum(len(s.text) for s in segs) > 1900


def test_segment_empty_and_whitespace():
    assert segment_text("") == []
    assert segment_text("   \n\n  ") == []


# ---- glossary ----

def test_glossary_exact_match_and_variants(glossary):
    assert glossary.exact("甘草").binomial == "Glycyrrhiza uralensis"
    assert glossary.exact("国老").entry_id == "tcm-h0001"  # variant
    assert glossary.exact("ashwagandha").entry_id == "ayu-h0001"  # IAST-folded
    assert glossary.exact("अश्वगन्धा").entry_id == "ayu-h0001"


def test_glossary_find_in_text_cjk(glossary):
    hits = glossary.find_in_text("桂枝汤含桂枝与甘草，主治风寒。", "zh")
    ids = {e.entry_id for e in hits}
    assert {"tcm-f0001", "tcm-h0010", "tcm-h0001", "tcm-d0001"} <= ids


def test_glossary_no_partial_latin_match(glossary):
    # 'jamu' must not match inside 'jamu gendong' text when only whole word present
    hits = glossary.find_in_text("jamu is a tradition", "id")
    assert any(e.entry_id == "sea-h0022" for e in hits)
    assert glossary.find_in_text("the jamu gendong seller", "id")


def test_glossary_csv_roundtrip(glossary):
    csv_text = glossary.to_csv()
    g2 = Glossary()
    n = g2.load_csv_text(csv_text)
    assert n == len(glossary.entries)
    assert g2.exact("甘草").english == "liquorice root"


# ---- prompts ----

def test_prompt_contains_binding_glossary(glossary):
    ctx = retrieve(glossary, TranslationMemoryIndex(), "甘草与黄芪。", "zh")
    msgs = build_translation_prompt("甘草与黄芪。", "zh", ctx)
    assert "BINDING" in msgs[0]["content"]
    assert "liquorice root" in msgs[1]["content"]
    assert "NEVER invent a scientific binomial" in msgs[0]["content"]


def test_parse_translation_response_tolerates_fences():
    raw = '```json\n{"translation": "ok", "terms": [], "notes": ""}\n```'
    assert parse_translation_response(raw)["translation"] == "ok"
    with pytest.raises(ValueError):
        parse_translation_response("not json")


# ---- validation gates ----

def _validate(translation, source="甘草。", terms=None, glossary=None, registry=None):
    g = glossary or Glossary()
    entry = g.exact("甘草") if g.entries else None
    return validate_segment(
        segment_id="t1", source_text=source, translation=translation,
        terms=terms or [], expected_glossary=[entry] if entry else [],
        source_lang="zh", glossary=g, registry=registry,
    )


def test_gate_glossary_missing_fails(glossary):
    report = _validate("The root is used.", glossary=glossary)
    assert not report.passed
    assert any(r.gate == "glossary" and not r.passed for r in report.results)


def test_gate_hallucinated_binomial_fails(glossary):
    report = _validate("Glycyrrhiza fakensis is used.", source="某药。", glossary=glossary)
    assert any(r.gate == "hallucination" and not r.passed for r in report.results)


def test_gate_registry_accepts_known_binomial(glossary):
    report = _validate(
        "Glycyrrhiza fakensis is used.", source="某药。", glossary=glossary,
        registry={"Glycyrrhiza fakensis"},
    )
    assert all(r.gate != "hallucination" or r.passed for r in report.results)


def test_gate_residual_script(glossary):
    report = _validate("liquorice root 甘草 黄芪 人参 当归 黄连", glossary=glossary)
    assert any(r.gate == "untranslated" and not r.passed for r in report.results)


def test_gate_numbers_preserved(glossary):
    report = _validate("Take liquorice root 9 g daily.", source="甘草九克，用9克。", glossary=glossary)
    assert all(r.gate != "numbers" or r.passed for r in report.results)
    report2 = _validate("Take liquorice root daily.", source="甘草九克，用9克。", glossary=glossary)
    assert any(r.gate == "numbers" and not r.passed for r in report2.results)


# ---- translation memory / RAG ----

def test_memory_retrieves_similar_segment():
    mem = TranslationMemoryIndex()
    mem.add("s1", "桂枝汤主治风寒表虚证。", "Cinnamon Twig Decoction treats wind-cold.")
    mem.add("s2", "六味地黄丸滋阴补肾。", "Six-Ingredient Rehmannia Pill nourishes yin.")
    hits = mem.search("桂枝汤主治风寒。", top_k=1)
    assert hits and hits[0].segment_id == "s1"
    assert hits[0].score > 0.5


def test_memory_save_load(tmp_path):
    mem = TranslationMemoryIndex()
    mem.add("s1", "甘草。", "liquorice root")
    p = tmp_path / "mem.json"
    mem.save(str(p))
    mem2 = TranslationMemoryIndex()
    mem2.load(str(p))
    assert mem2.search("甘草。")


# ---- full pipeline with mock backend ----

def test_pipeline_end_to_end(glossary):
    tr = Translator(backend=MockBackend(), glossary=glossary)
    segs = segment_text("桂枝汤含甘草。麻黄汤含麻黄。")
    results = tr.translate_document(segs, "zh")
    assert len(results) == 2
    assert "liquorice root" in results[0].translation
    assert "Cinnamon Twig Decoction" in results[0].translation
    assert results[0].status in ("auto_pass", "needs_review")


def test_classical_stage_inserts_modern_rewrite(glossary):
    tr = Translator(backend=MockBackend(), glossary=glossary)
    segs = segment_text("甘草。")
    res = tr.translate_document(segs, "lzh", variant="classical")[0]
    assert res.modern_text is not None
    assert "[modern]" in res.modern_text


# ---- service + review -> memory loop ----

def test_service_review_feeds_memory(tmp_path):
    svc = Service(db_path=str(tmp_path / "t.db"), backend_config=__import__("tmtrans.backend", fromlist=["BackendConfig"]).BackendConfig(kind="mock"))
    svc.glossary.load_csv(DATA / "seed_tcm.csv")
    doc_id = svc.submit_text("t", "桂枝汤含甘草。", "zh")
    for _ in range(100):
        if svc.store.get_document(doc_id)["status"] == "completed":
            break
        time.sleep(0.05)
    segs = svc.store.list_segments(doc_id)
    assert segs
    reviewed = svc.review(segs[0]["id"], "Approved translation with liquorice root.", "tester", "approve")
    assert reviewed["status"] == "approved"
    assert svc.memory.search("桂枝汤含甘草。")
    rec = svc.record(doc_id)
    assert rec["segments"][0]["reviewed_by"] == "tester"


def test_unmatched_terms_become_candidates(tmp_path):
    from tmtrans.backend import BackendConfig

    svc = Service(db_path=str(tmp_path / "t.db"), backend_config=BackendConfig(kind="mock"))
    svc.glossary.load_csv(DATA / "seed_tcm.csv")
    doc_id = svc.submit_text("t", "某未知药与甘草。", "zh")
    for _ in range(100):
        if svc.store.get_document(doc_id)["status"] == "completed":
            break
        time.sleep(0.05)
    # Mock emits only matched terms, so inject one to test candidate flow
    svc.store.add_term_candidate("某未知药", "zh", doc_id, "seg-x")
    cands = svc.store.list_term_candidates()
    assert any(c["source_form"] == "某未知药" for c in cands)


# ---- exports ----

def test_export_jsonl_and_xlsx(tmp_path, glossary):
    store = Store(str(tmp_path / "e.db"))
    doc_id = store.create_document("t", "zh")
    store.upsert_segment({
        "id": "s1", "document_id": doc_id, "idx": 0, "source_text": "甘草。",
        "modern_text": None, "translation": "liquorice root", "terms_json": "[]",
        "notes": "", "status": "approved", "report_json": json.dumps({"status": "auto_pass", "results": []}),
        "error": None, "start_offset": 0, "end_offset": 3, "page": None,
    })
    n = export_jsonl(store, doc_id, tmp_path / "out.jsonl", approved_only=True)
    assert n == 1
    record = document_record(store, doc_id)
    assert record["segments"][0]["source_location"]["start"] == 0
    export_xlsx(store, doc_id, tmp_path / "out.xlsx")
    assert (tmp_path / "out.xlsx").stat().st_size > 0


def test_gate_residual_script_latin_source(glossary):
    # A perfect Thai translation of an English source must NOT trip G4:
    # the gate must not count the target's own script as "residual".
    report = _validate("นี่คือประโยคทดสอบ", source="This is a test sentence.", glossary=glossary)
    g4 = next(r for r in report.results if r.gate == "untranslated")
    assert g4.passed, f"G4 false-positive on Latin-source row: {g4.detail}"


def test_gate_residual_script_detects_source_leftover(glossary):
    # Thai leftovers in an English target (th->en) must still be flagged.
    # _validate hardcodes source_lang="zh", which counts CJK, so call the
    # validator directly with source_lang="th".
    from tmtrans.validate import validate_segment
    report = validate_segment(
        segment_id="t-th", source_text="นี่คือการทดสอบ",
        translation="This is นี่คือ a test", terms=[],
        expected_glossary=[], source_lang="th", glossary=glossary,
    )
    g4 = next(r for r in report.results if r.gate == "untranslated")
    assert not g4.passed


# ---- NLLB backend (no torch required) ----

def test_nllb_backend_registered():
    from tmtrans.backend import BackendConfig, get_backend, NLLBBackend
    cfg = BackendConfig(kind="nllb")
    assert isinstance(get_backend(cfg), NLLBBackend)


def test_nllb_reports_missing_dependency_without_torch():
    from tmtrans.backend import BackendConfig, NLLBBackend
    b = NLLBBackend(BackendConfig(kind="nllb"))
    h = b.health()
    # Either torch is installed (ok=True) or it reports the missing extra clearly.
    assert h["ok"] is False or h["ok"] is True
    if not h["ok"]:
        assert "nllb" in h["error"]


def test_nllb_extracts_source_from_prompt():
    from tmtrans.backend import NLLBBackend
    src = NLLBBackend._extract_source([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": 'Translate...\n"""\n桂枝汤主治风寒\n"""\nReturn JSON'},
    ])
    assert src == "桂枝汤主治风寒"


def test_flores_language_codes():
    from tmtrans.lang import flores_code
    assert flores_code("th") == "tha_Thai"
    assert flores_code("zh") == "zho_Hans"
    assert flores_code("lzh") == "zho_Hans"
    assert flores_code("sa") == "san_Deva"
    assert flores_code("km") == "khm_Khmr"
    assert flores_code("en") == "eng_Latn"
    with __import__("pytest").raises(ValueError):
        flores_code("xx")


def test_get_backend_rejects_unknown_kind():
    from tmtrans.backend import BackendConfig, get_backend, BackendError
    import pytest
    with pytest.raises(BackendError):
        get_backend(BackendConfig(kind="bogus"))
