# What Was NOT Validated in This Run (validation/v2)

Branch: `validation/v2` · Date: 2026-11-20

Everything below is **explicitly unvalidated**. Nothing in
`VALIDATION_REPORT_v2.md` claims coverage of these items.

## 1. Model scope

- **TCM-specific model (ShizhenGPT-7B-LLM or equivalent): NOT run.**
  No GPU inference stack for a 7B model was available in this environment
  (no vLLM, no Ollama; the only reachable runtime was mlx-lm on Apple MPS).
  The real-model runs use `mlx-community/Qwen2.5-3B-Instruct-4bit` — a general
  model at 3B parameters, **smaller** than the 7B-class models the workbench
  README recommends. All quality numbers are lower-bound estimates for the
  recommended configuration. A second column with a TCM-specific model was
  requested by the protocol and **could not be produced**.
- **Sanskrit-specific translation model** (`diabolic6045/Sanskrit-qwen-7B-Translate-v2`):
  not run (same GPU constraint). No Sanskrit dataset category was executed.

## 2. Dataset categories not run with a real model

- **Ayurveda / Sanskrit terminology checks: NOT run.** No accessible parallel
  Ayurvedic benchmark with a compatible license was confirmed; the shortlisted
  Sanskrit OCR corpora were blocked (below).
- **TCM-specific parallel benchmark: only n=3 available.** The Gare dataset
  (MIT) is a genuine parallel corpus but contains **only 3 (source, reference)
  pairs** (6 interleaved rows). The classical-zh translation-quality numbers
  are based on n=3; no statistical claim is licensed. The previously
  shortlisted `xs12345/TCM-Ancient-Modern-Open` was excluded because its
  parallel content is **not public** (metadata only) — using it would have
  violated the protocol's dataset rules.
- **`deliciosodemente/holistic` (EHSD, Ayurveda subset): NOT used.** Gated
  dataset requiring HF information-sharing consent (auto-gated). Per the
  license/access protocol, gated datasets were not pulled in this run.
- **`samuelyeh/HalluEntity`: NOT executed.** Listed as a future calibration
  resource for the G5 detector only; no entity-level detector calibration was
  performed. The G5 numbers in the report come from binomial matching against
  the accepted-species registry, not from HalluEntity.
- **`AIX-Text/TerminologyDataset`: NOT used.** Per-language coverage for
  zh/lo/km unverified.

## 3. OCR pipeline: NOT validated

No CER/WER numbers were produced. The OCR front-end was not run against any
manuscript dataset in this validation. Protocol and Sanskrit OCR datasets were
identified but **both shortlisted OCR datasets are unusable**:
- `snskrt/Sanskrit-OCR-Parallel-Corpus`: HF API returns **401 Unauthorized** —
  license and contents unverifiable; excluded per protocol.
- `Process-Venue/Sanskrit-OCR-Typed-Dataset`: not verified/used.
The OCR feature is therefore **engineering-tested only** (11 unit tests with a
mock OCR backend), not benchmark-validated.

## 4. Human review: NOT validated

"Human review: not validated in this run." No human reviewer scored segments;
no adequacy/fluency ratings, acceptance rate, or inter-annotator agreement
exist. The acceptance-rate threshold in `METRICS.md` is pre-registered but
unmeasured. Only one human (the repo author) was available and no scoring
session was conducted.

## 5. Commercial / excluded data

- **USDA full registry (76,907 rows): commercial, NOT used.** Only the
  400-row free sample (`ethno_sample_400.json`, CC BY 4.0) is used, and of
  those 400 rows only **48 contain dosage fields**. The G6 dosage results rest
  on 48 probes.
- **`DFKI-SLT/BotanicalNER`: NOT used.** License is **GPL-3.0 (copyleft)** —
  corrects the previous "commercial-only" misstatement. GPL-3.0 data cannot be
  committed into this Apache-2.0 repository, and derived results are ambiguous
  under copyleft; the dataset was dropped. Substitute: species list from the
  USDA CC BY 4.0 sample + curated glossary binomials
  (`data/validation_registry.txt`, 334 names).

## 6. Languages not run

- NTREX-128 was run **only for en→th, en→lo, en→km** (25 sentences each in
  this run, of 1,997 available). The other 124 languages were not run.
- Vietnamese, Indonesian, Malay, Tagalog, Pali, Hindi, Tamil, Burmese: **no
  dataset category run** in this validation.

## 7. Gates not exercised

- Segmentation boundary F1 / exact-match: **not measured** (no gold
  segmentation annotation; unit tests cover behavior only).
- OCR gates: not measured.
- G7 is computed but its threshold is weakly informative for term-level
  glossary items (single-term outputs have extreme length ratios by design);
  glossary-adherence G7 rates must be read in that light.

## 8. Blockers encountered and their effect

1. **No Ollama/vLLM/LM Studio** on this machine initially (all three default
   endpoints unreachable). Resolved for the purpose of Part B by installing
   `mlx-lm 0.32.2` and serving
   `mlx-community/Qwen2.5-3B-Instruct-4bit` (4-bit quantized, MLX format,
   Apple GPU) at `http://localhost:8099/v1` with `temperature=0`. This is a
   real OpenAI-compatible model run, but on a smaller model than recommended.
2. **Gare dataset is tiny** (n=3 parallel pairs). Not a blocker per the
   protocol ("if a dataset is not a parallel corpus, do not use it as a
   translation-quality benchmark"); it IS parallel, but the sample size
   constrains all classical-zh claims.
3. **Sanskrit OCR dataset access blocked** (401). OCR CER/WER validation is
   blocked; documented above.