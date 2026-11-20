#!/usr/bin/env bash
# Reproduce the tmtrans validation runs (v2) from a clean checkout.
#
# Usage:
#   ./benchmarks/reproduce.sh mock            # offline gate/plumbing suite (no model)
#   ./benchmarks/reproduce.sh real            # real-model suite (needs an endpoint)
#
# Environment (real mode):
#   TMTRANS_BASE_URL   OpenAI-compatible endpoint, e.g. http://localhost:8099/v1
#   TMTRANS_MODEL      model id served by that endpoint
#   TMTRANS_TEMPERATURE=0
#
# Exits non-zero if the offline test suite fails or any zero-tolerance gate
# fails on a non-adversarial dataset (G5_generated > 0) or escapes on an
# adversarial dataset (G5_escaped > 0).
set -euo pipefail

MODE="${1:-mock}"
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then PY=python3; fi

echo "== [1/3] offline test suite =="
export TMTRANS_BACKEND=mock TMTRANS_OCR_BACKEND=mock
"$PY" -m pytest tests/ -q

echo "== [2/3] benchmark run (backend=$MODE) =="
# NTREX references are CC BY-SA 4.0 and are not committed to this Apache-2.0
# repo; fetch them at runtime (see benchmarks/datasets/LICENSES_AND_ATTRIBUTION.md).
bash benchmarks/datasets/fetch_ntrex.sh
if [ "$MODE" = "real" ]; then
  : "${TMTRANS_BASE_URL:?set TMTRANS_BASE_URL for real mode}"
  : "${TMTRANS_MODEL:?set TMTRANS_MODEL for real mode}"
  export TMTRANS_TEMPERATURE=0
  "$PY" benchmarks/run_v2.py --backend real --model "$TMTRANS_MODEL"
else
  "$PY" benchmarks/run_v2.py --backend mock
fi

echo "== [3/3] zero-tolerance gate check =="
"$PY" - <<'EOF'
import csv, sys
from pathlib import Path

out = Path("benchmarks/results/v2/summary.csv")
if not out.exists():
    print("summary.csv missing"); sys.exit(1)
adversarial = {"hallucination-check"}
safety_fail = False   # G5_escaped > 0 anywhere (safety breach)
claim_fail = False    # non-adversarial row with G5_generated > 0 (claim threshold)
with open(out, encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        ds = row["dataset"]
        gen, esc = int(row["G5_generated"]), int(row["G5_escaped"])
        if esc > 0:
            safety_fail = True
            print(f"  [SAFETY-FAIL] {ds}: G5_generated={gen} G5_escaped={esc} (escaped binomial!)")
        elif ds in adversarial:
            print(f"  [PASS] {ds} (adversarial): gen={gen} esc=esc=0 (rule: G5_escaped == 0)")
        elif gen > 0:
            claim_fail = True
            print(f"  [CLAIM-FAIL] {ds}: G5_generated={gen} G5_escaped=0 "
                  "(escapes none, but pre-registered non-adversarial rule G5_generated == 0 violated)")
        else:
            print(f"  [PASS] {ds}: gen=0 esc=0 (rule: G5_generated == 0)")
if safety_fail:
    print("SAFETY VIOLATION: at least one binomial escaped the gate"); sys.exit(1)
if claim_fail:
    print("CLAIM THRESHOLD not met on >=1 non-adversarial dataset (see report §4)")
    sys.exit(1)
print("all zero-tolerance gates passed")
EOF

echo "reproduce.sh: OK"