"""Rebuild summary.csv / ablations.csv / summary.json from saved per-segment
JSONL files (no model calls). Used after run_v2.py runs so the expensive
dataset runs are never repeated just to rebuild tables.

Usage: python benchmarks/collect_v2.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from run_v2 import gate_rates, metrics_with_ci

OUT = Path(__file__).resolve().parent / "results" / "v2"

ABL_RE = re.compile(r"^abl_(.+?)_(baseline|rag_off|binding_off|classical_off)_")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(path: Path, dataset: str, model: str, condition: str = "") -> dict:
    rows = load_rows(path)
    gen = sum(r["g5"]["generated"] for r in rows)
    caught = sum(r["g5"]["caught"] for r in rows)
    escaped = sum(r["g5"]["escaped"] for r in rows)
    out = {
        "dataset": dataset, "model": model, "n_segments": len(rows),
        **metrics_with_ci(rows), **gate_rates(rows),
        "G5_generated": gen, "G5_caught": caught, "G5_escaped": escaped,
        "G5_escape_rate": round(escaped / gen, 4) if gen else "n/a",
        "notes": condition, "_file": path.name,
    }
    return out


def main() -> None:
    model_tag = None
    main_rows, abl_rows = [], []
    for path in sorted(OUT.glob("*.jsonl")):
        m = ABL_RE.match(path.name)
        if m:
            abl_rows.append((path, m.group(1), m.group(2)))
            continue
        if path.name.startswith("repro_"):
            continue
        if model_tag is None and "_mlx-community" in path.name:
            model_tag = path.name.split("_", 1)[1].rsplit(".jsonl", 1)[0]
        dataset = path.name.split(f"_{model_tag}")[0] if model_tag else path.stem
        main_rows.append((path, dataset, "main"))

    model = model_tag or "unknown"
    summary = [summarize(p, ds, model) for p, ds, _ in main_rows]
    ablations = [summarize(p, ds, model, cond) for p, ds, cond in abl_rows]

    # reproducibility delta from the rerun JSONL if present
    repro = {"dataset": "classical-zh", "note": "no rerun file"}
    run1 = next((s for s in summary if s["dataset"] == "classical-zh"), None)
    rerun_path = OUT / f"repro_classical-zh_run2_{model}.jsonl"
    if run1 and rerun_path.exists():
        run2 = summarize(rerun_path, "classical-zh", model)
        repro = {"dataset": "classical-zh", "run1_chrf": run1["chrf"],
                 "run2_chrf": run2["chrf"],
                 "abs_delta": round(abs(run2["chrf"] - run1["chrf"]), 2)}

    cols = ["dataset", "model", "n_segments", "chrf", "chrf_ci", "bleu", "bleu_ci", "ter",
            "G3_glossary_pass_rate", "G4_untranslated_pass_rate",
            "G5_generated", "G5_caught", "G5_escaped", "G5_escape_rate",
            "G6_numbers_pass_rate", "G7_length_pass_rate", "notes"]

    def flat(r):
        return {
            "dataset": r["dataset"], "model": r["model"], "n_segments": r["n_segments"],
            "chrf": r["chrf"], "chrf_ci": f"[{r['chrf_ci'][0]},{r['chrf_ci'][1]}]",
            "bleu": r["bleu"], "bleu_ci": f"[{r['bleu_ci'][0]},{r['bleu_ci'][1]}]",
            "ter": r["ter"],
            "G3_glossary_pass_rate": r["G3_glossary_pass_rate"],
            "G4_untranslated_pass_rate": r["G4_untranslated_pass_rate"],
            "G5_generated": r["G5_generated"], "G5_caught": r["G5_caught"],
            "G5_escaped": r["G5_escaped"], "G5_escape_rate": r["G5_escape_rate"],
            "G6_numbers_pass_rate": r["G6_numbers_pass_rate"],
            "G7_length_pass_rate": r["G7_length_pass_rate"], "notes": r["notes"],
        }

    with open(OUT / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in summary:
            w.writerow(flat(r))
    with open(OUT / "ablations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in ablations:
            w.writerow(flat(r))
    with open(OUT / "summary.json", "w", encoding="utf-8") as fh:
        json.dump({"model": model, "seed": 42, "n_boot": 1000,
                   "summary": [{k: v for k, v in r.items() if k != "_file"} for r in summary],
                   "ablations": [{k: v for k, v in r.items() if k != "_file"} for r in ablations],
                   "reproducibility": repro}, fh, ensure_ascii=False, indent=2)

    print(f"summary.csv: {len(summary)} rows; ablations.csv: {len(ablations)} rows")
    for r in summary:
        print(f"  {r['dataset']:24s} chrf={r['chrf']:5.2f} G5={r['G5_generated']}/{r['G5_caught']}/{r['G5_escaped']}")
    for r in ablations:
        print(f"  [abl] {r['dataset']}/{r['notes']:12s} chrf={r['chrf']:5.2f} G3={r['G3_glossary_pass_rate']}")
    print(f"reproducibility: {repro}")


if __name__ == "__main__":
    main()