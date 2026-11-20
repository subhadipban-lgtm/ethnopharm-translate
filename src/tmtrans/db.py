"""SQLite persistence: documents, segments, validation reports, review state,
and unmatched-term candidates for dictionary growth."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    variant TEXT,
    tradition TEXT,
    source_file TEXT,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    total_segments INTEGER NOT NULL DEFAULT 0,
    done_segments INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    modern_text TEXT,
    translation TEXT,
    terms_json TEXT,
    notes TEXT,
    status TEXT NOT NULL,
    report_json TEXT,
    error TEXT,
    start_offset INTEGER,
    end_offset INTEGER,
    page INTEGER,
    reviewed_by TEXT,
    reviewed_at REAL,
    UNIQUE(document_id, idx)
);
CREATE TABLE IF NOT EXISTS term_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_form TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    document_id TEXT,
    segment_id TEXT,
    occurrences INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'open',
    UNIQUE(source_form, source_lang)
);
"""


class Store:
    def __init__(self, path: str | Path = "data/tmtrans.db") -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- documents ----
    def create_document(
        self,
        title: str,
        source_lang: str,
        variant: str | None = None,
        tradition: str | None = None,
        source_file: str | None = None,
    ) -> str:
        doc_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO documents(id, title, source_lang, variant, tradition, source_file, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (doc_id, title, source_lang, variant, tradition, source_file, time.time()),
        )
        self.conn.commit()
        return doc_id

    def get_document(self, doc_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT d.*, "
            " SUM(CASE WHEN s.status='auto_pass' THEN 1 ELSE 0 END) AS auto_pass,"
            " SUM(CASE WHEN s.status='needs_review' THEN 1 ELSE 0 END) AS needs_review,"
            " SUM(CASE WHEN s.status='approved' THEN 1 ELSE 0 END) AS approved,"
            " SUM(CASE WHEN s.status='failed' THEN 1 ELSE 0 END) AS failed"
            " FROM documents d LEFT JOIN segments s ON s.document_id=d.id"
            " GROUP BY d.id ORDER BY d.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_document_progress(self, doc_id: str, done: int, total: int, status: str) -> None:
        self.conn.execute(
            "UPDATE documents SET done_segments=?, total_segments=?, status=? WHERE id=?",
            (done, total, status, doc_id),
        )
        self.conn.commit()

    # ---- segments ----
    def upsert_segment(self, seg: dict) -> None:
        self.conn.execute(
            "INSERT INTO segments(id, document_id, idx, source_text, modern_text, translation,"
            " terms_json, notes, status, report_json, error, start_offset, end_offset, page)"
            " VALUES(:id,:document_id,:idx,:source_text,:modern_text,:translation,:terms_json,"
            " :notes,:status,:report_json,:error,:start_offset,:end_offset,:page)"
            " ON CONFLICT(document_id, idx) DO UPDATE SET"
            " translation=excluded.translation, modern_text=excluded.modern_text,"
            " terms_json=excluded.terms_json, notes=excluded.notes, status=excluded.status,"
            " report_json=excluded.report_json, error=excluded.error",
            seg,
        )
        self.conn.commit()

    def list_segments(self, doc_id: str, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM segments WHERE document_id=?"
        params: list = [doc_id]
        if status:
            q += " AND status=?"
            params.append(status)
        q += " ORDER BY idx"
        rows = self.conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["terms"] = json.loads(d.pop("terms_json") or "[]")
            d["report"] = json.loads(d.pop("report_json") or "{}")
            out.append(d)
        return out

    def get_segment(self, segment_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["terms"] = json.loads(d.pop("terms_json") or "[]")
        d["report"] = json.loads(d.pop("report_json") or "{}")
        return d

    def review_segment(
        self,
        segment_id: str,
        translation: str,
        reviewer: str,
        action: str,  # approve | reject
        notes: str | None = None,
    ) -> dict | None:
        seg = self.get_segment(segment_id)
        if not seg:
            return None
        status = "approved" if action == "approve" else "needs_review"
        self.conn.execute(
            "UPDATE segments SET translation=?, status=?, reviewed_by=?, reviewed_at=?,"
            " notes=COALESCE(?, notes) WHERE id=?",
            (translation, status, reviewer, time.time(), notes, segment_id),
        )
        self.conn.commit()
        return self.get_segment(segment_id)

    def approved_pairs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, source_text, translation FROM segments WHERE status='approved'"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- unmatched term candidates ----
    def add_term_candidate(self, source_form: str, source_lang: str, doc_id: str, seg_id: str) -> None:
        self.conn.execute(
            "INSERT INTO term_candidates(source_form, source_lang, document_id, segment_id)"
            " VALUES(?,?,?,?)"
            " ON CONFLICT(source_form, source_lang) DO UPDATE SET occurrences=occurrences+1",
            (source_form, source_lang, doc_id, seg_id),
        )
        self.conn.commit()

    def list_term_candidates(self, state: str = "open") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM term_candidates WHERE state=? ORDER BY occurrences DESC", (state,)
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_term_candidate(self, candidate_id: int, state: str = "resolved") -> None:
        self.conn.execute(
            "UPDATE term_candidates SET state=? WHERE id=?", (state, candidate_id)
        )
        self.conn.commit()
