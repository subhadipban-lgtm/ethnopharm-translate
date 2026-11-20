"""Stage-2: run the 7 ablation conditions + reproducibility rerun, one at a
time, persisting each result before moving on. A server drop mid-run loses
only the in-flight condition. Then rebuilds the CSVs via collect_v2.

Usage: python benchmarks/stage2_ablations.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_v2 import OUT, load_gare, load_mespen, make_translator, run_dataset, set_seed

MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"

ABL_SPECS = [
    ("classical-zh", "baseline", dict(rag=True, binding=True, classical=True)),
    ("classical-zh", "rag_off", dict(rag=False, binding=True, classical=True)),
    ("classical-zh", "binding_off", dict(rag=True, binding=False, classical=True)),
    ("classical-zh", "classical_off", dict(rag=True, binding=True, classical=False)),
    ("glossary-adherence", "baseline", dict(rag=True, binding=True, classical=True)),
    ("glossary-adherence", "rag_off", dict(rag=False, binding=True, classical=True)),
    ("glossary-adherence", "binding_off", dict(rag=True, binding=False, classical=True)),
]


def main() -> None:
    set_seed()
    translator = make_translator("real", MODEL, extra_glossary="mespen")
    datasets = {"classical-zh": load_gare(), "glossary-adherence": load_mespen(30)}
    done = {}
    done_path = OUT / "ablations_raw.json"
    if done_path.exists():
        try:
            for r in json.loads(done_path.read_text()):
                done[f"{r['dataset']}/{r['notes']}"] = r
        except Exception:
            pass

    for name, cond, flags in ABL_SPECS:
        key = f"{name}/{cond}"
        if key in done:
            print(f"[stage2] skip {key} (already done)")
            continue
        print(f"[stage2] ablation {key} ...", flush=True)
        try:
            res = run_dataset(translator, datasets[name], name, MODEL,
                              label=f"abl_{name}_{cond}", **flags)
        except Exception:
            traceback.print_exc()
            print(f"[stage2] FAILED {key}; continuing", flush=True)
            continue
        res["ablation_condition"] = cond
        done[key] = {k: v for k, v in res.items() if not k.startswith("_")}
        done_path.write_text(json.dumps(list(done.values()), ensure_ascii=False, indent=2))
        print(f"    chrf={res['chrf']} G3={res['G3_glossary_pass_rate']} "
              f"G5={res['G5_generated']}/{res['G5_caught']}/{res['G5_escaped']}", flush=True)

    if not (OUT / "repro_classical-zh_run2_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl").exists():
        print("[stage2] reproducibility rerun (classical-zh) ...", flush=True)
        try:
            rerun = run_dataset(translator, datasets["classical-zh"], "classical-zh", MODEL,
                                label="repro_classical-zh_run2")
            print(f"    rerun chrf={rerun['chrf']}", flush=True)
        except Exception:
            traceback.print_exc()
    print("stage2 complete", flush=True)


if __name__ == "__main__":
    main()