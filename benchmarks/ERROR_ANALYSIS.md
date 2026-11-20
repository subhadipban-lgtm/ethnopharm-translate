# Error Analysis — validation/v2

All examples below are **real outputs** from the v2 run
(`mlx-community/Qwen2.5-3B-Instruct-4bit`, temperature 0), extracted from the
per-segment JSONL files in `benchmarks/results/v2/`. Nothing here is invented.

Categories and which datasets surfaced them:

| Category | Sourced from | Count observed |
|---|---|---|
| Terminology miss (glossary rendering not reproduced) | glossary-adherence | see run |
| Hallucinated binomial — **caught** | glossary-adherence, hallucination-check | 2–3 per run |
| Hallucinated binomial — **escaped** | none so far in v2 | 0 |
| Dosage / number corruption | glossary-adherence | 4 |
| Untranslated span (source script left in output) | glossary-adherence (1 empty), en→th (partial) | varies |
| Segmentation error | not measured (no gold segmentation) | — |
| Over-constrained / awkward translation | glossary-adherence, ntrex | several |
| OCR failure | NOT RUN (see NOT_VALIDATED.md) | — |

---

## 1. Terminology miss

The MeSpEn glossary-adherence set (zh term → en rendering) surfaces the model's
default chemical-name behavior: it transliterates/appeals to generic chemistry
naming instead of the attested glossary rendering.

- `10-甲氧基美迪紫檀素` → expected `10-methoxymedicarpin`; model output:
  `10-Methoxymediphloroglucin` — wrong but plausible-looking chemical name.
- `10-羟基-Δ2-葵烯酸,王浆酸` → expected `10-Hydroxydecylenic acid`; model output:
  `10-Oxidos-Δ2-caryolic acid, royal jelly acid` — partial (王浆酸 got
  `royal jelly acid`), first term mangled.
- `10-羟基喜树碱` → expected `10-Hydroxy-camptothecin`; model output:
  `10-Oxylidobetuline` — completely different compound class.
- `10-脱乙酰基巴卡丁 III` → expected `10-Deacetyl baccatin III`; model output:
  `10-N-Acetylcarnitin III` — wrong compound.
- `1,10-菲咯啉[金属蛋白酶的抑制剂]` → expected `ophen` (data glitch in the
  reference itself); model output `1,11-Pyrolidine [Metalloproteinase
  inhibitor]` — the reference is degenerate here, worth noting.

**Driver:** the terms are absent from the seed TCM/Ayurveda glossaries; the
MeSpEn terms ARE loaded as binding constraints in this run (see ablation table
for the before/after effect: chrF 38.26 without MeSpEn bindings vs 81.66 with
them in the glossary-adherence run).

## 2. Hallucinated binomial — caught by G5

The gate flagged and blocked these (status `failed`; segments cannot reach
`auto_pass`):

- `10-羟基葵烯酸` → `10-Oxidosylkanoic acid` — gate detail:
  `unattested binomials: Oxidosylkanoic acid`.
- `1,10-菲咯啉[金属蛋白酶的抑制剂]` → `1,10-Pyrolidine [Metalloproteinase
  inhibitor]` — gate detail: `unattested binomials: Metalloproteinase
  inhibitor`.
- hallucination-check (source contains fabricated `Curcuma fabricata`,
  `Herba fictitia`, `Glycyrrhiza imaginaria`, `Panax fictionalis`): the model
  tends to **preserve** the fabricated names from the source; the gate catches
  them because they are absent from the glossary+registry.

**Caveat (over-blocking):** on th→en news text the gate also flagged 13–15
false positives of the shape `[Capitalized word] [past-tense verb]` —
e.g. `Some even`, `Congress said`, `Caucus said`, `This has`. These are
sentence-boundary artifacts of the `Genus species` regex, not species names.
They never **escaped** (0 escaped), so safety held, but G3/G5 precision on
general text is poor — see RECOMMENDATION.md conditions.

## 3. Hallucinated binomial — escaped

**None observed in v2.** G5_escaped = 0 on every dataset row run so far,
including the adversarial hallucination-check (criterion: escaped = 0 there).

## 4. Dosage / number corruption

Chemical locants are treated as disposable numbers:

- `1,2-萘醌` → `Naphthoquinone` — expected `1,2-Naphthoquinone`; gate detail:
  `source numbers missing in translation: 1, 2`.
- `1,4-萘醌` → `Naphthoquinone` — same failure mode (locant 1,4 dropped).
- `1,4-按树脑` → **empty output** — G2 failure (`empty translation`) plus
  numbers missing. Worst single failure in the set.
- `1,4-按树脑` variant rows repeat the pattern.

**Driver:** the 3B model drops IUPAC locants under glossary pressure; the G6
gate detects it reliably (4/4 caught).

## 5. Untranslated span

- classical-zh artifacts show the classical→modern rewrite as the scored
  artifact; the English output still contains the rewritten Chinese in
  `raw_output` (by design — G4 is n/a for the modern-Chinese target in v2).
- en→th row: `It has arisen because of plans to change the name of the
  assembly…` → model output `เพราะมีPlans to change the name of the assembly to
  the Welsh Parliament.` — mixed Thai/English: only the prefix was translated
  (residual script 9.72%). The 3B model code-switches on long sentences.
- Empty/failed outputs (`1,4-按树脑`) also surface here.

## 6. Segmentation error

**Not measured** — no gold segmentation annotation exists for these datasets.
Unit tests cover boundary behavior (CJK 。！？, Indic danda ।॥, Thai/Lao/Khmer);
boundary F1 is listed in NOT_VALIDATED.md.

