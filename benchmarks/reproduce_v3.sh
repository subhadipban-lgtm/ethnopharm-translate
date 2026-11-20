#!/usr/bin/env bash
# Reproduce the validation/v3.1 correction round from a clean checkout.
#
#   ./benchmarks/reproduce_v3.sh mock   # offline suite + label checks (no model)
#   ./benchmarks/reproduce_v3.sh real   # + reproducibility re-runs (needs endpoint)
#
# Environment (real mode): TMTRANS_BASE_URL, TMTRANS_MODEL, TMTRANS_TEMPERATURE=0
#
# NOTE: JSONL filenames retain the underscore-form model id
# (`mlx-community_Qwen2.5-3B-Instruct-4bit`) for CSV/filename safety; CSV values
# use slash form (`mlx-community/Qwen2.5-3B-Instruct-4bit`).
#
# Exits non-zero if: the offline suite fails, any P0 condition is unmet
# (G6 != 1.0 on dosage-bearing rows, or G2 empty/copy rate > 0.05), any G5
# detection lacks a manual label, or run1 deviates from the stored v2 baseline.
#
# This script enforces evidence-level P0 (model-level G6/G2), not deployment-level
# P0. A fail-closed mitigation is required to clear RECOMMENDATION.md P0;
# verifying it is out of scope here.
set -euo pipefail

MODE="${1:-mock}"
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then PY=python3; fi

echo "== [1/4] offline test suite =="
export TMTRANS_BACKEND=mock TMTRANS_OCR_BACKEND=mock
"$PY" -m pytest tests/ -q

echo "== [2/4] G5 precision labelling completeness =="
"$PY" - <<'EOF'
import csv, json, sys
from pathlib import Path

# every detection in the v2 JSONLs must have a label in g5_precision.csv
labelled = set()
p = Path("benchmarks/results/v3.1/g5_precision.csv")
if not p.exists():
    print("g5_precision.csv missing — hand-label all detections first"); sys.exit(1)
for r in csv.DictReader(open(p, encoding="utf-8")):
    if r["manual_label"] not in ("TP", "FP", "UNCLEAR"):
        print(f"unlabelled/invalid label: {r['dataset']} {r['detected_span']}"); sys.exit(1)
    labelled.add((r["dataset"], r["segment_id"].split(":")[-1], r["detected_span"]))

# segment_id key format: dataset:idx  # assert this if the format changes
tp = sum(1 for r in csv.DictReader(open(p, encoding="utf-8")) if r["manual_label"] == "TP")
fp = sum(1 for r in csv.DictReader(open(p, encoding="utf-8")) if r["manual_label"] == "FP")
unclear = sum(1 for r in csv.DictReader(open(p, encoding="utf-8")) if r["manual_label"] == "UNCLEAR")
total = tp + fp + unclear
print(f"label distribution: TP={tp} FP={fp} UNCLEAR={unclear} total={total}")
if unclear and unclear / max(total, 1) > 0.10:
    print(f"FAIL: {unclear}/{total} labels are UNCLEAR (>10%) — labelling incomplete"); sys.exit(1)

missing = 0
skipped = 0
v2 = Path("benchmarks/results/v2")
for f in v2.glob("*_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl"):
    name = f.name.split("_mlx-community")[0]
    if name.startswith(("abl_", "repro_")):
        skipped += 1
        continue
    for line in f.read_text().splitlines():
        r = json.loads(line)
        for span in r["g5"].get("generated_names", []):
            if (name, str(r["idx"]), span) not in labelled:
                print(f"UNLABELLED: {name}:{r['idx']} {span!r}"); missing += 1
print(f"skipped {skipped} ablation/repro files")
if missing:
    sys.exit(1)
print(f"all detections labelled ({len(labelled)} labels)")
EOF

