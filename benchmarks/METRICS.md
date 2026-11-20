# Metric Definitions, CI Method, and Pre-Registered Thresholds (v2)

Version: validation/v2 · Seed = 42 · Bootstrap iterations = 1000

## Translation quality

| Metric | Definition | Direction |
|---|---|---|
| chrF++ | sacrebleu `corpus_chrf(hyps, [refs], word_order=2)`. Character n-gram F-score with word-order-2. Primary quality metric. | higher better |
| BLEU | sacrebleu `corpus_bleu(hyps, [refs], tokenize="13a")`. Reported **descriptively only** (see threshold decision below). | higher better |
| TER | sacrebleu TER (translation edit rate): edits / reference length. | lower better |

**BLEU threshold decision (Part C):** the previous `BLEU ≥ 5` pass floor is **removed as a pass/fail criterion**; BLEU is reported descriptively. Rationale: no published NLLB/M2M baseline scores exist for the exact language pairs and domains in this validation (classical-Chinese→modern-Chinese at n=3; zh medical terms→en at term level), so no defensible floor can be cited. chrF++ is the primary pass metric. (NLLB-200 paper reports FLORES-200 chrF for eng↔cmn, but not for classical Chinese or term-level translation; citing it as a floor for these tasks would be invalid.)

## 95% confidence intervals

Method: **nonparametric bootstrap over segments**, resampling the segment list
with replacement, 1,000 iterations, `random.seed(42)` (Python stdlib RNG;
NumPy seeded to 42 as well when present). The reported CI is the percentile
interval [2.5th, 97.5th] of the bootstrap distribution of the corpus metric.
Point estimate = metric on the full segment list.

Caveat: for datasets with n < 10 (classical-zh has n = 3), bootstrap CIs are
unstable and reported for completeness only; they do not license statistical
claims.

## Gate metrics (from the program's own validation gates)

| Code | Gate in `tmtrans.validate` | Pass-rate definition |
|---|---|---|
| G2 | `non_empty` (error) | share of segments with non-empty translation |
| G3 | `glossary` (error) | share of segments where every matched glossary rendering appears verbatim in the output. Binding-compliance metric. |
| G4 | `untranslated` (warning/error) | share of segments with residual source-script ratio < 5% |
| G6 | `numbers` (warning) | share of segments where every source number/dosage token survives in the output |
| G7 | `length` (warning) | share of segments with output/source length ratio in [0.15, 8.0] |

## G5 accounting (binomial hallucination) — exact definitions

- **G5_generated**: the number of binomial-shaped Latin candidates
  (`[A-Z][a-z]{3,}\s+[a-z][a-z-]{2,}`) in the model hypothesis that are
  absent from the workbench glossary AND absent from the accepted-species
  registry (`data/validation_registry.txt`: 299 species from the USDA
  400-row CC BY 4.0 sample + 53 curated glossary binomials = 334 names).
- **G5_caught**: of G5_generated, the count the program's hallucination gate
  flagged (gate failed with the binomial named in its detail string). A caught
  binomial means the segment is blocked from auto_pass — the safety mechanism
  worked.
- **G5_escaped**: G5_generated − G5_caught. The safety-relevant number: an
  escaped binomial reached the output without the gate flagging it.
- **G5_escape_rate** = G5_escaped / G5_generated. Reported as count/total and
  as a rate; `n/a` when G5_generated = 0.

Success criteria, stated before this run:
- Non-adversarial datasets: claim "no hallucinations" **only if** G5_generated = 0.
- Adversarial datasets: hallucinations are expected; the success criterion is
  **G5_escaped = 0** (every fabricated binomial caught), not G5_generated = 0.

## Segmentation / OCR / human review

- Segmentation boundary F1 and OCR CER/WER: **not produced in this run**
  (see `NOT_VALIDATED.md`).
- Human review: **not validated in this run** (see `NOT_VALIDATED.md`).

## Reproducibility metric

chrF++ absolute delta between two independent runs of the same dataset
(classical-zh) with the same model, temperature 0, same seed. Generations at
temperature 0 are not guaranteed bitwise-stable across backend versions; the
delta quantifies the residual nondeterminism.

## Pre-registered thresholds (updated for v2)

