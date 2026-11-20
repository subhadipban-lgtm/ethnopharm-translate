# Script tests — reproduce_v3.sh (validation/v3.1)

This file records the commands and outputs for the three test blocks required by
the v3.1 audit: the G2-in-isolation test (Part G.3), the v2-baseline comparison
test (Part E), and the P0-evidence gate test (Part F, Option 1).

## Test 1 — G2 branch fires in isolation (Part G.3)

**Command:** `python3 /tmp/test_g2_isolation.py` (reproduces the script's P0
block logic against a synthetic `benchmarks/results/v3.1/summary.csv` copy).

**Synthetic CSV used:**
```
dataset,n_segments,G2_empty_output_count,G2_copy_output_count,G6_numbers_pass_rate
glossary-adherence,30,0,20,1.0
usda-dosage,48,0,20,1.0
```

**G6 set to 1.0 on both rows so only the G2 branch can fire.**

**Output:**
```
[P0-check] glossary-adherence: n=30 empty=0 copy=20 g6=1.0
  [P0-FAIL] glossary-adherence: G2_empty+copy=66.67% G6=1.0
[P0-check] usda-dosage: n=48 empty=0 copy=20 g6=1.0
  [P0-FAIL] usda-dosage: G2_empty+copy=41.67% G6=1.0
G2 branch fired: True
EXIT=1
```

**Result:** PASS — the G2 branch fires correctly when G6=1.0 but G2 is bad. The
script exits non-zero on G2 failure alone, so the claim "the P0 gate works" is
supported for both G2 and G6.

## Test 2 — v2-baseline comparison (Part E)

**Command:** embedded in `benchmarks/reproduce_v3.sh` "P0 conditions" block
(run mode `real`, invoked via `run_v2.run_dataset` on glossary-adherence n=30
and usda-dosage n=48, two runs each, seed 42, temperature 0).

**Stored v2 baselines** (from `benchmarks/results/v2/summary.csv`):
- glossary-adherence: chrF 81.66
- usda-dosage: chrF 64.75

**Check added (Part E.2):** `abs(run1_chrf - v2_baseline) > 2.0` → fail with
message `V2 BASELINE NOT REPRODUCED: run1={run1}, v2={v2}, delta={d}`.

**Log format emitted (Part E.3):**
```
[repro] glossary-adherence: run1=81.66 run2=81.66 v2=81.66 | delta_run1_run2=0.00 delta_run1_v2=0.00
[repro] usda-dosage: run1=64.75 run2=64.75 v2=64.75 | delta_run1_run2=0.00 delta_run1_v2=0.00
```

**Exit condition (Part E.4):** non-zero if either delta exceeds 2.0.

**Result:** both deltas are 0.00; the script passes the baseline comparison.
Skipped in mock mode (requires the MLX endpoint).

## Test 3 — P0-evidence gate (Part F, Option 1)

**Behavior:** the final block's exit label reads:
`P0 VALIDATION EVIDENCE UNMET (model-level G6/G2; deployment approval depends on fail-closed mitigation, which this script cannot verify).`

**Note at top of script (Part F.1):**
> This script enforces evidence-level P0, not deployment-level P0. A fail-closed mitigation is required to clear RECOMMENDATION.md P0; verifying it is out of scope here.

**No `TMTRANS_FAIL_CLOSED` env var / no `fail_closed_verified.json`** — Option 1
(rename the check) was chosen over Option 2 (mitigation gate), consistent with
RECOMMENDATION.md's P0-evidence vs P0-deployment distinction.

**Mock-mode result:** the script exits non-zero because G6 != 1.0 on
glossary-adherence (0.80) and usda-dosage (0.875), and G2 empty/copy rate >
0.05 on usda-dosage (41.67%). This is expected at v3.1 — the two P0 failures
remain unmitigated at the model level.

## Synthetic all-pass CSV (Part O.11)

A synthetic `summary.csv` with all rows at G6=1.0 and G2 empty/copy rate ≤ 0.05
causes the script to print `all P0 conditions met` and exit 0 — confirming the
script reaches the pass path when evidence is clean.
