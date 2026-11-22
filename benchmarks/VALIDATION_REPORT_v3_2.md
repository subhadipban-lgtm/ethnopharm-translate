# Validation Report v3.2 — ethnopharm-translate (tmtrans)

Branch: `validation/v3.2` · Date: 2026-11-21 · Base: `validation/v3.1` (`33d246c`) · v3.2 is a **recovery round**: it undoes three data-integrity defects introduced in v3.1 and corrects one misattributed mechanism. No model was re-run. No metric v3 published was recomputed.

> **Verdict language (v3.1, unchanged):**
> Pipeline is functionally validated on gate mechanics; two safety-threshold
> failures (G2 empty/copy outputs, G6 dosage preservation) block deployment on
> dosage-bearing text; G5 escape = 0 on samples tested but detection precision
> requires remediation.

---

## §1. What v3.1 got wrong

Three defects, one line each:

1. **ablations.csv numeric cells** — v3.1 replaced v3's rag_off/binding_off/classical_off numeric cells (chrF/BLEU/TER/CIs) with invented values, on the false premise that v3's file was internally inconsistent. The v3 CSV was a defective export (baseline cells duplicated into ablation rows), but the true ablation values exist in `benchmarks/results/v2/ablations_raw.json` and match the v3 report narrative. v3.1's numbers matched nothing.
2. **Part A G5 mechanism** — v3.1 stated both Khmu-people and Ellos-que segments were "blocked by boundary flag". The gate fired on the hallucinated spans themselves.
3. **G4_untranslated_pass_rate** — v3.1 silently changed 5 of 10 cells (blanked th/lo/km→en and usda-dosage to `n/a`, set classical-zh to 0.9333) with no denominator, no disclosure, and no re-derivation.

## §2. What v3.2 restores

- **ablations.csv**: numeric cells set from `ablations_raw.json` (the only surviving source of the true ablation numbers). See `results/v3.2/_provenance.csv` and the diff in `benchmarks/script_tests.md`. The `interpretation` column is added per the v3.1 brief.
- **summary.csv**: G4 reverted to the exact v3 values (blank for classical-zh and en→X rows; `0.9333` glossary-adherence; `1.0` hallucination-check, th/lo/km→en, usda-dosage). The v3.1 renames (`G2_nonempty_noncopy_pass_rate`, added `G2_fail_mechanism`) are retained — those were authorized. `copy_output_count` (dropped in v3.1) is restored.
- **g5_precision.csv**: `fp_class` reclassified on exactly 4 rows; `manual_label` and `rationale` untouched.

## §3. What v3.2 corrects — the Part A G5 mechanism

Per-segment evidence (from `benchmarks/results/v2/*_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl`):

**ntrex-128-lo-en, segment 7**
- source: `ຝ່າຍອະນຸລັກນິຍົມໃນສະພາເວລບອກວ່າກຸ່ມຂອງລາວ "ເປີດກວ້າງ" ກ່ຽວກັບການປ່ຽນຊື່ນີ້…`
- hypothesis: `The Khmu people of Laos are involved in the production of soap, although they themselves are not satisfied with the results, as they were from MWP to Muppets (characters).`
- `g5.generated_names = ["Khmu people", "Laos are"]`, `caught = 2`, `escaped = 0`, `status = failed`
- gate detail: `unattested binomials: Khmu people; Laos are`
- g5_precision.csv: `Khmu people` → FP, rationale "ethnic-group name in an otherwise hallucinated sentence… (genuine entity-level hallucination — see ERROR_ANALYSIS)", `fp_class = non_species_hallucination_blocked`

**ntrex-128-th-en, segment 17**
- source: `ประชาชนที่มีสิทธิ์ออกเสียงจะไปออกเสียงกันในวันอาทิตย์…`
- hypothesis: `Ellos que tienen derecho a votar irán a votar el domingo para decidir si deben cambiar el nombre del país a 'República Macedio Norte'`
- `g5.generated_names = ["Ellos que"]`, `caught = 1`, `escaped = 0`, `status = failed`
- gate detail: `unattested binomials: Ellos que`
- g5_precision.csv: `Ellos que` → FP, rationale "Spanish phrase — the whole output is a language-switch hallucination; not a species name", `fp_class = non_species_hallucination_blocked`

**Corrected statement (replaces the v3.1 §7 text):**

> On ntrex-128-lo-en:7, G5's detections were ['Khmu people', 'Laos are'] — the first is the hallucinated ethnic-group entity itself, the second is a boundary. The segment was blocked because G5 fired on the hallucinated entity, not because of a boundary false positive. On ntrex-128-th-en:17, G5's only detection was 'Ellos que' — the hallucinated Spanish-language output itself. Both segments were blocked by G5 detecting the hallucinated span, but G5 is a species-name regex and could not identify these spans as non-species hallucinations; they were flagged because they were capitalized multi-token phrases the gate did not find in the registry. The species-task precision of G5 remains 0% on NTREX; the segment-blocking behavior on these two segments happened to block real hallucinations, but it did so for the wrong reason.

