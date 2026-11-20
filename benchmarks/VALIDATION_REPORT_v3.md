# Validation Report v3 — ethnopharm-translate (tmtrans)

Branch: `validation/v3` · Date: 2026-11-21 · Base: `validation/v2` (`08d529b`, `c2a93b6`) · v3 is a **correction round**, not a new benchmark round: all model outputs are v2's; v3 fixes framing, exposes hidden failures, and adds precision labelling + reproducibility on larger samples.

## 1. Executive summary

Two safety-threshold failures block deployment on dosage-bearing text: **G2** (empty/copy outputs) fails 42% of usda-dosage rows (20/48 verbatim copies; 1/3 classical-zh outputs empty) and **G6** (dosage preservation) fails the pre-registered zero-tolerance threshold on 2 of 3 applicable rows (glossary-adherence 80%, usda-dosage 87.5%; non-copy rates 79.3%/78.6%), including three genuine value corruptions (EC100→EC150, IC100→IC150, 180°→185°). The G5 safety floor held: 0/63 binomial candidates escaped the gate, including 10/10 on the adversarial set — but detection precision is 0% on news text (0 TP / 50 FP) and 40% adversarial, so escape=0 is a floor, not evidence of accuracy. chrF≥40 fails on 7/10 rows (6/8 quality rows) at 3B. Segment count corrected: **241**, not 209. Reproducibility deltas 0.00 at n=30 and n=48 (temperature 0).

## 2. Environment

Unchanged from v2: `mlx-community/Qwen2.5-3B-Instruct-4bit` (4-bit MLX), endpoint `http://localhost:8099/v1` (mlx-lm 0.32.2), temperature 0, seed 42, Python 3.15.2, macOS arm64. Offline tests: **42** (`pytest -q`: `42 passed in 0.53s`). v2 commit `08d529b6fd4cc0c3f086f1fef00f2fe3f9f75341`; v3 adds correction-layer commits on `validation/v3` (SHA recorded in Part 11).

## 3. Part A — segment-count reconciliation

The v2 narrative said "209 segments." The sum of `n_segments` in
`benchmarks/results/v2/summary.csv` is:

`3 + 30 + 10 + 25 + 25 + 25 + 25 + 25 + 25 + 48 = **241**`

**Total evaluated segments: 241 (see results/v2/summary.csv for per-dataset counts).** The 209 figure was an arithmetic error in the v2 narrative (no exclusion rule produced it; 241 − 209 = 32 matches no subset of the rows). Struck: "209 segments." The G5 totals (63 generated / 63 caught / 0 escaped) are unaffected — they are sums over per-segment detections, not over n_segments.

## 4. Part B — chrF framing (both numbers reported)

Row classes are defined in `METRICS.md` §v3: translation-quality rows =
classical-zh, glossary-adherence, six NTREX rows (8 rows); gate-only rows =
hallucination-check (adversarial construction), usda-dosage (en→en probes,
42% copy outputs — chrF not interpretable). classical-zh is additionally a
smoke test (n=3, inferred parallelism — Part 10).

| Framing | chrF≥40 failures |
|---|---|
| (a) All 10 rows | **7/10** fail (only glossary-adherence 81.66, th-en 43.53, usda-dosage 64.75 pass) |
| (b) Translation-quality rows only (8) | **6/8** fail (classical-zh 3.32, en-th 24.56, en-lo 5.44, en-km 15.44, lo-en 23.41, km-en 27.09 fail) |
| (c) Quality rows minus the n=3 smoke test (7) | **5/7** fail |

v2's "6/8" held only under framing (b) and was presented without the rule.
All three framings are now on record; (a) is the least favorable and is the
headline number.

## 5. Part C — G5 claim-threshold failures (explicit)

Pre-registered rule: G5_generated = 0 on non-adversarial rows. **Five
non-adversarial rows fail it** (v2 narrative called out one):

| dataset | G5_generated | claim threshold |
|---|---|---|
| glossary-adherence | 3 | **FAIL** |
| ntrex-128-en-lo | 5 | **FAIL** |
| ntrex-128-km-en | 14 | **FAIL** |
| ntrex-128-lo-en | 16 | **FAIL** |
| ntrex-128-th-en | 15 | **FAIL** |

