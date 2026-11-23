"""FLORES-200 devtest evaluation for tmtrans.

Human-anchored, reference-based, single command. Fetches FLORES-200 via
fetch_flores.sh (not committed). Computes chrF++ / BLEU / TER against
eng_Latn source with sacrebleu.

Usage:
  python benchmarks/run_flores.py --model <id> --directions eng_Latn->tha_Thai,eng_Latn->zho_Hans \
      --limit 1012 --out benchmarks/results/flores/<tag>.json
"""
import argparse, json, os, sys, time
from pathlib import Path

import sacrebleu

ROOT = Path(__file__).resolve().parent.parent
FLORES = ROOT / "benchmarks" / "datasets" / "flores200_dataset" / "devtest"

def load_pair(src: str, tgt: str):
    s = (FLORES / f"{src}.devtest").read_text(encoding="utf-8").splitlines()
    t = (FLORES / f"{tgt}.devtest").read_text(encoding="utf-8").splitlines()
    assert len(s) == len(t), (len(s), len(t))
    return s, t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="openai_compat", choices=["openai_compat", "mock", "nllb"])
    ap.add_argument("--src-lang", default=None, help="FLORES src code for nllb, e.g. eng_Latn")
    ap.add_argument("--tgt-lang", default=None, help="FLORES tgt code; default comes from direction")
    ap.add_argument("--model", required=True)
    ap.add_argument("--directions", default="eng_Latn->tha_Thai,eng_Latn->zho_Hans")
    ap.add_argument("--limit", type=int, default=1012)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not FLORES.exists():
        sys.exit("FLORES-200 not found. Run: bash benchmarks/datasets/fetch_flores.sh")

    if args.backend == "mock":
        from tmtrans.backend import MockBackend
        backend = MockBackend()
    elif args.backend == "nllb":
        from tmtrans.backend import BackendConfig, NLLBBackend
        cfg = BackendConfig.from_env()
        cfg.nllb_model = args.model
        cfg.src_lang = args.src_lang or "eng_Latn"
        cfg.temperature = 0.0
        backend = NLLBBackend(cfg)
    else:
        from tmtrans.backend import BackendConfig, OpenAICompatBackend
        cfg = BackendConfig.from_env()
        if args.model:
            cfg.model = args.model
        cfg.temperature = 0.0
        backend = OpenAICompatBackend(cfg)

    results = []
    LANG = {
        "tha_Thai": "Thai",
        "zho_Hans": "Simplified Chinese",
        "zho_Hant": "Traditional Chinese",
        "khm_Khmr": "Khmer",
        "lao_Laoo": "Lao",
        "eng_Latn": "English",
        "hin_Deva": "Hindi",
        "jpn_Jpan": "Japanese",
        "kor_Hang": "Korean",
        "vie_Latn": "Vietnamese",
    }
    for direction in args.directions.split(","):
        src, tgt = direction.split("->")
        if args.backend == "nllb":
            backend.cfg.tgt_lang = args.tgt_lang or tgt
            backend.cfg.src_lang = args.src_lang or src
        srcs, refs = load_pair(src, tgt)
        srcs, refs = srcs[:args.limit], refs[:args.limit]
        tgt_name = LANG.get(tgt, tgt)
        preds = []
        t0 = time.time()
        for i, s in enumerate(srcs):
            msgs = [
                {"role": "system",
                 "content": (f"You are a professional translator. Translate the user's "
                             f"text into {tgt_name}. Output only the {tgt_name} translation, "
                             f"no commentary, no romanization, no explanation.")},
                {"role": "user", "content": s},
            ]
            hyp = backend.complete(msgs)
            if args.backend == "nllb":
                # NLLB backend returns the tmtrans JSON envelope; unwrap it.
                try:
                    hyp = json.loads(hyp).get("translation", "")
                except Exception:
                    pass
            preds.append(hyp.strip())
            if (i + 1) % 50 == 0:
                print(f"  {direction} {i+1}/{len(srcs)} ({time.time()-t0:.0f}s)", flush=True)
        chrf = sacrebleu.corpus_chrf(preds, [refs], word_order=2).score
        bleu = sacrebleu.corpus_bleu(preds, [refs], tokenize="13a").score
        try:
            from sacrebleu.metrics import TER
            ter = TER().corpus_score(preds, [refs]).score
        except Exception:
            ter = None
        results.append({
            "direction": direction, "n": len(srcs),
            "chrf_pp": round(chrf, 2),
            "bleu_13a": round(bleu, 2),
            "ter": (round(ter, 2) if ter is not None else None),
            "model": args.model,
        })
        print(f"DONE {direction}: CHRF++={chrf:.2f} BLEU={bleu:.2f} TER={ter}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
