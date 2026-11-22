# Script tests — reproduce_v3.sh (validation/v3.2)

Tests 1–4 below were run against the actual `benchmarks/reproduce_v3.sh` in
validation/v3.2, on the real `benchmarks/results/v3.2/summary.csv`. Earlier
versions of this file (v3.1) tested a synthetic 5-column CSV and skipped the
failing v2-baseline case; both are replaced here.

Prerequisites: `benchmarks/reproduce_v3.sh` supports two test-only overrides:

- `TMTRANS_P0_CSV` — path to a summary.csv to use for the P0 check
  (default `benchmarks/results/v3.2/summary.csv`)
- `TMTRANS_P0_BASELINE` — path to a v2-format summary.csv whose `chrf` column
  is used as the baseline for the repro delta check
  (default `benchmarks/results/v2/summary.csv`)

Modes: `mock` (default), `real`, `p0-only` (P0 check only, no test suite),
`baseline-check` (v2-baseline delta check only).

---

## Test 1 — G2-only failure via `TMTRANS_P0_CSV` (Part E.1)

Command:
```
cp benchmarks/results/v3.2/summary.csv /tmp/summary_g2.csv
python3 -c "
import csv
rows = list(csv.DictReader(open('/tmp/summary_g2.csv')))
for r in rows:
    if r['dataset'] == 'usda-dosage':
        r['G6_numbers_pass_rate'] = '1.0'
w = csv.DictWriter(open('/tmp/summary_g2.csv','w'), fieldnames=list(rows[0].keys()))
w.writeheader(); w.writerows(rows)
"
TMTRANS_P0_CSV=/tmp/summary_g2.csv bash benchmarks/reproduce_v3.sh p0-only; echo "EXIT=$?"
```

Result (full output in `/tmp/test1.log`): **EXIT=1**. The usda-dosage row shows
`empty=0 copy=20 g6=1.0` and is tagged `[P0-FAIL]` with
`G2_empty+copy=41.67% G6=1.0`. The P0 gate fires on G2 alone — G6 was patched
to 1.0 for this test, so the failure is attributable to G2 alone. The classical-zh
row also fails on G2 (33.33% empty+copy), and glossary-adherence fails on G6
(0.8, dosage-bearing). All other rows PASS.

## Test 2 — v2-baseline comparison, both directions (Part E.2)

The script supports a `baseline-check` mode that compares the stored repro
chrF (from `results/v3.2/reproducibility.json`) against the v2 baseline CSV.
A failing case is produced by pointing `TMTRANS_P0_BASELINE` at a patched
copy of the v2 summary in which glossary-adherence chrf is set to 79.00.

Failing case:
```
python3 -c "
import csv
rows = list(csv.DictReader(open('benchmarks/results/v2/summary.csv')))
for r in rows:
    if r['dataset'] == 'glossary-adherence':
        r['chrf'] = '79.00'
w = csv.DictWriter(open('/tmp/baseline_patched.csv','w'), fieldnames=list(rows[0].keys()))
w.writeheader(); w.writerows(rows)
"
TMTRANS_P0_BASELINE=/tmp/baseline_patched.csv bash benchmarks/reproduce_v3.sh baseline-check; echo "EXIT=$?"
```
Output:
```
== [baseline-check] stored/injected repro chrF vs v2 baseline (/tmp/baseline_patched.csv) ==
[repro-check] glossary-adherence: run1=81.66 v2=79.0 | delta=2.66
V2 BASELINE NOT REPRODUCED: run1=81.66, v2=79.00, delta=2.66
[repro-check] usda-dosage: run1=64.75 v2=64.75 | delta=0.00
EXIT=1
```

Passing case (real v2 baseline):
```
$ bash benchmarks/reproduce_v3.sh baseline-check; echo "EXIT=$?"
== [baseline-check] stored/injected repro chrF vs v2 baseline (benchmarks/results/v2/summary.csv) ==
[repro-check] glossary-adherence: run1=81.66 v2=81.66 | delta=0.00
[repro-check] usda-dosage: run1=64.75 v2=64.75 | delta=0.00
EXIT=0
```

Note: the `real` mode of `reproduce_v3.sh` performs the same comparison against
freshly-generated repro runs (`run1`/`run2` from `run_v2.run_dataset`) and
also fails if either delta exceeds 2.0. The `baseline-check` mode exists so
the failure path can be exercised without an MLX endpoint.

## Test 3 — byte-identical diff, demonstrated (Part E.3)

Commands and outputs (exact):

