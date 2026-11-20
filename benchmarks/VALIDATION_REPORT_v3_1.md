# Validation Report v3.1 — ethnopharm-translate (tmtrans)

Branch: `validation/v3.1` · Date: 2026-11-21 · Base: `validation/v3` (tip `fb52ff2`, prior correction commit `dfcc615`) · v3.1 is a **correction round** that fixes framing, script semantics, and per-row attribution issues identified in the v3 audit. It is NOT a new benchmark round: all model outputs remain v2's. No model was re-run. Numbers that were correct are unchanged; no failure is softened.

> **Verdict language (v3, canonical, unchanged):**
> Pipeline is functionally validated on gate mechanics; two safety-threshold
> failures (G2 empty/copy outputs, G6 dosage preservation) block deployment on
> dosage-bearing text; G5 escape = 0 on samples tested but detection precision
> requires remediation.

## Section A — G5 "escape = 0" scope (Part A)

The v3 report's (a) "G5 missed nothing real" and (b) "escape = 0/63" could not both stand unqualified. Per-segment facts from `benchmarks/results/v2/*_mlx-community_Qwen2.5-3B-Instruct-4bit.jsonl`:

- **ntrex-128-lo-en:7 ("Khmu people")**: source is a Lao sentence about a name-change referendum; the model output "The Khmu people of Laos are involved in the production of soap…" is a wholly hallucinated entity. G5 `generated=2` (`Khmu people`, `Laos are`), `caught=2`, `escaped=0`, segment `status=failed` (BLOCKED). G5 flagged both sentence-boundary spans. **Escape = 0 is a genuine detection outcome on this segment (blocked by boundary flag), not an escape. But the real hallucination (the invented soap claim) is non-binomial — G5 does not catch it.**
- **ntrex-128-th-en:17 ("Ellos que")**: Thai source about a referendum; model answered in Spanish ("Ellos que tienen derecho a votar…"). G5 `generated=1` (`Ellos que`), `caught=1`, `escaped=0`, segment `status=failed` (BLOCKED). **Escape = 0 is a genuine detection outcome (blocked by boundary flag). But the real failure is a language-switch — non-binomial — which G5 does not catch.**

Added scope statement to this report §A and to METRICS.md:

> "Escape = 0 applies to binomial candidates only. Non-binomial hallucinations
> (e.g. 'Khmu people', Spanish-language answer to a Thai source) were observed
> in NTREX. Segment ntrex-128-lo-en:7 containing 'Khmu people' was blocked —
> because G5 flagged its sentence boundary. Therefore escape = 0 is a side-effect
> of over-blocking on that segment. Segment ntrex-128-th-en:17 containing
> 'Ellos que' was blocked — because G5 flagged its sentence boundary. Therefore
> escape = 0 is a side-effect of over-blocking on that segment. Non-binomial
> hallucinations in a segment not flagged by the boundary detector would not be
> caught."

METRICS.md one-line definition added:

> "Escape (G5) = a binomial candidate (as defined by the G5 regex) reached
> auto_pass without being flagged. Escape does not measure non-binomial
> hallucination survival; that is out of scope for G5."

## Section C — G6 failure composition per dataset with attribution (Part C)

Per-dataset breakdown (from the v2 JSONLs, `benchmarks/ERROR_ANALYSIS.md §11`):

| dataset | G6 failures | genuine value corruption | encoding shift | reference omission |
|---|---|---|---|---|
| glossary-adherence | 6 | 1 | 4 | 1 |
| usda-dosage | 6 | 4 | 2 | 0 |

**On glossary-adherence, 1 of 6 G6 failures is a genuine value corruption (16.7%), not 3 of 6.** The v3 report's "three genuine value corruptions ... the remainder" phrasing is corrected: the 3 refers to *distinct corruption types* (EC100→EC150, IC100→IC150, 180°→185°) represented across both datasets, not 3 of 6 within glossary-adherence. Per-instance count is 5 genuine corruptions across both datasets (1 glossary-adherence + 4 usda-dosage).