## 7. Over-constrained / awkward translation

- With binding constraints ON, the model sometimes forces glossary renderings
  into wrong slots (see ablation table in the report for the G3-vs-chrF
  tradeoff).
- JSON protocol failures on th→th output (2 segments in the discarded run):
  `No JSON object in model response: '{\n "translation": "สมชัยกรรมการซึ่ Ma…'` —
  the 3B model malforms JSON when generating Thai strings with embedded quotes;
  the pipeline's parse-error path records the failure rather than silently
  accepting garbage.
- NTREX en→th: `Welsh AMs worried about 'looking like muppets'` → `เวสเทิร์น AMs
  ห่วง 'ดูเหมือนมุปุก้า'` — "Welsh" mistranslated as "Western" (เวสเทิร์น);
  loanword hallucination on the proper noun.

## 8. OCR failure

**Not run.** No OCR dataset was executed (both shortlisted Sanskrit OCR corpora
were inaccessible/unlicensed for use — see NOT_VALIDATED.md).

## Which dataset surfaced what

- **glossary-adherence (MeSpEn):** terminology miss (primary), hallucination
  caught, dosage corruption, empty output. Could not surface: true
  free-prose fluency issues (term-level items are not sentences).
- **classical-zh (Gare, n=3):** classical-stage rewrites; too small to surface
  distributional errors; surfaced the G4 n/a issue (fixed in harness).
- **NTREX en→th / th→en:** fluency floor, code-switching (untranslated spans),
  over-blocking false positives on G5, proper-noun mistranslation, JSON
  protocol failures. Could not surface: domain terminology.
- **hallucination-check:** adversarial preservation of fabricated binomials
  and the gate's catch behavior. Could not surface: subtle plausible-looking
  substitutions (the fabricated names are obvious).
- **usda-dosage:** dosage/number preservation on real ethnobotanical rows.
---

# v3 additions (2026-11-21)

## 9. G5 false positives (real detections from results/v3/g5_precision.csv)

The species-regex `[Capitalized] [lowercase]` matches sentence boundaries and
news entities. All 50 NTREX detections are false positives (precision 0%):

- `Congress said` (th-en idx=4) — "One member of the Workers' Congress said…";
  institution + verb, matched mid-sentence.
- `Some even` (th-en idx=1) — sentence-initial adverb phrase.
- `French people` (km-en idx=19) — demonym phrase; the sentence itself is a
  hallucination but the span is not species-name-like.
- `Khmu people` (lo-en idx=7) — ethnic-group name inside a wholly hallucinated
  sentence ("The Khmu people of Laos are involved in the production of soap"
  for a Welsh-politics source). FP for the species guardrail, but a genuine
  entity-level hallucination — evidence that G5 does not catch what actually
  went wrong here.
- `Ellos que` (th-en idx=17) — the model answered in **Spanish** ("Ellos que
  tienen derecho a votar…") for a Thai source; the regex matched the Spanish
  phrase. A severe language-switch failure that G5 labels as a "binomial".
- `Please provide` (hallucination-check idx=8) — imperative phrase from an
  instruction-following output.

Worse: 2 of the 3 glossary-adherence flags were **correct** renderings
(`10-Hydroxydecylenic acid`, `Hydroxydecenoic acid` — exact glossary
reference strings). The gate blocks right answers on chemical nomenclature.

## 10. G2 failures (empty and copy outputs)

The v3 audit premise said "20 of 48 usda-dosage outputs are empty." The
JSONLs show **0 empty and 20 verbatim copies** (hypothesis ≡ source). The
program's G2 gate counts both; the mechanism is copy, not empty:

- Copy (usda idx=6): src `Preparation of Frangula purshiana with dosage
  IC50=20-60 ug/ml` → hyp identical. en→en probe echo.
- Copy (usda idx=7): src `Preparation of Dioscorea pentaphylla with dosage
  FEMA 6,000` → hyp identical.
- Copy (usda idx=8): src `Preparation of Cistus ladaniferus with dosage
  MIC=800-1,600 ug/ml` → hyp identical.
- True empty (classical-zh idx=0): modern stage produced empty rewrite while
  the raw English output existed — the only genuine empty in the corpus.
- Copy (glossary-adherence idx=18): `13-顺-维甲酸` → `Ro acutane` matched its
  source-side glossary constraint verbatim (the source column contained Latin).

## 11. G6 dosage/number failures (real examples)

Genuine value corruption (safety-critical):
- usda idx=0: src `EC100=50 uM` → hyp `EC150 dosage = 50 uM` — the potency
  label **changed value** (100→150). Silent dosage corruption.
- usda idx=29: src `IC100=2 mM` → hyp `IC150=2 mM` — same corruption pattern.
- glossary idx=29: src `180° plane rotation pulse` → hyp `185度…` — 180→185.

Gate false positives / encoding shifts (number semantically kept or absent in
the reference too):
- glossary idx=18: `13-顺-维甲酸` → `Ro acutane` drops "13", but the gold
  reference is also `Ro acutane` — the reference itself omits the locant.
- glossary idx=1: `10-羟基-Δ2-葵烯酸` → `10-Hydroxydecylenic acid` — the Δ2
  locant is encoded inside the chemical name; gate flags "2" missing.
- usda idx=15: `750 mg/4x/day` → `750 mg taken four times` — numeric 4x
  rendered as a word.

Data-quality note: glossary idx=29 is an **inverted MeSpEn row** (English in
the source column, Chinese reference) — a dataset defect that surfaced only
because G6 flagged it.