```
$ diff <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_glossary-adherence_run1_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) \
       <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_glossary-adherence_run2_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) | wc -l
0
$ diff <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_glossary-adherence_run1_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) \
       <(jq -r '.hypothesis' benchmarks/results/v2/glossary-adherence_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) | wc -l
0
$ diff <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_usda-dosage_run1_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) \
       <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_usda-dosage_run2_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) | wc -l
0
$ diff <(jq -r '.hypothesis' benchmarks/results/v3/repro_v3_usda-dosage_run1_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) \
       <(jq -r '.hypothesis' benchmarks/results/v2/usda-dosage_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl) | wc -l
0
```

All four diffs are empty (0 lines). `reproducibility.json` `byte_identical: true`
is therefore supported by direct diff, not merely by equal chrF.

## Test 4 — label distribution after Part D reclassifications (Part E.4)

Command:
```
python3 -c "import csv; from collections import Counter; rows=list(csv.DictReader(open('benchmarks/results/v3.2/g5_precision.csv'))); print(Counter(r['fp_class'] for r in rows)); print(Counter(r['manual_label'] for r in rows))"
```

Output:
```
Counter({'n/a': 55, 'boundary': 4, 'correct_rendering_outside_registry': 2, 'non_species_hallucination_blocked': 2})
Counter({'FP': 59, 'TP': 4})
```

The four reclassified rows are:
- `hallucination-check:4` Sweet wormwood → `correct_rendering_outside_registry`
- `hallucination-check:6` Coptis rhizome → `correct_rendering_outside_registry`
- `ntrex-128-lo-en:7` Khmu people → `non_species_hallucination_blocked`
- `ntrex-128-th-en:17` Ellos que → `non_species_hallucination_blocked`

`manual_label` is unchanged everywhere (TP=4, FP=59).

## Part A diff — ablations.csv vs validation/v3 git (Part A.5)

Command (as specified in the brief):
```
diff <(git show validation/v3:benchmarks/results/v3/ablations.csv | cut -d, -f1-16) \
     <(cut -d, -f1-16 benchmarks/results/v3.2/ablations.csv)
```
Output (exit 1):
```
5c5
< classical-zh,...,classical_off,3,3.32,"[0.0, 13.05]",0.0,"[0.0, 0.0]",100.0,0.0,0,,,0
---
> classical-zh,...,classical_off,3,0.0,"[0.0, 0.0]",0.0,"[0.0, 0.0]",100.0,0.0,0,,,0
7,8c7,8
< glossary-adherence,...,rag_off,30,81.66,"[67.68, 94.06]",55.82,"[30.82, 81.05]",37.84,0.9,2,1.0,1.0,2
< glossary-adherence,...,binding_off,30,81.66,"[67.68, 94.06]",55.82,"[30.82, 81.05]",37.84,0.9667,1,0.9,0.9333,4
---
> glossary-adherence,...,rag_off,30,38.16,"[29.15, 46.34]",14.21,"[4.93, 26.85]",154.05,0.9,2,1.0,1.0,2
> glossary-adherence,...,binding_off,30,82.61,"[69.8, 94.45]",56.0,"[30.42, 84.84]",40.54,0.9667,1,0.9,0.9333,4
```

The numeric cells therefore do **not** match the v3 git CSV — and cannot,
because that CSV carries duplicated baseline cells in exactly these three rows
(an export defect in v3). The v3.2 values come from
`benchmarks/results/v2/ablations_raw.json` (raw runner output) and are
identical to the values named in the v3.2 brief, and to the v3 report
narrative (§6: "chrF 81.66 → 38.16 when off"; §11: "chrF 81.66 → 82.61";
§10: "3.32 → 0.0 when disabled"). Verified: every numeric cell in
v3.2/ablations.csv matches ablations_raw.json exactly. Provenance is recorded
in `benchmarks/results/v3.2/_provenance.csv`. All other rows and columns are
byte-identical to v3; the only added column is `interpretation`.

## Part C diff — summary.csv G4 column vs v3

`G4_untranslated_pass_rate` was reverted to the exact v3 values:
blank for classical-zh, ntrex-128-en-th, ntrex-128-en-lo, ntrex-128-en-km;
`0.9333` glossary-adherence; `1.0` hallucination-check, ntrex-128-th-en,
ntrex-128-lo-en, ntrex-128-km-en, usda-dosage. All other columns (including
the v3.1 `G2_nonempty_noncopy_pass_rate` rename and the new `G2_fail_mechanism`
column) are unchanged from v3.1. See the diff below (Part C.4).

## Full mock-mode run (context)

`bash benchmarks/reproduce_v3.sh mock` → 42 passed; labelling completeness OK
(TP=4 FP=59 UNCLEAR=0); exits 1 because the two P0 failures (G6 ≠ 1.0 on
dosage-bearing rows, G2 empty/copy > 5% on usda-dosage and classical-zh) remain
unmitigated. That is the expected and documented behaviour.