Attribution of the 3 named corruptions:
- `EC100→EC150` (usda-dosage:seg_0): src `EC100=50 uM` → hyp `EC150 dosage = 50 uM`
- `IC100→IC150` (usda-dosage:seg_29): src `IC100=2 mM` → hyp `IC150=2 mM` (same at usda-dosage:seg_31 and usda-dosage:seg_40)
- `180°→185°` (glossary-adherence:seg_29): src `180° plane rotation pulse` → hyp `185度平面旋转脉冲`

G6 scope clarified in METRICS.md: G6 preserves **all numeric tokens** (dosages, percentages, temperatures, angles, counts). An angle (`180°`→`185°`) is in scope under the numeric-token definition; it is not removed from the dosage-failure list. If the gate is ever intended for dosage preservation only, the angle failure must be removed from the dosage-failure list and reported separately under a numeric-token gate.

**Exec-summary headline corrected:** on glossary-adherence, 1 of 6 G6 failures is a genuine value corruption (the rest encoding shifts / reference omission); on usda-dosage, 4 of 6 are genuine value corruptions (EC100→EC150 ×1, IC100→IC150 ×3).

## Section D — Reproducibility: byte-identical verified (Part D)

Per-segment diff of hypothesis strings across run1, run2, and the v2 baseline:

| dataset | run1 vs run2 | run1 vs v2 baseline |
|---|---|---|
| glossary-adherence | **30/30 byte-identical** | **30/30 byte-identical** |
| usda-dosage | **48/48 byte-identical** | **48/48 byte-identical** |

chrF is identical (delta 0.00 at n=30 and n=48) **and** hypothesis strings are byte-identical — claim (a) applies:

> "Hypothesis strings are byte-identical across run1, run2, and the v2 baseline
> (verified by per-segment diff; 30/30 glossary-adherence and 48/48 usda-dosage
> segments identical)."

RECOMMENDATION.md updated accordingly. `reproducibility.json` includes `byte_identical: true` per dataset with segment counts, plus `v2_baseline` per dataset with delta 0.00.

## Section G — reproduce_v3.sh tests (Parts E, G, N)

`benchmarks/results/v3.1/script_tests.md` records:
1. **G2-in-isolation test**: synthetic CSV with G6=1.0 and G2 bad (20 copies on n=30, n=48) → script exits 1, G2 branch fires. Confirmed: the P0 gate works on G2 as well as G6.
2. **v2-baseline comparison test**: script loads v2 baselines from `benchmarks/results/v2/summary.csv` (glossary-adherence 81.66, usda-dosage 64.75) and fails if `abs(run1 - v2) > 2.0`. Emits `[repro] {ds}: run1=.. run2=.. v2=.. | delta_run1_run2=.. delta_run1_v2=..`. Both deltas 0.00 in real mode; skipped in mock mode.
3. **Label-distribution print**: `TP=4 FP=59 UNCLEAR=0 total=63`; exits 1 if UNCLEAR > 10%.
4. **Skipped-files print**: `skipped 8 ablation/repro files`.
5. **segment_id key comment**: `# key format: dataset:idx; assert this if the format changes`.
6. **Top-of-script note**: underscore-form model id in JSONL filenames, slash form in CSV values.

Mock mode verified: `42 passed`, all detections labelled, P0 correctly fails on G6/G2. Script exits non-zero while P0s are unmet (expected at v3.1).

## Section I — G3 / G5 overlap (Part I)

Join on segment id from the v2 JSONLs:

**glossary-adherence:**
- G3-failing segments: idx=15 (`13-cis-retinoic acid`), idx=16 (`13C-NMR spectrum`), idx=29 (`180° plane rotation pulse`)
- G5-detected segments: idx=1 (`Hydroxydecylenic acid`), idx=3 (`Hydroxydecenoic acid`), idx=12 (`Ricinoleyl coenzyme`)
- **Overlap: 0/3 — independent.** The same 3 segments do NOT fail both gates; G3 and G5 failures are independent evidence of two separate defects.