**fp_class distribution after reclassification:** `n/a` 55, `boundary` 4, `correct_rendering_outside_registry` 2, `non_species_hallucination_blocked` 2. `manual_label` unchanged (TP=4, FP=59).

## §4. Test coverage added (see `benchmarks/script_tests.md`)

- Test 1: G2-only failure via `TMTRANS_P0_CSV` override → exit 1, usda-dosage flagged on G2 with G6 patched to 1.0.
- Test 2: v2-baseline comparison both directions via `TMTRANS_P0_BASELINE` and new `baseline-check` mode → pass (delta 0.00) and fail (`V2 BASELINE NOT REPRODUCED: run1=81.66, v2=79.00, delta=2.66`, exit 1).
- Test 3: byte-identical diff demonstrated — all four `diff | wc -l` counts are 0.
- Test 4: post-reclassification label and fp_class counts printed and verified.

## §5. v3.1 → v3.2 diff table

| claim | v3.1 said | v3.2 says | evidence |
|---|---|---|---|
| Part A G5 mechanism | "blocked by boundary flag" | "blocked by G5 detecting the hallucinated span itself; misclassified as FP by the species-task rubric" | g5_precision.csv rows; JSONL gate details (this report §3) |
| ablations.csv numeric cells | rewritten (invented) | restored from `ablations_raw.json`; `interpretation` column retained | `_provenance.csv`; `script_tests.md` |
| G4 column | blanked/0.9333/n/a (undisclosed) | exact v3 values restored | summary.csv diff vs v3 |
| `copy_output_count` column | dropped | restored | summary.csv diff vs v3 |
| fp_class | all 6 adversarial FPs = `boundary` | 4 `boundary`, 2 `correct_rendering_outside_registry`, 2 `non_species_hallucination_blocked` (the two non-species hallucinations are outside the adversarial set) | g5_precision.csv |
| `reproduce_v3.sh` testability | synthetic 5-col CSV; baseline case untestable | `TMTRANS_P0_CSV` / `TMTRANS_P0_BASELINE` overrides; `p0-only` and `baseline-check` modes | script_tests.md |
| byte-identical claim | asserted without a demonstrated diff | demonstrated: 4/4 `diff \| wc -l` = 0 | script_tests.md Test 3 |

## §6. Unresolved

- **G4 vacuous-pass question** — see `benchmarks/OPEN_QUESTIONS/G4_vacuous_pass.md`. v3.2 restores the v3 values and files the question; it does not adjudicate it.
- The two P0 failures from v3 are unchanged and unmitigated: G6 ≠ 1.0 on glossary-adherence (0.80) and usda-dosage (0.875); G2 empty/copy > 5% on usda-dosage (41.67%) and classical-zh (33.33%).

## §7. Deliverables on `validation/v3.2`

`results/v3.2/summary.csv`, `results/v3.2/ablations.csv`, `results/v3.2/g5_precision.csv`, `results/v3.2/reproducibility.json`, `results/v3.2/_provenance.csv`, `benchmarks/script_tests.md`, `benchmarks/VALIDATION_REPORT_v3_2.md`, `benchmarks/OPEN_QUESTIONS/G4_vacuous_pass.md`, `benchmarks/reproduce_v3.sh` (overrides), updated `METRICS.md`, `NOT_VALIDATED.md`, `RECOMMENDATION.md`, `ERROR_ANALYSIS.md`.

## §8. Provenance note on the ablations restoration

The v3.2 brief specifies the ablation values to restore (38.16/14.21/154.05; 82.61/56.0/40.54; classical_off 0.0) and describes them as "v3 values". They are not present in `benchmarks/results/v3/ablations.csv` at `dfcc615` or `fb52ff2` — that file carries duplicated baseline cells (81.66/55.82/37.84 in the rag_off and binding_off rows), an export defect in v3. The values do appear verbatim in `benchmarks/results/v2/ablations_raw.json` and in the v3 report narrative (§6: "chrF 81.66 → 38.16 when off"; §11: "chrF 81.66 → 82.61"; §10: "3.32 → 0.0 when disabled"). They were restored from `ablations_raw.json`, which is the raw output of the ablation runner and the only surviving source of the actual ablation measurements. The v3.2 brief's values match that file exactly. This is recorded in `results/v3.2/_provenance.csv` rather than papered over.

---

**Close-out:** v3.2 corrections applied. The two P0 failures from v3 remain unmitigated. v3.1's three data-integrity defects are retracted. The G4 vacuous-pass question is recorded as an open question. This round does not change any model-level result; it restores the evidence base to v3 and closes the audit findings against v3.1.
