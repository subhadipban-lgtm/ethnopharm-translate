"""OCR layer tests: reading-order logic, stitching, mock OCR end-to-end
(folder -> pages -> segments -> translation), JSONL round-trip."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

from tmtrans.backend import BackendConfig
from tmtrans.dictionary import Glossary
from tmtrans.ocr import (
    Line,
    MockOCRBackend,
    discover_images,
    ocr_folder,
    order_lines,
    segments_from_jsonl,
    stitch,
    write_jsonl,
)
from tmtrans.segment import ingest_file, segment_text
from tmtrans.service import Service

DATA = Path(__file__).parent.parent / "data" / "dictionary"

# Minimal valid 1x1 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ---- reading order & stitching ----

def test_order_lines_rtl_columns():
    # Two vertical columns: x=100 (right, read first) and x=0 (left).
    lines = [
        Line("col2-line1", bbox=(0, 0, 20, 100)),
        Line("col1-line2", bbox=(100, 50, 20, 100)),
        Line("col1-line1", bbox=(100, 0, 20, 100)),
        Line("col2-line2", bbox=(0, 50, 20, 100)),
    ]
    ordered = order_lines(lines, "rtl-columns")
    assert [ln.text for ln in ordered] == ["col1-line1", "col1-line2", "col2-line1", "col2-line2"]


def test_order_lines_ltr():
    lines = [
        Line("second", bbox=(0, 100, 200, 20)),
        Line("first", bbox=(0, 0, 200, 20)),
    ]
    assert [ln.text for ln in order_lines(lines, "ltr-lines")] == ["first", "second"]


def test_order_lines_without_boxes_preserved():
    lines = [Line("a"), Line("b")]
    assert [ln.text for ln in order_lines(lines, "rtl-columns")] == ["a", "b"]


def test_stitch_cjk_joins_without_separator():
    assert stitch(["桂枝湯主治", "風寒表虛證。"], "\n") == "桂枝湯主治風寒表虛證。"


def test_stitch_latin_keeps_lines():
    assert stitch(["rau má chữa", "bỏng nhẹ"], "\n") == "rau má chữa\nbỏng nhẹ"


# ---- discovery ----

def test_discover_images_natural_sort(tmp_path):
    for name in ("p10.png", "p2.png", "p1.png", "notes.txt", "p3.jpg"):
        (tmp_path / name).write_bytes(PNG)
    names = [p.name for p in discover_images(tmp_path)]
    assert names == ["p1.png", "p2.png", "p3.jpg", "p10.png"]


def test_discover_images_rejects_empty(tmp_path):
    with pytest.raises(Exception):
        discover_images(tmp_path)


# ---- mock OCR end-to-end ----

@pytest.fixture
def scans_dir(tmp_path):
    d = tmp_path / "scans"
    d.mkdir()
    for name in ("page_01.png", "page_02.png", "page_03.png"):
        (d / name).write_bytes(PNG)
    return d


def test_ocr_folder_mock(scans_dir):
    pages = ocr_folder(str(scans_dir), "lzh", MockOCRBackend())
    assert len(pages) == 3
    assert [p.page for p in pages] == [1, 2, 3]
    assert all("。" in p.text for p in pages)
    assert pages[0].backend == "MockOCRBackend"


def test_ocr_service_end_to_end(tmp_path, scans_dir):
    svc = Service(
        db_path=str(tmp_path / "t.db"),
        backend_config=BackendConfig(kind="mock"),
        ocr_config=__import__("tmtrans.ocr", fromlist=["OCRBackendConfig"]).OCRBackendConfig(kind="mock"),
    )
    svc.glossary.load_csv(DATA / "seed_tcm.csv")
    doc_id = svc.submit_ocr_folder(
        str(scans_dir), "zh", variant=None, tradition="tcm", title="scan test",
        reading_order="rtl-columns",
    )
    for _ in range(200):
        d = svc.store.get_document(doc_id)
        if d["status"] in ("completed", "error"):
            break
        time.sleep(0.05)
    assert d["status"] == "completed", d
    segs = svc.store.list_segments(doc_id)
    assert segs
    pages_seen = {s["page"] for s in segs}
    assert pages_seen == {1, 2, 3}
    joined = " ".join(s["translation"] for s in segs)
    assert "Cinnamon Twig Decoction" in joined or "liquorice" in joined


def test_ocr_service_rejects_bad_reading_order(tmp_path, scans_dir):
    svc = Service(db_path=str(tmp_path / "t.db"), backend_config=BackendConfig(kind="mock"))
    with pytest.raises(ValueError):
        svc.submit_ocr_folder(str(scans_dir), "zh", reading_order="bottom-up")


# ---- JSONL round-trip ----

def test_jsonl_roundtrip(tmp_path, scans_dir):
    pages = ocr_folder(str(scans_dir), "lzh", MockOCRBackend())
    out = tmp_path / "ocr.jsonl"
    write_jsonl(pages, out, "lzh", "rtl-columns", iast=False)
    recs = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(recs) == 3
    assert recs[0]["lang"] == "lzh" and recs[0]["reading_order"] == "rtl-columns"

    segments = segments_from_jsonl(out)
    assert segments
    assert {s.page for s in segments} == {1, 2, 3}

    # ingest_file dispatches .jsonl to the same path (tmtrans translate out.jsonl)
    via_ingest = ingest_file(str(out))
    assert [s.text for s in via_ingest] == [s.text for s in segments]