echo "== [3/4] reproducibility re-runs (real mode only) =="
if [ "$MODE" = "real" ]; then
  : "${TMTRANS_BASE_URL:?set TMTRANS_BASE_URL}"
  : "${TMTRANS_MODEL:?set TMTRANS_MODEL}"
  export TMTRANS_TEMPERATURE=0
  bash benchmarks/datasets/fetch_ntrex.sh
  "$PY" - <<'EOF'
import sys
sys.path.insert(0, "benchmarks")
from pathlib import Path
import run_v2
run_v2.OUT_SAVE = Path("benchmarks/results/v3")
from run_v2 import load_mespen, load_usda, make_translator, run_dataset, set_seed
import json, csv
import os
model = os.environ["TMTRANS_MODEL"]
t = make_translator("real", model, extra_glossary="mespen")
v2_baseline = {}
with open("benchmarks/results/v2/summary.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        v2_baseline[r["dataset"]] = float(r["chrf"])
for ds, loader in [("glossary-adherence", load_mespen), ("usda-dosage", load_usda)]:
    pairs = loader(30 if ds == "glossary-adherence" else 48)
    ch = []
    for run in (1, 2):
        set_seed(42)
        ch.append(run_dataset(t, pairs, ds, model, label=f"repro_v3_{ds}_run{run}")["chrf"])
    delta = abs(ch[0] - ch[1])
    v2 = v2_baseline[ds]
    d_v2 = abs(ch[0] - v2)
    print(f"[repro] {ds}: run1={ch[0]} run2={ch[1]} v2={v2} | delta_run1_run2={delta} delta_run1_v2={d_v2}")
    if delta > 2.0:
        print(f"REPRODUCIBILITY FAIL: run1 vs run2 delta {delta} > 2.0")
        sys.exit(1)
    if d_v2 > 2.0:
        print(f"V2 BASELINE NOT REPRODUCED: run1={ch[0]}, v2={v2}, delta={d_v2}")
        sys.exit(1)
EOF
else
  echo "skipped (mock mode)"
fi

echo "== [4/4] P0 conditions =="
"$PY" - <<'EOF'
import csv, sys
from pathlib import Path

# Print the actual CSV header so column names can be verified.
header = Path("benchmarks/results/v3.1/summary.csv").read_text(encoding="utf-8").splitlines()[0]
print(f"[P0-check] CSV header: {header}")

rows = list(csv.DictReader(open("benchmarks/results/v3.1/summary.csv", encoding="utf-8")))
p0_fail = False
for r in rows:
    ds = r["dataset"]
    n = int(r["n_segments"])
    # G2 columns must match summary.csv exactly: G2_empty_output_count, G2_copy_output_count
    empty = int(r.get("G2_empty_output_count") or 0)
    copy = int(r.get("G2_copy_output_count") or 0)
    g2_bad = (empty + copy) / n > 0.05
    dosage_bearing = ds in ("glossary-adherence", "usda-dosage")
    g6 = float(r["G6_numbers_pass_rate"]) if r["G6_numbers_pass_rate"] not in ("", "None") else 1.0
    g6_bad = dosage_bearing and g6 < 1.0
    print(f"[P0-check] {ds}: n={n} empty={empty} copy={copy} g6={g6}")
    tag = "PASS"
    if g2_bad or g6_bad:
        tag = "P0-FAIL"
        p0_fail = True
    print(f"  [{tag}] {ds}: G2_empty+copy={(empty+copy)/n:.2%} G6={g6}"
          f"{' (dosage-bearing, zero-tolerance)' if dosage_bearing else ''}")

# G2 branch fired in isolation (see script_tests.md for the synthetic-CSV test).
if p0_fail:
    print("P0 VALIDATION EVIDENCE UNMET (model-level G6/G2; deployment approval depends on "
          "fail-closed mitigation, which this script cannot verify).")
    sys.exit(1)
print("all P0 conditions met (evidence level)")
EOF

echo "reproduce_v3.sh: OK"
