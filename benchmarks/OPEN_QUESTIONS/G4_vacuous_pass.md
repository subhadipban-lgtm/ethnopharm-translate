# OPEN QUESTION — G4 (untranslated) vacuous pass on en→X rows

Status: open (not evaluated in v3.2) · Raised: 2026-11-21 · Owner: unassigned

## The question

`G4_untranslated_pass_rate` is reported as `1.0` on the X→en NTREX rows
(th→en, lo→en, km→en) and on usda-dosage, and is blank on the en→X rows
(en→th, en→lo, en→km) and on classical-zh.

The v3.1 round silently re-wrote these values (blanked the X→en / usda rows,
set classical-zh to 0.9333 and en→X rows to `n/a`) without a stated
denominator or a re-derivation. v3.2 reverted those edits to the v3 values.

What has not been established:

- Whether G4 on en→X rows is **vacuous** — i.e. whether the gate is checking
  anything at all when the target script is Thai/Lao/Khmer/Chinese, or whether
  it keys off English-target tokens and therefore passes trivially.
- Whether G4 = 1.0 on th→en / lo→en / km→en / usda-dosage reflects a real
  measurement or the same vacuity.
- Whether the classical-zh value should be reported at sub-sentence
  granularity rather than per segment.

## Why it matters

If G4 is vacuous on any row, those rows contribute nothing to the G4 pass
rate, and the 1.0 values are not evidence of "no untranslated spans".

## What is needed to close it

1. Read `tmtrans.validate` to determine exactly which tokens G4 matches on and
   what denominator it uses (per segment vs per token).
2. For one en→th segment with a known residual-script defect (e.g. the
   `เวสเทิร์น AMs` code-switch case in ERROR_ANALYSIS.md), confirm the gate
   fires or does not.
3. Decide: report G4 as n/a where the gate is vacuous, or fix the gate.
4. Record the decision here and in METRICS.md.

## Explicitly out of scope for v3.2

v3.2 only restored the v3 values and filed this question. No G4 value was
recomputed and no gate code was changed.