The adversarial row (hallucination-check, generated=10) is judged by the
escape criterion, not the generation criterion, and **passes** (escaped=0).

Why "claim fails / safety passes" is not a contradiction: the claim threshold
measures whether unattested candidates were *produced at all* (a quality
aspiration); the escape criterion measures whether any candidate reached
auto_pass *without being flagged* (the safety property). A gate can catch
everything the model produces (safety holds) while the model still produces
too much noise (claim fails). Per the v3 precision study (§7), most claim
failures are detector false positives on sentence boundaries, not species
inventions — but the pre-registered rule is reported as failed regardless.

## 6. Part D — RAG claim qualified

RAG glossary retrieval is the dominant quality factor **where an applicable
glossary exists** (glossary-adherence: chrF 81.66 → 38.16 when off). On
classical-zh, where no glossary term applies, RAG has no measurable effect
(baseline = rag_off = 3.32 exactly). The unqualified phrase "RAG is the
dominant quality factor" is withdrawn.

## 7. Part G — G5 precision (63 detections manually labelled)

Full labelling: `results/v3/g5_precision.csv` (dataset, segment_id, span,
source, manual_label, rationale for every detection). Rubric: TP only if the
source implied a species-name-like term and the model fabricated one absent
from the registry; sentence-boundary phrases, news entities, place names,
chemical names = FP.

| set | detections | TP | FP | precision | FP rate |
|---|---|---|---|---|---|
| NTREX rows (km/lo/th/en-lo) | 50 | 0 | 50 | **0.0%** | 100% |
| hallucination-check (adversarial) | 10 | 4 | 6 | **40.0%** | 60% |
| glossary-adherence | 3 | 0 | 3 | 0.0% | 100% |

Two facts from the labelling: (1) the 4 designed fabricated binomials
(Curcuma fabricata, Herba fictitia, Glycyrrhiza imaginaria, Panax
fictionalis) were all caught — recall 4/4 on the designed set; (2) 2 of the
3 glossary flags were **correct** glossary renderings
(10-Hydroxydecylenic acid, 10-Hydroxydecenoic acid) — the gate blocks right
answers on chemical nomenclature. On NTREX the gate flagged sentence
boundaries ("Congress said", "Some even") and missed nothing real because
nothing real was there — and where real entity hallucinations occurred
("Khmu people" soap sentence, Spanish-language answer "Ellos que…"), G5
flagged only their boundaries.

**Rewritten G5 claim:** escape rate on samples tested **0/63**; detection
precision **0% on NTREX news, 40% on the adversarial set**. Escape rate is a
floor on safety, not evidence of detection accuracy. Per the <50% precision
rule, G5 is described as a **species-name guardrail that requires an in-domain
source**, not a hallucination detector.

## 8. Part F + H — G2 and G6 (the two safety-threshold failures)

### Gate G2 (empty/copy outputs)

The program's G2 gate fails on empty **or** verbatim-copy outputs. The audit
premise said usda-dosage had "20 empty"; the JSONLs show **0 empty, 20
copies** (hypothesis ≡ source) — the gate value stands, the mechanism is
copy. `G2_nonempty_pass_rate` (gate semantics) with decomposition:

| dataset | G2 gate pass | empty | copy |
|---|---|---|---|
| classical-zh | 0.6667 | **1** | 0 |
| glossary-adherence | 0.9667 | 0 | 1 |
| ntrex-128-en-km | 0.96 | 0 | 1 |
| usda-dosage | **0.5833** | 0 | **20** |
| all other rows | 1.0 | 0 | 0 |

Part F consequence (decision **(b)**, documented in METRICS.md): usda-dosage
chrF 64.75 is computed on a row with 42% copy outputs and is **not a reliable
translation-quality signal**; usda-dosage is used for G2/G6 gate validation
only. The classical-zh true empty (modern stage produced an empty rewrite) is
the corpus's only genuine empty output.

