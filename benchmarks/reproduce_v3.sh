#!/usr/bin/env bash
# Reproduce the validation/v3 correction round from a clean checkout.
#
#   ./benchmarks/reproduce_v3.sh mock   # offline suite + label checks (no model)
#   ./benchmarks/reproduce_v3.sh real   # + reproducibility re-runs (needs endpoint)
#
# Environment (real mode): TMTRANS_BASE_URL, TMTRANS_MODEL, TMTRANS_TEMPERATURE=0
#
# Exits non-zero if: the offline suite fails, any P0 condition is unmet
# (G6 != 1.0 on dosage-bearing rows, or G2 empty/copy rate > 0.05), or any
# G5 detection lacks a manual label.
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
p = Path("benchmarks/results/v3/g5_precision.csv")
if not p.exists():
    print("g5_precision.csv missing — hand-label all detections first"); sys.exit(1)
for r in csv.DictReader(open(p, encoding="utf-8")):
    if r["manual_label"] not in ("TP", "FP", "UNCLEAR"):
        print(f"unlabelled/invalid label: {r['dataset']} {r['detected_span']}"); sys.exit(1)
    labelled.add((r["dataset"], r["segment_id"].split(":")[-1], r["detected_span"]))

missing = 0
v2 = Path("benchmarks/results/v2")
for f in v2.glob("*_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl"):
    name = f.name.split("_mlx-community")[0]
    if name.startswith(("abl_", "repro_")):
        continue
    for line in f.read_text().splitlines():
        r = json.loads(line)
        for span in r["g5"].get("generated_names", []):
            if (name, str(r["idx"]), span) not in labelled:
                print(f"UNLABELLED: {name}:{r['idx']} {span!r}"); missing += 1
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
import os
model = os.environ["TMTRANS_MODEL"]
t = make_translator("real", model, extra_glossary="mespen")
for ds, pairs in [("glossary-adherence", load_mespen(30)), ("usda-dosage", load_usda(48))]:
    ch = []
    for run in (1, 2):
        set_seed(42)
        ch.append(run_dataset(t, pairs, ds, model, label=f"repro_v3_{ds}_run{run}")["chrf"])
    delta = abs(ch[0] - ch[1])
    print(f"[repro] {ds}: {ch} delta={delta}")
    if delta > 2.0:
        print(f"REPRODUCIBILITY FAIL: delta {delta} > 2.0 — v2 numbers must be retracted")
        sys.exit(1)
EOF
else
  echo "skipped (mock mode)"
fi

echo "== [4/4] P0 conditions =="
"$PY" - <<'EOF'
import csv, sys
from pathlib import Path

rows = list(csv.DictReader(open("benchmarks/results/v3/summary.csv", encoding="utf-8")))
p0_fail = False
for r in rows:
    ds = r["dataset"]
    n = int(r["n_segments"])
    empty = int(r.get("G2_empty_output_count") or 0)
    copy = int(r.get("G2_copy_output_count") or 0)
    g2_bad = (empty + copy) / n > 0.05
    # P0-1: G6 zero-tolerance on dosage-bearing rows
    dosage_bearing = ds in ("glossary-adherence", "usda-dosage")
    g6 = float(r["G6_numbers_pass_rate"]) if r["G6_numbers_pass_rate"] not in ("", "None") else 1.0
    g6_bad = dosage_bearing and g6 < 1.0
    tag = "PASS"
    if g2_bad or g6_bad:
        tag = "P0-FAIL"
        p0_fail = True
    print(f"  [{tag}] {ds}: G2_empty+copy={(empty+copy)/n:.2%} G6={g6}"
          f"{' (dosage-bearing, zero-tolerance)' if dosage_bearing else ''}")
if p0_fail:
    print("P0 conditions UNMET: deployment on dosage-bearing text is blocked (expected at v3)")
    sys.exit(1)
print("all P0 conditions met")
EOF

echo "reproduce_v3.sh: OK"