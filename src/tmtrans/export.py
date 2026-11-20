"""Export translated documents as bilingual, provenance-annotated datasets.

Formats: JSONL (aligned segments with validation + review provenance),
CSV/XLSX (for reviewers), plain text (final translation), and a full document
record conforming to schemas/translation-record.schema.json.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path


def document_record(store, doc_id: str) -> dict:
    doc = store.get_document(doc_id)
    if not doc:
        raise KeyError(f"unknown document {doc_id}")
    segments = store.list_segments(doc_id)
    return {
        "document_id": doc["id"],
        "title": doc["title"],
        "source_language": doc["source_lang"],
        "target_language": "en",
        "variant": doc.get("variant"),
        "tradition": doc.get("tradition"),
        "source_file": doc.get("source_file"),
        "created_at": doc["created_at"],
        "segments": [
            {
                "segment_id": s["id"],
                "index": s["idx"],
                "source_text": s["source_text"],
                "modern_text": s.get("modern_text"),
                "translation": s.get("translation") or "",
                "terms": s["terms"],
                "validation": s["report"],
                "status": s["status"],
                "reviewed_by": s.get("reviewed_by"),
                "reviewed_at": s.get("reviewed_at"),
                "source_location": {
                    "start": s.get("start_offset"),
                    "end": s.get("end_offset"),
                    "page": s.get("page"),
                },
            }
            for s in segments
        ],
    }


def export_jsonl(store, doc_id: str, path: str | Path, approved_only: bool = False) -> int:
    record = document_record(store, doc_id)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for seg in record["segments"]:
            if approved_only and seg["status"] != "approved":
                continue
            fh.write(json.dumps(seg, ensure_ascii=False) + "\n")
            n += 1
    return n


def export_full_json(store, doc_id: str, path: str | Path) -> None:
    record = document_record(store, doc_id)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)


def export_csv(store, doc_id: str, path: str | Path, approved_only: bool = False) -> int:
    record = document_record(store, doc_id)
    n = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["segment_id", "index", "source_text", "modern_text", "translation",
             "status", "validation_status", "reviewed_by", "terms", "notes"]
        )
        for s in record["segments"]:
            if approved_only and s["status"] != "approved":
                continue
            writer.writerow(
                [
                    s["segment_id"],
                    s["index"],
                    s["source_text"],
                    s.get("modern_text") or "",
                    s["translation"],
                    s["status"],
                    (s["validation"] or {}).get("status", ""),
                    s.get("reviewed_by") or "",
                    "; ".join(
                        f"{t.get('source','')}={t.get('english','')}" for t in s["terms"]
                    ),
                    "",
                ]
            )
            n += 1
    return n


def export_xlsx(store, doc_id: str, path: str | Path) -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    record = document_record(store, doc_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "bilingual"
    headers = ["index", "source_text", "modern_text", "translation", "status", "terms", "gates_failed"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    status_fill = {
        "approved": PatternFill("solid", fgColor="C6EFCE"),
        "auto_pass": PatternFill("solid", fgColor="E2EFDA"),
        "needs_review": PatternFill("solid", fgColor="FFEB9C"),
        "failed": PatternFill("solid", fgColor="FFC7CE"),
    }
    n = 0
    for s in record["segments"]:
        failed = [
            r["gate"] for r in (s["validation"] or {}).get("results", [])
            if not r["passed"] and r["severity"] in ("error", "warning")
        ]
        ws.append(
            [
                s["index"],
                s["source_text"],
                s.get("modern_text") or "",
                s["translation"],
                s["status"],
                "; ".join(f"{t.get('source','')}={t.get('english','')}" for t in s["terms"]),
                ", ".join(failed),
            ]
        )
        fill = status_fill.get(s["status"])
        if fill:
            ws.cell(row=ws.max_row, column=5).fill = fill
        n += 1
    for col, width in zip("ABCDEFG", (8, 45, 45, 55, 14, 35, 20)):
        ws.column_dimensions[col].width = width
    wb.save(path)
    return n


def export_text(store, doc_id: str, path: str | Path, approved_only: bool = True) -> int:
    record = document_record(store, doc_id)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for s in record["segments"]:
            if approved_only and s["status"] != "approved":
                continue
            if s["translation"]:
                fh.write(s["translation"].strip() + "\n\n")
                n += 1
    return n