### Gate G6 (dosage/number preservation) — safety-threshold FAILURE

Pre-registered threshold: G6 = 1.0 (zero tolerance). **Fails on 2 of 3
applicable rows:**

| dataset | G6 (all rows) | G6 (non-copy rows) | fails |
|---|---|---|---|
| glossary-adherence | **0.80** | **0.793** (23/29) | 6 of 30 |
| usda-dosage | **0.875** | **0.786** (22/28) | 6 of 48 |
| all other rows | 1.0 | 1.0 | 0 |

G2×G6 correlation (Part H.3): copy rows pass G6 **by construction** (every
source number survives a verbatim copy) — the 20 usda copies inflate the
headline 0.875; the non-trivial rate on non-copy rows is 0.786. No G6 failure
overlaps a copy row; vacuous-pass inflation is confirmed and quantified.

Failure composition (ERROR_ANALYSIS §11): three genuine **value corruptions**
— `EC100`→`EC150`, `IC100`→`IC150`, `180°`→`185°` — the dangerous class for
dosage-bearing text; the remainder are encoding shifts (Δ2 locant inside a
chemical name; `4x`→`four`) and cases where the gold reference itself omits
the number (e.g. `13-顺-维甲酸`→ref `Ro acutane`). Regardless of composition,
the zero-tolerance rule is failed; P0 remediation is required.

## 9. Part I — vacuous G3 fixed

G3 (glossary binding) vacuously passes when no glossary term matches the
scored source. Recomputed applicability from the JSONLs with the run's
constraint glossary: only **glossary-adherence** (28/30 rows with matches)
and **hallucination-check** (3/10) have a non-empty applicable glossary. All
six NTREX rows, usda-dosage, and classical-zh are **n/a** (their v2 "1.0"
values were vacuous and are replaced by n/a in results/v3). Reportable G3:
glossary-adherence **0.90**, hallucination-check **0.90** — both below the
zero-tolerance 1.0 threshold (3 glossary rows produced unattested candidates
the gate blocked; 1 adversarial row missed a rendering).

## 10. Part J — Gare documented as smoke test

`hf_license_audit.json`: Gare features = `["text"]`, size = null. The 3 pairs
are derived from alternating 古文/现代文 lines — **parallelism is inferred,
not verified**; the HF API returns no dataset size (datasets-server exposes a
single `train` split of 6 rows). The classical-zh row is labelled
**smoke test (n=3)**: its chrF = 3.32 is not evidence of translation quality;
it evidences that the classical→modern stage runs and is load-bearing
(3.32 → 0.0 when disabled, ablation table). Recorded in NOT_VALIDATED.md.

## 11. Part K — binding constraints requalified

binding_off on glossary-adherence: chrF 81.66 → 82.61 (marginally *better*),
CIs overlap; G5_generated 3 → 4, within noise. Binding constraints show **no
measurable chrF effect on n=30** and are retained as defense-in-depth, not as
the primary quality driver. The v2 wording implying binding constraints are a
decisive safety mechanism is withdrawn; glossary *retrieval* (RAG) is the
measurable driver (§6).

## 12. Part L — model-name normalization

All v3 files use the canonical HF id `mlx-community/Qwen2.5-3B-Instruct-4bit`
(slash form). The underscore form (`mlx-community_Qwen2.5-3B-Instruct-4bit`)
in v2 CSVs was a CSV-safe filename encoding, not a different model. v3 CSVs
regenerated from the JSONL source of truth.

## 13. Part E — reproducibility (larger samples)

Temperature 0, seed 42, two runs per dataset (results/v3/reproducibility.json):

| dataset | n | run1 chrF | run2 chrF | abs delta | vs v2 baseline |
|---|---|---|---|---|---|
| glossary-adherence | 30 | 81.66 | 81.66 | **0.00** | 0.00 / 0.00 |
| usda-dosage | 48 | 64.75 | 64.75 | **0.00** | 0.00 / 0.00 |
| classical-zh (footnote) | 3 | 3.32 | 3.32 | 0.00 | n=3 smoke test, uninformative for variance |

