# OPEN QUESTION — G4 (untranslated) on Latin-source rows: RESOLVED in v4 (found defect)

Status: **resolved by code fix in commit after d076d47** · Raised: 2026-11-21 · Updated: 2026-11-22

## Original question

Whether `G4_untranslated_pass_rate` on en→X rows was **vacuous** — i.e. whether
the gate was checking anything at all.

## What the code actually did (pre-fix)

`tmtrans.validate._residual_script_ratio` selected which Unicode ranges count as
"residual source script" from the **source** language alone:

- `zh`/`lzh`/`ja` → CJK ranges
- `vi`/`id`/`ms`/`tl` → returned `0.0` (Latin source, nothing to detect)
- **everything else (including `en`) → `_INDIC_RANGES`**

Consequences:

1. **en → th/lo/km**: the "residual" ranges were Indic/Thai/Lao/Khmer, i.e. the
   *target* script. A perfect Thai/Lao/Khmer translation scored ratio 1.0 and
   would fail G4. Measured: `_residual_script_ratio("นี่คือประโยคทดสอบ",
   source_lang="en") == 1.0`. The v3/v4 benchmark harness masked this by
   forcing `passed=None` for non-English targets.
2. **en → anything Latin** (e.g. Vietnamese glossary checks): identical
   mis-count, because `en` was never special-cased.
3. en → th was therefore never a valid measurement; the en→X "blank" cells in
   the summary tables were blank for a reason, and the th→en / km→en / usda rows
   that showed `1.0` were **not** evidence of anything either — with an English
   target, the gate had no source-script characters to find and trivially passed.

So: the 1.0 values were vacuous-by-construction on Latin-source rows, and the
gate was actively wrong (would false-fail) on genuinely non-Latin targets from
a Latin source. Not a threshold problem — a wrong-ranges-selected problem.

## Fix (v4)

`_LATIN_SOURCE_LANGS = {"en", "vi", "id", "ms", "tl"}` → return `0.0` (gate not
applicable). `zh`/`lzh`/`ja` keep CJK ranges; other Indic-source languages keep
the Indic ranges. Two regression tests added
(`test_gate_residual_script_latin_source`,
`test_gate_residual_script_detects_source_leftover`); 44 tests pass.

## Residual open items (NOT closed by this fix)

- **No non-Latin-target detection for Latin sources remains impossible** — G4
  cannot tell a correct Thai output from an empty one on en→th. If that
  direction matters, G4 needs an explicit "target script present?" check
  (e.g. require ≥ X% of chars in the target script for non-Latin targets).
  Not implemented; no claim is made about en→X quality from G4.
- The **en→X rows in the benchmark still carry no G4 signal** and should be
  reported as n/a, not as 1.0. No metric was recomputed in this round.
- **v3/v4 summary CSVs were NOT regenerated** — G4 values there are stale
  artifacts of the buggy gate and of the harness's `passed=None` masking. They
  should be regenerated in the next validation round, which also requires
  re-running the models (not done here; see Co-Authored-By note in commit).
- The classical-zh `n/a` for G4 remains correct (target is Chinese; residual
  check is meaningless).

## Decision record

Do not backfill numbers into v3/v4 artifacts. Report G4 as n/a for en→X and for
Latin-target rows until the harness emits a target-script-presence gate.
