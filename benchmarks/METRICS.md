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