Deltas 0.00 at n=30 and n=48; both runs reproduce the v2 baselines exactly —
the v2 numbers stand (no retraction needed). Determinism is supported on this
MLX stack at temperature 0; not guaranteed across backend versions.

## 14. v2 → v3 diff table

| claim | v2 said | v3 says | evidence |
|---|---|---|---|
| segment count | 209 | **241** | sum of n_segments in summary.csv |
| chrF failures | 6/8 | **7/10 all rows; 6/8 quality; 5/7 minus smoke test** | Part 4 |
| G5 claim failures | 1 called out | **5 non-adversarial rows** | Part 5, summary.csv |
| G5 nature | "hallucination detector" | **species-name guardrail, in-domain only**; precision 0% NTREX / 40% adversarial | g5_precision.csv, 63 labels |
| G2 | not surfaced | **0.5833 usda (20 copies, 0 empty), 0.6667 classical (1 empty)** | Part 8, JSONLs |
| G6 | "maintained/supported" | **safety-threshold FAIL on 2/3 rows; non-copy 0.793/0.786; 3 value corruptions** | Part 8, ERROR_ANALYSIS §11 |
| G3 | 1.0 on NTREX | **n/a (vacuous)**; reportable 0.90/0.90 only | Part 9 |
| usda chrF 64.75 | quality number | **not interpretable (42% copies)**; gate-validation only | METRICS.md §v3 |
| RAG | "dominant quality factor" | **dominant only where a glossary applies** | Part 6, ablations |
| binding constraints | implied decisive | **no measurable effect (CIs overlap)** | Part 11, ablations |
| Gare/classical-zh | benchmark row | **smoke test (n=3, inferred parallelism)** | Part 10 |
| reproducibility | delta 0.00 (n=3) | **deltas 0.00 (n=30, n=48), v2 baselines reproduced** | Part 13 |

## 15. Limitations

Full list: `NOT_VALIDATED.md` (v2 items + v3 additions). Headline: G5
precision characterized by single-labeller manual labeling only; human review
not validated; OCR not validated; TCM-specific and non-Qwen models not run;
Gare parallelism inferred (n=3); usda-dosage chrF uninterpretable; USDA full
registry commercial; MeSpEn contains inverted rows.

## 16. Recommendation

**APPROVE WITH CONDITIONS** — `RECOMMENDATION.md`, with P0 conditions: G6
zero-tolerance failure and G2 empty/copy outputs block deployment on
dosage-bearing text pending fail-closed behavior or model upgrade; P1: G5
precision remediation and human-review validation; P2: non-Qwen/7B-class run
and a larger classical gold set.

## 17. Deliverables

| file | content |
|---|---|
| `benchmarks/results/v3/summary.csv` | corrected results table (G2 decomposition, G3 n/a, G6 non-copy, precision columns, slash model id) |
| `benchmarks/results/v3/ablations.csv` | ablations with binding_off annotation |
| `benchmarks/results/v3/g5_precision.csv` | 63 manually labelled detections (TP/FP/UNCLEAR + rationale) |
| `benchmarks/results/v3/reproducibility.json` | two-run deltas at n=30/n=48 + classical footnote |
| `benchmarks/results/v3/repro_v3_*.jsonl` | per-segment outputs of the reproducibility runs |
| `benchmarks/METRICS.md` | v3 definitions: row classes, G2 semantics, G3 n/a rule, G6 zero-tolerance, G5 precision/escape, usda caveat |
| `benchmarks/ERROR_ANALYSIS.md` | v3 sections: G5 false positives (6 real), G2 empty/copy (5 real), G6 failures (6 real) |
| `benchmarks/NOT_VALIDATED.md` | v3 additions (precision scope, Gare inference, repro extension, usda caveat, non-Qwen gap) |
| `benchmarks/RECOMMENDATION.md` | P0/P1/P2 conditions |
| `benchmarks/reproduce_v3.sh` | mock suite + repro re-runs + label-completeness check; exits non-zero on P0 unmet |
| `benchmarks/VALIDATION_REPORT_v3.md` | this report |