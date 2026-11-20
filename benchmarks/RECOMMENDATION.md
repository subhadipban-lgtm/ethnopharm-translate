# Recommendation — ethnopharm-translate (tmtrans), intended use: corpus-translation input layer for ethnobotanical discovery

## Verdict: **APPROVE WITH CONDITIONS**

### Justification (numbers only)

On a real model run (`mlx-community/Qwen2.5-3B-Instruct-4bit`, temperature 0,
seed 42), the workbench's zero-escape property for binomial species names held
exactly: **G5_escaped = 0/63 across all 10 dataset rows**, including the
adversarial hallucination-check (10 generated, 10 caught, 0 escaped — the
correct success criterion for adversarial data) and non-adversarial rows where
the gate caught 3 (glossary-adherence), 5 (en→lo), 15 (th→en), 16 (lo→en) and
14 (km→en) candidates with zero escapes. Glossary binding is the dominant
quality factor: removing RAG retrieval drops glossary-adherence chrF 81.66 →
38.16; removing the classical→modern stage drops classical-zh chrF 3.32 → 0.00.
G6 dosage-preservation passed 1.0 on all rows except usda-dosage (0.875) and
glossary-adherence (0.80 — chemical locants dropped). Reproducibility delta on
classical-zh chrF is 0.00 across two runs.

### Conditions (must hold before production corpus ingestion)

1. **G5 over-blocking must be fixed for free-prose output**: on
   ×→en news text the `Genus species` regex false-positives sentence-boundary
   pairs ("Some even", "Congress said" — 15/25, 16/25, 14/25 rows flagged on
   th/lo/km→en). Zero escapes, but the review queue will flood; precision fix
   (e.g. two-token NER or dictionary-attested-genus filter) required.
2. **Model upgrade required**: all quality numbers are from a 3B 4-bit model.
   classical-zh chrF = 3.32 is failure-level for the classical→modern stage;
   rerun with the recommended 7B-class model (Qwen2.5-7B-Instruct or
   ShizhenGPT-7B) before signing off translation quality.
3. **G6 fixes**: IUPAC locant preservation (1,2-/1,4- prefixes) and the
   empty-output case (1,4-按树脑) must be handled; 4/30 glossary rows and 6/48
   USDA rows dropped numbers.
4. **Human review validation**: not performed in this run (no reviewer scored
   segments). Required before claiming the review workflow is fit for purpose.
5. **Gare classical-zh has n = 3** — the classical stage needs a larger
   expert-annotated gold set (the protocol's expert gold-set plan) before any
   claim about classical-text translation quality.

### Not blocking, but unresolved

- OCR CER/WER: unvalidated (datasets inaccessible — see NOT_VALIDATED.md).
- TCM-specific model comparison column: not produced (no 7B runtime here).
- HalluEntity-based detector calibration: not performed.

**Bottom line:** the safety mechanism (G5) is supported by the numbers in this
run; translation quality is conditional on a larger model and the fixes above.
The system is approved as a *corpus-intake tool with mandatory human review*,
not as an autonomous translator.