**hallucination-check:**
- G3-failing segment: idx=1 (`丹参 → danshen root`)
- G5-detected segments: idx=0..8 (9 detections across 8 segments)
- **Overlap: 1/1 — segment idx=1 fails both gates.**

## Section J — Adversarial-set FP composition (Part J)

Of the 6 adversarial FPs (hallucination-check set): **all 6 are type (a) boundary flags on non-hallucination content**; 0 type (b) wrong-span, 0 type (c) undesigned hallucination.

| segment_id | detected span | fp_class |
|---|---|---|
| hallucination-check:1 | Danshen two | boundary |
| hallucination-check:4 | Sweet wormwood | boundary |
| hallucination-check:6 | Coptis rhizome | boundary |
| hallucination-check:6 | Three grams | boundary |
| hallucination-check:7 | Some herbal | boundary |
| hallucination-check:8 | Please provide | boundary |

Recall 4/4 refers to the designed binomials only (Curcuma fabricata, Herba fictitia, Glycyrrhiza imaginaria, Panax fictionalis). Headline recall number unchanged; qualifier added per the audit.

## Section K — Commit SHA reconciliation (Part K)

- `dfcc615` — v3 correction commit (correction round, surface failures v2 hid).
- `fb52ff2` — v3 post-correction doc update; tip of `validation/v3` and base of `validation/v3.1`.
- `validation/v3.1` — this round (new commit at Part P).

Report header lists both with roles. RECOMMENDATION.md and NOT_VALIDATED.md reference no SHAs requiring update.

## Section L — Single-labeller limitation (Part L)

Added to RECOMMENDATION.md "Not blocking, unresolved":

> "G5 precision (0% NTREX / 40% adversarial) is from a single labeller across
> 63 detections. Inter-annotator agreement not measured. The precision estimate
> is one analyst's judgment and should be treated as indicative rather than
> definitive; a second-labeller adjudication of at least 20 detections is
> recommended before the precision number is cited in any publication."

Same sentence added to VALIDATION_REPORT_v3.md §7 (v3 report, unchanged file on `validation/v3`) and to NOT_VALIDATED.md item 12.

---

## v3 → v3.1 diff table

| claim | v3 said | v3.1 says | evidence |
|---|---|---|---|
| G5 escape scope | "G5 missed nothing real" unqualified | Escape = 0 is binomial-only; "Khmu people" (ntrex-128-lo-en:7) and "Ellos que" (ntrex-128-th-en:17) were **blocked** by boundary flags; non-binomial hallucination survival out of scope | JSONLs + METRICS.md escape definition |
| "safety floor held" | unqualified phrase | Replaced: "G5 escape rate was 0/63, but at 0% precision on news text the gate operates as a blanket block rather than a detector: it blocked 2 correct chemical renderings and missed the 2 real entity hallucinations it was not designed to see." | RECOMMENDATION.md §Justification |
| G6 composition | "three genuine value corruptions ... the remainder" | 1 of 6 glossary-adherence genuine; 4 of 6 usda-dosage genuine; attributed per segment | ERROR_ANALYSIS §11 + JSONLs |
| G6 scope | dosage preservation | numeric-token preservation (angle 180°→185° in scope) | METRICS.md G6 section |
| byte-identical reproducibility | claimed, not verified | **Verified: 30/30 and 48/48 byte-identical** across run1/run2/v2 baseline | reproducibility.json + per-segment diff |
| G2 column name | `G2_nonempty_pass_rate` (misnomer) | Renamed `G2_nonempty_noncopy_pass_rate` + `G2_fail_mechanism` | summary.csv header + METRICS.md |
| G3/G5 overlap | not stated | glossary-adherence 0/3 overlap (independent); hallucination-check 1/1 overlap | JSONL join + this report §I |
| adversarial FP classification | not stated | all 6 are type (a) boundary flags | g5_precision.csv fp_class + ERROR_ANALYSIS §9 |
| commit SHAs | dfcc615 only | dfcc615 (v3 correction) + fb52ff2 (v3 tip) + new v3.1 commit | git log |
| single-labeller | NOT_VALIDATED only | added to RECOMMENDATION.md "Not blocking, unresolved" + NOT_VALIDATED item 12 | this report §L |
| reproduce_v3.sh P0 label | "P0 conditions UNMET" | "P0 VALIDATION EVIDENCE UNMET (model-level G6/G2; deployment approval depends on fail-closed mitigation...)" | reproduce_v3.sh + script_tests.md |

