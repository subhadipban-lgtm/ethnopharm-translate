"""Command-line interface for tmtrans.

Examples:
  tmtrans serve --port 8765
  tmtrans translate input.txt --lang lzh --out outputs/
  tmtrans glossary import data/dictionary/seed_tcm.csv
  tmtrans export <doc_id> --fmt jsonl --approved-only
  tmtrans doctor
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .backend import BackendConfig, OpenAICompatBackend, get_backend
from .db import Store
from .dictionary import Glossary
from .export import export_csv, export_full_json, export_jsonl, export_text, export_xlsx
from .rag import TranslationMemoryIndex
from .segment import ingest_file
from .translate import Translator

DEFAULT_DICTS = ["data/dictionary/seed_tcm.csv", "data/dictionary/seed_ayurveda.csv",
                 "data/dictionary/seed_seasian.csv"]


def _glossary(paths: list[str]) -> Glossary:
    g = Glossary()
    for p in paths:
        if Path(p).exists():
            g.load_csv(p)
    return g


def cmd_serve(args) -> None:
    import uvicorn

    from .server import create_app

    app = create_app(dictionary_paths=args.dictionary, db_path=args.db)
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_translate(args) -> None:
    glossary = _glossary(args.dictionary)
    translator = Translator(backend=get_backend(), glossary=glossary, memory=TranslationMemoryIndex())
    segments = ingest_file(args.input)
    print(f"Translating {len(segments)} segments from {args.input} (lang={args.lang})…")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = Store(str(out_dir / "tmtrans-cli.db"))
    doc_id = store.create_document(Path(args.input).name, args.lang, args.variant, source_file=args.input)
    counts = {"auto_pass": 0, "needs_review": 0, "failed": 0}
    import json

    for i, seg in enumerate(segments, 1):
        res = translator.translate_segment(seg, args.lang, args.variant, doc_id)
        store.upsert_segment({
            "id": res.report.segment_id, "document_id": doc_id, "idx": seg.index,
            "source_text": seg.text, "modern_text": res.modern_text, "translation": res.translation,
            "terms_json": json.dumps(res.terms, ensure_ascii=False), "notes": res.notes,
            "status": res.status, "report_json": json.dumps(res.report.to_dict(), ensure_ascii=False),
            "error": res.error, "start_offset": seg.start, "end_offset": seg.end, "page": seg.page,
        })
        counts[res.status] = counts.get(res.status, 0) + 1
        print(f"  [{i}/{len(segments)}] {res.status}: {seg.text[:50]!r}")
    export_jsonl(store, doc_id, out_dir / f"{doc_id}.jsonl")
    export_csv(store, doc_id, out_dir / f"{doc_id}.csv")
    export_full_json(store, doc_id, out_dir / f"{doc_id}.json")
    print(f"Done: {counts}. Document id {doc_id}. Bilingual export in {out_dir}/")
    print("Review needs_review/failed segments in the web UI (tmtrans serve) before final export.")


def cmd_ocr(args) -> None:
    from pathlib import Path as _Path

    from .ocr import (
        OCRBackendConfig,
        get_ocr_backend,
        ocr_folder,
        write_jsonl,
    )
    from .segment import ingest_file

    ocr_cfg = OCRBackendConfig.from_env(
        fallback_base_url="", fallback_api_key=""
    )
    # fall back to the translation endpoint vars when no OCR-specific ones set
    import os

    if not ocr_cfg.base_url:
        ocr_cfg.base_url = os.environ.get("TMTRANS_BASE_URL", "")
    backend = get_ocr_backend(ocr_cfg)
    out = _Path(args.out) if args.out else _Path("outputs") / f"ocr-{int(time.time())}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    pages = ocr_folder(
        args.input, args.lang, backend,
        reading_order=args.reading_order, iast=args.iast,
        line_segmentation=args.line_segmentation,
        progress=lambda i, n, name: print(f"  [{i}/{n}] {name}"),
    )
    write_jsonl(pages, out, args.lang, args.reading_order, args.iast)
    print(f"OCR complete: {len(pages)} pages -> {out}")
    if not args.translate:
        print(f"Next: tmtrans translate {out} --lang {args.lang}"
              + (f" --variant {args.variant}" if args.variant else ""))
        return
    # Chain straight into translation (sequential staging on one GPU).
    args.input, args.out = str(out), str(out.parent)
    cmd_translate(args)


def cmd_export(args) -> None:
    store = Store(args.db)
    out = Path(args.out or f"outputs/{args.doc_id}.{args.fmt}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.fmt == "jsonl":
        n = export_jsonl(store, args.doc_id, out, args.approved_only)
    elif args.fmt == "csv":
        n = export_csv(store, args.doc_id, out, args.approved_only)
    elif args.fmt == "xlsx":
        n = export_xlsx(store, args.doc_id, out)
    elif args.fmt == "txt":
        n = export_text(store, args.doc_id, out, args.approved_only)
    else:
        export_full_json(store, args.doc_id, out)
        n = -1
    print(f"Exported {n if n >= 0 else 'document'} to {out}")


def cmd_glossary(args) -> None:
    if args.action == "import":
        g = Glossary()
        n = g.load_csv(args.file)
        # Merge into the canonical seed file for persistence.
        target = Path("data/dictionary/custom.csv")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(args.file, encoding="utf-8-sig") as src, open(target, "a", encoding="utf-8") as dst:
            lines = src.read().splitlines()
            if target.exists() and target.stat().st_size > 0:
                lines = lines[1:]
            dst.write("\n".join(lines) + "\n")
        print(f"Imported {n} entries; appended to {target}")
    elif args.action == "stats":
        print(_glossary(args.dictionary).stats())
    elif args.action == "export":
        Path(args.out).write_text(_glossary(args.dictionary).to_csv(), encoding="utf-8")
        print(f"Wrote {args.out}")


def cmd_doctor(args) -> None:
    cfg = BackendConfig.from_env()
    print(f"Backend: {cfg.kind}  model={cfg.model}  base_url={cfg.base_url}")
    backend = get_backend(cfg)
    if isinstance(backend, OpenAICompatBackend):
        print("Endpoint health:", backend.health())
    else:
        print("Mock backend active (set TMTRANS_BACKEND=openai_compat for a real model).")
    g = _glossary(args.dictionary)
    print("Glossary:", g.stats())
    print("Python:", sys.version.split()[0])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tmtrans", description=__doc__)
    p.add_argument("--db", default="data/tmtrans.db")
    p.add_argument("--dictionary", action="append", default=None,
                   help="dictionary CSV path (repeatable); defaults to data/dictionary seeds")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the local web workbench")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    t = sub.add_parser("translate", help="translate a file from the command line")
    t.add_argument("input")
    t.add_argument("--lang", default="zh")
    t.add_argument("--variant", default=None, choices=["classical", "modern"])
    t.add_argument("--out", default="outputs")
    t.set_defaults(func=cmd_translate)

    o = sub.add_parser("ocr", help="OCR a folder of manuscript scans to JSONL (then translate)")
    o.add_argument("input", help="folder of images (.png/.jpg/.tif/...)")
    o.add_argument("--lang", default="lzh")
    o.add_argument("--variant", default=None, choices=["classical", "modern"])
    o.add_argument("--reading-order", default="auto", choices=["auto", "rtl-columns", "ltr-lines"])
    o.add_argument("--iast", action="store_true", help="emit IAST transliteration (Sanskrit)")
    o.add_argument("--line-segmentation", default="none", choices=["none", "surya"],
                   help="crop lines first via surya (palm leaf / Samut Khoi)")
    o.add_argument("--out", default=None, help="JSONL path (default outputs/ocr-<ts>.jsonl)")
    o.add_argument("--translate", action="store_true",
                   help="continue straight into translation after OCR")
    o.set_defaults(func=cmd_ocr)

    e = sub.add_parser("export", help="export a document from the database")
    e.add_argument("doc_id")
    e.add_argument("--fmt", default="jsonl", choices=["jsonl", "json", "csv", "xlsx", "txt"])
    e.add_argument("--approved-only", action="store_true")
    e.add_argument("--out", default=None)
    e.set_defaults(func=cmd_export)

    g = sub.add_parser("glossary", help="manage the bilingual dictionary")
    g.add_argument("action", choices=["import", "stats", "export"])
    g.add_argument("file", nargs="?")
    g.add_argument("--out", default="outputs/glossary.csv")
    g.set_defaults(func=cmd_glossary)

    d = sub.add_parser("doctor", help="check backend connectivity and dictionary")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dictionary is None:
        args.dictionary = DEFAULT_DICTS + ["data/dictionary/custom.csv"]
    args.func(args)


if __name__ == "__main__":
    main()