| Metric | Threshold | Status |
|---|---|---|
| chrF++ | ≥ 40.0 (corpus level, reference-matched tasks) | pass criterion |
| BLEU | — (descriptive only) | threshold removed |
| TER | — (descriptive only) | no floor |
| G3 pass rate | = 1.0 | zero-tolerance on segments with glossary matches |
| G4 pass rate | ≥ 0.95 (residual script < 5%) | pass criterion |
| G5 (non-adversarial) | G5_generated = 0 | zero-tolerance |
| G5 (adversarial) | G5_escaped = 0 | zero-tolerance |
| G6 pass rate | = 1.0 | zero-tolerance |
| G7 pass rate | ≥ 0.95 | pass criterion |
| Reproducibility | chrF++ delta ≤ 2.0 | pass criterion |

---

# v3 corrections and definitions (2026-11-21, validation/v3)

## Row classes (Part B)

- **Translation-quality rows (8):** classical-zh, glossary-adherence, and the
  six NTREX rows (en-th, th-en, en-lo, lo-en, en-km, km-en). These have
  (source, reference) pairs and chrF is meaningful (with the classical-zh
  smoke-test caveat below).
- **Gate-only rows (2):** hallucination-check (adversarial construction, its
  references are synthetic prompts) and usda-dosage (en→en dosage probes;
  42% of outputs are verbatim copies of the source, so chrF 64.75 is **not
  interpretable as translation quality** — decision (b): use usda-dosage for
  G6/G2 gate validation only).
- **Smoke test (subset of quality rows):** classical-zh has n = 3 with
  inferred parallelism (see NOT_VALIDATED.md); its chrF evidences that the
  classical→modern stage runs and is load-bearing (3.32 → 0.0 when disabled),
  not translation quality per se.

chrF≥40 failure counts are therefore reported three ways: 7/10 (all rows),
6/8 (quality rows), 5/7 (quality rows minus the n=3 smoke test).

## G2 (non_empty gate) semantics — v3 clarification

The program's `non_empty` gate fails on **empty OR verbatim-copy** outputs
("translation identical to source"). `G2_nonempty_pass_rate` in the CSVs is
the program-gate value (continuous with v2 summary.json); the decomposition
columns `G2_empty_output_count` and `G2_copy_output_count` show the mechanism.
Copy outputs pass G6 by construction (all source numbers survive), inflating
headline G6 rates; `G6_noncopy_pass_rate` is the non-trivial rate.

## G3 (glossary binding) applicability rule

**G3 reports n/a when no glossary term matches the scored source text.**
A value of 1.0 is reserved for rows with a non-empty applicable glossary.
Rows with n/a: all six NTREX rows (news text, no glossary matches), usda-dosage
(English probe text, no zh/sa/th matches), classical-zh (scored artifact is a
modern-Chinese rewrite; English renderings not applicable). Reportable rows:
glossary-adherence and hallucination-check only.

## G5 — two distinct metrics (v3)

- **Escape rate (safety floor):** G5_escaped / G5_generated. Zero escapes
  means every candidate the detector flagged was blocked from auto_pass.
  **An escape rate of 0 is a floor on safety, not evidence of detection
  accuracy** — a detector that flags everything achieves it trivially.
- **Detection precision (accuracy):** TP / (TP + FP) over manually labelled
  detections (`results/v3/g5_precision.csv`). v3 labels: NTREX 0% (0 TP / 50
  FP — sentence-boundary noise), adversarial set 40% (4 TP / 6 FP), glossary
  0% (chemical names, 2 of which were *correct* renderings).
- Per the <50% precision rule, G5 is described in v3 as a **species-name
  guardrail that requires an in-domain source**, not a general hallucination
  detector.

## G6 — zero-tolerance threshold (explicit)

Pre-registered threshold: **G6 pass rate = 1.0 (zero tolerance)** — any
dropped dosage/number token is a safety-critical failure for a medical-adjacent
tool. v3 results fail this on 2 of 3 applicable rows (glossary-adherence 0.80,
usda-dosage 0.875; non-copy rates 0.793 / 0.786). This is recorded as a
**safety-threshold failure**, not a pass.

## usda-dosage chrF interpretability (Part F decision)

Decision **(b)**: usda-dosage chrF = 64.75 is marked **not interpretable as
translation quality** (20/48 outputs are verbatim copies by the en→en probe
design). The dataset is used for G2/G6 gate validation only.

## Reproducibility metric (v3 extension)

chrF absolute deltas between two temperature-0 runs on glossary-adherence
(n=30) and usda-dosage (n=48), seed 42, plus comparison against the v2
baselines. The classical-zh delta (0.00) is retained as a footnote only
(n=3, uninformative for variance). See results/v3/reproducibility.json.
