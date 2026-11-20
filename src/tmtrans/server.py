"""FastAPI server for the local translation workbench.

Run:  tmtrans serve --host 127.0.0.1 --port 8765
Then open http://127.0.0.1:8765 in a browser.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, export
from .lang import supported_source_codes
from .service import Service

STATIC_DIR = Path(__file__).parent / "web" / "static"


class TextSubmission(BaseModel):
    title: str
    text: str
    source_lang: str = "zh"
    variant: str | None = None
    tradition: str | None = None


class ReviewSubmission(BaseModel):
    translation: str
    reviewer: str = "local"
    action: str = "approve"  # approve | reject
    notes: str | None = None


class GlossaryEntrySubmission(BaseModel):
    entry_id: str
    category: str = "herb"
    source_lang: str
    source_form: str
    variants: list[str] = []
    english: str = ""
    binomial: str = ""
    inchikey: str = ""
    family: str = ""
    tradition: str = ""
    pharmacopoeia: str = ""
    notes: str = ""


def create_app(service: Service | None = None, dictionary_paths: list[str] | None = None,
               db_path: str = "data/tmtrans.db") -> FastAPI:
    svc = service or Service(db_path=db_path, dictionary_paths=dictionary_paths or [])
    app = FastAPI(title="tmtrans", version=__version__)
    app.state.service = svc

    # ---- UI ----
    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ---- health & metadata ----
    @app.get("/api/health")
    def health() -> dict:
        from .backend import OpenAICompatBackend

        backend = {"kind": svc.backend_config.kind, "model": svc.backend_config.model}
        if isinstance(svc.backend, OpenAICompatBackend):
            backend["endpoint"] = svc.backend.health()
        return {"version": __version__, "backend": backend, "glossary": svc.glossary.stats()}

    @app.get("/api/languages")
    def languages() -> dict:
        return {"source_codes": supported_source_codes()}

    # ---- documents ----
    @app.get("/api/documents")
    def list_documents() -> list[dict]:
        return svc.store.list_documents()

    @app.post("/api/documents/text")
    def submit_text(sub: TextSubmission) -> dict:
        doc_id = svc.submit_text(sub.title, sub.text, sub.source_lang, sub.variant, sub.tradition)
        return {"document_id": doc_id}

    @app.post("/api/documents/file")
    async def submit_file(
        file: UploadFile = File(...),
        source_lang: str = Form("zh"),
        variant: str | None = Form(None),
        tradition: str | None = Form(None),
        title: str | None = Form(None),
    ) -> dict:
        suffix = Path(file.filename or "upload.txt").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        doc_id = svc.submit_file(tmp_path, title or file.filename, source_lang, variant, tradition)
        return {"document_id": doc_id}

    @app.get("/api/documents/{doc_id}")
    def get_document(doc_id: str) -> dict:
        doc = svc.store.get_document(doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        return doc

    @app.get("/api/documents/{doc_id}/segments")
    def get_segments(doc_id: str, status: str | None = None) -> list[dict]:
        return svc.store.list_segments(doc_id, status)

    @app.get("/api/documents/{doc_id}/record")
    def get_record(doc_id: str) -> dict:
        try:
            return svc.record(doc_id)
        except KeyError:
            raise HTTPException(404, "document not found")

    # ---- review ----
    @app.post("/api/segments/{segment_id}/review")
    def review(segment_id: str, sub: ReviewSubmission) -> dict:
        seg = svc.review(segment_id, sub.translation, sub.reviewer, sub.action, sub.notes)
        if not seg:
            raise HTTPException(404, "segment not found")
        return seg

    @app.post("/api/segments/{segment_id}/retranslate")
    def retranslate(segment_id: str) -> dict:
        seg = svc.retranslate_segment(segment_id)
        if not seg:
            raise HTTPException(404, "segment not found")
        return seg

    # ---- glossary ----
    @app.get("/api/glossary")
    def glossary_csv() -> Response:
        return Response(svc.glossary.to_csv(), media_type="text/csv")

    @app.get("/api/glossary/search")
    def glossary_search(q: str) -> list[dict]:
        entry = svc.glossary.exact(q)
        if entry:
            return [vars(entry)]
        hits = svc.glossary.find_in_text(q, "zh") + svc.glossary.find_in_text(q, "sa")
        seen, out = set(), []
        for e in hits:
            if e.entry_id not in seen:
                seen.add(e.entry_id)
                out.append(vars(e))
        return out

    @app.post("/api/glossary")
    def add_glossary_entry(sub: GlossaryEntrySubmission) -> dict:
        from .dictionary import DictEntry

        svc.glossary.add(DictEntry(**sub.model_dump()))
        return {"added": sub.entry_id, "stats": svc.glossary.stats()}

    @app.get("/api/term-candidates")
    def term_candidates(state: str = "open") -> list[dict]:
        return svc.store.list_term_candidates(state)

    # ---- export ----
    @app.get("/api/documents/{doc_id}/export/{fmt}")
    def export_document(doc_id: str, fmt: str, approved_only: bool = False) -> Response:
        out_dir = Path("outputs")
        out_dir.mkdir(exist_ok=True)
        path = out_dir / f"{doc_id}.{fmt if fmt != 'jsonl' else 'jsonl'}"
        if fmt == "jsonl":
            export.export_jsonl(svc.store, doc_id, path, approved_only)
        elif fmt == "json":
            export.export_full_json(svc.store, doc_id, path)
        elif fmt == "csv":
            export.export_csv(svc.store, doc_id, path, approved_only)
        elif fmt == "xlsx":
            export.export_xlsx(svc.store, doc_id, path)
        elif fmt == "txt":
            export.export_text(svc.store, doc_id, path, approved_only)
        else:
            raise HTTPException(400, f"unsupported format {fmt}")
        return FileResponse(path, filename=f"{doc_id}.{fmt}")

    @app.exception_handler(Exception)
    async def unhandled(request, exc):  # pragma: no cover
        return JSONResponse({"error": str(exc)}, status_code=500)

    return app
