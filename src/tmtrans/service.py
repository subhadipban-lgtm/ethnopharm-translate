"""Application service: wires store, glossary, memory and translator together
and runs document translation as background jobs."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

from .backend import BackendConfig, get_backend
from .db import Store
from .dictionary import Glossary
from .export import document_record
from .rag import TranslationMemoryIndex
from .segment import Segment, ingest_file, segment_text
from .translate import Translator


class Service:
    def __init__(
        self,
        db_path: str = "data/tmtrans.db",
        dictionary_paths: list[str] | None = None,
        backend_config: BackendConfig | None = None,
        registry_path: str | None = None,
    ) -> None:
        self.store = Store(db_path)
        self.glossary = Glossary()
        for p in dictionary_paths or []:
            if Path(p).exists():
                self.glossary.load_csv(p)
        self.memory = TranslationMemoryIndex()
        self._load_memory_from_db()
        self.backend_config = backend_config or BackendConfig.from_env()
        self.backend = get_backend(self.backend_config)
        self.registry = self._load_registry(registry_path) if registry_path else None
        self._jobs: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def _load_memory_from_db(self) -> None:
        for pair in self.store.approved_pairs():
            self.memory.add(pair["id"], pair["source_text"], pair["translation"])

    @staticmethod
    def _load_registry(path: str) -> set[str]:
        """Optional accepted-binomial registry (one per line). The NP-Alpha
        Gate-A LOTUS registry can be exported to this format and dropped in."""
        p = Path(path)
        if not p.exists():
            return set()
        return {line.strip() for line in p.read_text().splitlines() if line.strip()}

    def translator(self) -> Translator:
        return Translator(
            backend=self.backend, glossary=self.glossary, memory=self.memory, registry=self.registry
        )

    # ---- ingestion + background translation ----
    def submit_text(
        self, title: str, text: str, source_lang: str, variant: str | None = None,
        tradition: str | None = None,
    ) -> str:
        doc_id = self.store.create_document(title, source_lang, variant, tradition)
        segments = segment_text(text)
        self._start_job(doc_id, segments, source_lang, variant)
        return doc_id

    def submit_file(
        self, path: str, title: str | None = None, source_lang: str = "zh",
        variant: str | None = None, tradition: str | None = None,
    ) -> str:
        doc_id = self.store.create_document(
            title or Path(path).name, source_lang, variant, tradition, source_file=path
        )
        segments = ingest_file(path)
        self._start_job(doc_id, segments, source_lang, variant)
        return doc_id

    def _start_job(self, doc_id: str, segments: list[Segment], source_lang: str, variant: str | None) -> None:
        thread = threading.Thread(
            target=self._run_job, args=(doc_id, segments, source_lang, variant), daemon=True
        )
        with self._lock:
            self._jobs[doc_id] = thread
        thread.start()

    def _run_job(self, doc_id: str, segments: list[Segment], source_lang: str, variant: str | None) -> None:
        self.store.update_document_progress(doc_id, 0, len(segments), "running")
        translator = self.translator()
        done = 0
        try:
            for seg in segments:
                res = translator.translate_segment(seg, source_lang, variant, doc_id)
                self.store.upsert_segment(
                    {
                        "id": res.report.segment_id,
                        "document_id": doc_id,
                        "idx": seg.index,
                        "source_text": seg.text,
                        "modern_text": res.modern_text,
                        "translation": res.translation,
                        "terms_json": __import__("json").dumps(res.terms, ensure_ascii=False),
                        "notes": res.notes,
                        "status": res.status,
                        "report_json": __import__("json").dumps(
                            res.report.to_dict(), ensure_ascii=False
                        ),
                        "error": res.error,
                        "start_offset": seg.start,
                        "end_offset": seg.end,
                        "page": seg.page,
                    }
                )
                for term in res.terms:
                    if term.get("status") == "unmatched" and term.get("source"):
                        self.store.add_term_candidate(
                            term["source"], source_lang, doc_id, res.report.segment_id
                        )
                done += 1
                self.store.update_document_progress(doc_id, done, len(segments), "running")
            self.store.update_document_progress(doc_id, done, len(segments), "completed")
        except Exception:
            traceback.print_exc()
            self.store.update_document_progress(doc_id, done, len(segments), "error")
        finally:
            with self._lock:
                self._jobs.pop(doc_id, None)

    # ---- review ----
    def review(self, segment_id: str, translation: str, reviewer: str, action: str, notes: str | None = None) -> dict | None:
        seg = self.store.review_segment(segment_id, translation, reviewer, action, notes)
        if seg and action == "approve":
            # Human-approved pairs become RAG translation memory immediately.
            self.memory.add(seg["id"], seg["source_text"], seg["translation"])
        return seg

    def retranslate_segment(self, segment_id: str) -> dict | None:
        seg = self.store.get_segment(segment_id)
        if not seg:
            return None
        doc = self.store.get_document(seg["document_id"])
        s = Segment(index=seg["idx"], text=seg["source_text"], start=seg["start_offset"] or 0,
                    end=seg["end_offset"] or 0, page=seg["page"])
        res = self.translator().translate_segment(s, doc["source_lang"], doc.get("variant"), doc["id"])
        import json

        self.store.upsert_segment(
            {
                "id": segment_id,
                "document_id": doc["id"],
                "idx": s.index,
                "source_text": s.text,
                "modern_text": res.modern_text,
                "translation": res.translation,
                "terms_json": json.dumps(res.terms, ensure_ascii=False),
                "notes": res.notes,
                "status": res.status,
                "report_json": json.dumps(res.report.to_dict(), ensure_ascii=False),
                "error": res.error,
                "start_offset": s.start,
                "end_offset": s.end,
                "page": s.page,
            }
        )
        return self.store.get_segment(segment_id)

    def record(self, doc_id: str) -> dict:
        return document_record(self.store, doc_id)