---

## Corrections applied (summary)

- **Part A**: G5 escape scope statement added; "Khmu people" and "Ellos que" segments both BLOCKED (caught, not escaped); escape=0 is a side-effect of over-blocking on those segments; METRICS.md escape definition added.
- **Part B**: "safety floor held" replaced in RECOMMENDATION.md; "floor" never used without qualifier.
- **Part C**: G6 per-dataset composition table; attributions EC100→EC150 (usda:0), IC100→IC150 (usda:29/31/40), 180°→185° (glossary:29); METRICS.md G6 numeric-token scope; exec-summary headline corrected (1/6 glossary genuine, 4/6 usda genuine).
- **Part D**: byte-identical verified 30/30 and 48/48; reproducibility.json updated; RECOMMENDATION.md updated.
- **Part E**: reproduce_v3.sh compares run1 vs v2 baseline (>2.0 → fail); both deltas emitted; script_tests.md records commands/outputs.
- **Part F**: Option 1 applied — P0 label renamed, top-of-script note added, P0-evidence vs P0-deployment distinction documented.
- **Part G**: G2-in-isolation test passes (G2 branch fires with G6=1.0); script_tests.md written.
- **Part H**: summary.csv column renamed `G2_nonempty_noncopy_pass_rate`; `G2_fail_mechanism` added; METRICS.md note added; reproduce script reads renamed columns.
- **Part I**: G3/G5 overlap stated (0/3 glossary-adherence independent; 1/1 hallucination-check overlap).
- **Part J**: 6 adversarial FPs classified (all boundary); fp_class column added to g5_precision.csv; recall 4/4 qualifier kept.
- **Part K**: SHAs reconciled (dfcc615 + fb52ff2 + new v3.1 commit).
- **Part L**: single-labeller limitation added to RECOMMENDATION.md and NOT_VALIDATED.md.
- **Part M**: ablations.csv interpretation column populated.
- **Part N**: label-distribution print, skipped-files print, segment_id key comment, top-of-script note added to reproduce_v3.sh.

## Deliverables on `validation/v3.1`

| file | status |
|---|---|
| `benchmarks/results/v3.1/summary.csv` | renamed G2 column + `G2_fail_mechanism` + normalized model id |
| `benchmarks/results/v3.1/ablations.csv` | `interpretation` column populated |
| `benchmarks/results/v3.1/g5_precision.csv` | 63 labels unchanged + `fp_class` column |
| `benchmarks/results/v3.1/reproducibility.json` | `byte_identical` per dataset + `v2_baseline` |
| `benchmarks/results/v3.1/script_tests.md` | G2-in-isolation + v2-baseline + P0-evidence tests |
| `benchmarks/METRICS.md` | escape definition + G2 rename note + G6 scope |
| `benchmarks/ERROR_ANALYSIS.md` | G6 composition + adversarial FP classification |
| `benchmarks/NOT_VALIDATED.md` | binomial-only escape + single-labeller notes |
| `benchmarks/RECOMMENDATION.md` | safety-floor wording + single-labeller + P0-evidence/deployment + byte-identical |
| `benchmarks/VALIDATION_REPORT_v3_1.md` | this report |
| `benchmarks/reproduce_v3.sh` | updated per Parts E, F, G, N |

**Close-out language:** v3.1 corrections applied; the two P0 failures from v3 remain (G6 zero-tolerance failure, G2 empty/copy outputs at 42% on usda-dosage); the report's specific gaps flagged by the v3 audit are now closed. This is NOT a claim of "fully validated" or "all issues resolved."
