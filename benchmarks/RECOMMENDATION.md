# Recommendation — ethnopharm-translate (tmtrans), intended use: corpus-translation input layer for ethnobotanical discovery

## Verdict: **APPROVE WITH CONDITIONS** (retained from v2; conditions revised in v3)

## Verdict language (v3, canonical)

Pipeline is functionally validated on gate mechanics; two safety-threshold
failures (G2 empty/copy outputs, G6 dosage preservation) block deployment on
dosage-bearing text; G5 escape = 0 on samples tested but detection precision
requires remediation.

## Justification (numbers)

The safety floor held: G5_escaped = 0/63 across all rows including the
adversarial set (10 generated, 10 caught). But v3 surface corrections change
the risk picture: G2 fails 42% of usda-dosage rows (20/48 verbatim copies,
1/3 classical-zh true empty), G6 fails the pre-registered zero-tolerance
threshold on 2 of 3 applicable rows (glossary-adherence 0.80, usda-dosage
0.875; non-copy rates 0.793/0.786), and three of the G6 failures are genuine
dosage-value corruptions (EC100→EC150, IC100→IC150, 180°→185°). G5 detection
precision is 0% on news text (0 TP / 50 FP) and 40% on the adversarial set —
escape=0 is a floor, not evidence of accuracy. chrF≥40 fails on 7/10 rows
(6/8 quality rows) at 3B. RAG glossary retrieval is the dominant quality
factor where an applicable glossary exists (81.66→38.16 off); no measurable
effect where none applies.

## Conditions

### P0 — blocks deployment on dosage-bearing text

1. **G6 (dosage preservation) fails zero-tolerance** on glossary-adherence
   (80%) and usda-dosage (87.5%). Do not deploy on dosage-bearing text until
   G6 pass rate = 1.0 or a fail-closed behavior (reject any segment with a
   missing/altered numeric token) is implemented. The EC100→EC150 /
   IC100→IC150 value-corruption pattern must be eliminated specifically.
2. **G2 empty/copy outputs at 42% on usda-dosage** (20/48) and 1/3 on
   classical-zh. The 3B model produces empty output on the classical stage
   and verbatim copies on en→en probes. The pipeline must fail closed on
   empty output, or the model must be upgraded, before any dosage-bearing or
   classical text is processed.

### P1 — required before claiming validated translation behavior

3. **G5 precision fixes:** the species regex false-positives sentence
   boundaries and news entities (precision 0% on NTREX news, 40% on the
   adversarial set; it even blocked 2 correct chemical renderings). A
   dictionary-attested-genus filter or two-token NER is required before
   deployment on non-biology text. Until then G5 is a species-name guardrail
   requiring an in-domain source.
4. **Human-review validation:** not performed in v2 or v3. A scored review
   session (adequacy/fluency, acceptance rate, edit distance) is required.

### P2 — characterization gaps

5. **Non-Qwen model run required** to characterize model-family variance;
   all current numbers come from a single 3B checkpoint. A 7B-class model
   (Qwen2.5-7B-Instruct or ShizhenGPT-7B) run is also required to test
   whether the chrF<40 and G2/G6 failures are model-size artifacts.
6. **Larger classical-zh gold set** (Gare is n=3 with inferred parallelism).

## Not blocking, unresolved

- OCR CER/WER: unvalidated (datasets inaccessible — NOT_VALIDATED.md).
- G5 entity-level hallucination detection: not attempted (the guardrail missed
  real entity hallucinations it was not designed to see).
- MeSpEn inverted-row defects: the glossary-adherence set inherits them.

**Bottom line:** the escape-rate safety property is supported; two
safety-threshold failures (G2, G6) block deployment on dosage-bearing text.
Approved as a corpus-intake tool with mandatory human review and the P0
remediations above; not approved as an autonomous translator.