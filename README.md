# tmtrans — validated traditional-medicine translation workbench

Local-server program for translating traditional medicine literature (TCM,
Ayurveda, and Southeast Asian ethnopharmacology) into English with **proper
validation and a RAG strategy** — not generic machine translation.

Built as a standalone workstream of the ethnopharm-ai / NP-Alpha project, in its
own repository, so corpus translation can proceed independently of the
discovery pipeline.

## Why not generic MT

**"Generic MT" means a general-purpose machine translation system** — one
trained to translate everything to everything, rather than specialised for a
domain or language pair. Google Translate, DeepL, and Meta's NLLB-200 are
generic MT: enormous parallel corpora, hundreds of language pairs, fluent
output on everyday text. The contrast in this repository is with
*domain-specialised* MT: models tuned for a domain (medical, legal, TCM) or
constrained at inference time by a glossary, memory, or terminology list.

Traditional medicine texts defeat generic MT on three counts:

1. **Domain vocabulary is thin.** Formula names (桂枝汤), materia medica terms,
   and concepts with no biomedical equivalent (qi, dosha, 归经) are poorly
   represented in generic training data. A generic model renders them as
   something plausible-sounding but wrong, or silently normalises them away.
2. **The dangerous failure mode is fluent hallucination, not obvious garbage.**
   A generic model can produce a perfectly grammatical English sentence that
   invents a Latin binomial for a herb it could not identify — e.g. writing
   *Glycyrrhiza fakensis* — and nothing in the fluency signals the fabrication.
   That is precisely what the G5 binomial gate and the accepted-species
   registry exist to catch.
3. **Generic models will not obey binding constraints.** You can prompt
   "use exactly this rendering," but a generic model is only loosely obedient
   to it. tmtrans treats the glossary as a hard constraint instead, then
   **verifies** compliance deterministically with gate G3 — rather than
   trusting the model to follow it.

The failure mode that matters most is **hallucinated binomials**. tmtrans is
built around preventing exactly that.

**Limit of the claim.** "Not generic MT" does not mean tmtrans is a better
translator in the abstract. Our own FLORES-200 numbers are 30–40 chrF++ —
below the published NLLB-200 anchor (~55) and below what a tuned MT system
achieves. What tmtrans adds is the enforcement layer on top of the model: no
unattested binomial, no dropped dosage, no glossary violation ships silently,
no matter which underlying model you use. That layer is only as good as the
glossary and the human review behind it — and it is not a substitute for
either.

## How it works

```
source text / file
      │
      ▼
segmentation (CJK 。！？, Indic danda ।॥, Thai/Khmer/Lao aware)
      │
      ▼
[optional] classical → modern stage   (文言文 → modern Chinese, etc.)
      │
      ▼
RAG retrieval
  ├─ glossary hits  → injected as BINDING prompt constraints
  └─ translation memory (TF-IDF char-ngram index over human-approved pairs)
      │
      ▼
LLM translation   (any OpenAI-compatible endpoint: vLLM / Ollama / LM Studio)
      │
      ▼
deterministic validation gates
  G2 non-empty / not a copy of source
  G3 every glossary rendering appears verbatim in the output
  G4 residual source-script detection (untranslated spans)
        — v3.2 fix: Latin-script sources (en/vi/id/ms/tl) no longer
          false-fail; a perfect Thai translation of English scored 1.0 before
  G5 binomial hallucination check against glossary + accepted-species registry
  G6 numbers / dosages preserved  — FAIL-CLOSED (v3.2): any dropped numeric
        token blocks auto_pass. 180°→185°-type corruptions cannot ship.
  G7 length-ratio plausibility
      │
      ▼
human review queue (bilingual editor in the web UI)
      │
      ├─ approved pairs feed the translation memory (RAG improves over time)
      └─ unmatched terms → dictionary-growth queue
      │
      ▼
exports: JSONL / JSON / CSV / XLSX / TXT with full validation + review provenance
```

The central rule: **a binomial is only ever emitted if it is attested in the
glossary or the accepted-species registry.** Unmatched herbs keep their source
name and enter a curation queue. Nothing is silently guessed.

## Quick start (local server)

Requires Python 3.10+.

```bash
git clone <this-repo> && cd ethnopharm-translate
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Point at your model server — Ollama by default:
export TMTRANS_BASE_URL=http://localhost:11434/v1
export TMTRANS_MODEL=qwen2.5:7b-instruct

# Or vLLM:
# export TMTRANS_BASE_URL=http://localhost:8000/v1
# export TMTRANS_MODEL=Qwen/Qwen2.5-7B-Instruct

tmtrans doctor          # checks endpoint + glossary
tmtrans serve           # web workbench on http://127.0.0.1:8765
```

Open **http://127.0.0.1:8765**: paste text or upload a file, watch validation
gates run per segment, review in the bilingual editor, approve, export.

### No GPU? Dry-run mode

```bash
export TMTRANS_BACKEND=mock
tmtrans serve
```

The mock backend echoes the source with glossary substitutions so you can
exercise the full pipeline, validation gates, review queue and exports without
any model. This is also how the test suite runs.

### NLLB-200 backend (optional, non-commercial)

```bash
pip install -e '.[nllb]'
export TMTRANS_BACKEND=nllb
export TMTRANS_NLLB_MODEL=facebook/nllb-200-3.3B
export TMTRANS_SRC_LANG=zho_Hans      # FLORES-200 code; e.g. san_Deva, tha_Thai, khm_Khmr
export TMTRANS_TGT_LANG=eng_Latn
tmtrans serve
```

NLLB-200 is Meta's dedicated machine-translation model, **not** an instruction
model. Practical consequences, all deliberate:

- It ignores the system prompt, the glossary block and the JSON output contract,
  so **binding glossary constraints are not applied** to NLLB output. Terms will
  frequently diverge from the glossary; G3 will flag them.
- It takes no direction hint from the prompt; you must set `TMTRANS_SRC_LANG`
  (a FLORES-200 code) yourself, e.g. `zho_Hans`, `san_Deva`, `tha_Thai`.
- It emits no term annotations (`terms` is always `[]`).
- Validation gates (G3, G5, G6, G7) still run unchanged, so you will see which
  segments fail review rather than getting silent corruption.
- The classical→modern rewrite stage is not meaningful for NLLB (no
  instruction-following); leave it off or use modern input.

**Licence:** NLLB-200 weights are **CC-BY-NC-4.0 (non-commercial)**. Installing
`tmtrans[nllb]` does not change the Apache-2.0 licence of this repository, but
using the NLLB backend makes that deployment non-commercial. If you ship a
product, use an OpenAI-compatible open-weight model instead (Qwen2.5, the
M2M-100 family, Madlad-400) or obtain a commercial licence from Meta.

### Docker

```bash
docker compose up --build
# workbench on http://localhost:8765; edit docker-compose.yml for vLLM vs Ollama
```

## OCR: manuscript scans → text

For woodblock classical Chinese, Devanagari palm leaves, Thai Samut Khoi
folding books, and printed pharmacopoeias, tmtrans adds an OCR front-end with
the same pluggable-backend design: any vision-language model behind an
OpenAI-compatible endpoint (vLLM), plus an offline mock for dry-runs.

```
scans/ (png/jpg/tiff…)
   │  natural page ordering
   ▼
[optional] surya line detection → line crops
   (keeps Thai Sara / Devanagari matras sharp on palm-leaf folios)
   │
   ▼
VLM transcription (script-aware prompts; vertical RTL columns for woodblock,
IAST output option for Sanskrit/Pali)
   │
   ▼
OCR JSONL  ←──── staging boundary: OCR finishes and exits,
   │              then the translation model takes the full VRAM
   ▼
tmtrans translate pages.jsonl --lang lzh   (or --translate to chain)
```

```bash
# Serve a vision model with vLLM (24GB GPU: fits in ~16GB BF16):
vllm serve Qwen/Qwen2.5-VL-7B-Instruct --max-model-len 16384

export TMTRANS_OCR_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
export TMTRANS_OCR_BASE_URL=http://localhost:8000/v1   # defaults to TMTRANS_BASE_URL

tmtrans ocr scans/ --lang lzh --reading-order rtl-columns          # OCR → JSONL
tmtrans ocr scans/ --lang sa --iast                                # Sanskrit → IAST
tmtrans ocr palmleaf/ --lang th --line-segmentation surya --translate
```

Or from the workbench: **OCR scans** tab → folder path, language, reading
order → runs as one background job (status `ocr` → `running`), page numbers
preserved on every segment as provenance.

### Verified model options (HF, Nov 2026)

| Purpose | Model | Notes |
|---|---|---|
| Unified all-script | `Qwen/Qwen2.5-VL-7B-Instruct` / `Qwen/Qwen3-VL-8B-Instruct` | 5–6M downloads; vertical text, multi-script layout |
| Compact document OCR | `PaddlePaddle/PaddleOCR-VL-1.6` (0.9B), `zai-org/GLM-OCR` | <4GB VRAM; leaves room for the translation LLM on the same GPU |
| Sanskrit | `diabolic6045/Sanskrit-Qwen2.5-VL-7B-Instruct-OCR`, `MuseMesh/sansar-ocr-2b`, `Piyush3142/trocr-sanskrit-ocr` (trained on `yzk/veda-ocr-ms`) | community fine-tunes — low adoption, validate on your folios before batch runs |
| Thai | `deepseek-ai/DeepSeek-OCR` (base), `sthaps/DeepSeek-ocr-Thai`, `openthaigpt/thai-trocr` | thai-trocr is Apache-2.0, the most adopted of the three |
| Sanskrit→EN translation model | `diabolic6045/Sanskrit-qwen-7B-Translate-v2` | same repo family as the Sanskrit OCR checkpoint |

Caveats: `ByteDance/AncientDoc` (sometimes recommended for vertical woodblock
fine-tuning) could not be found on HF — treat that pointer as stale. The
script-specific checkpoints above are single-author releases with 18–578
downloads; pin exact revisions and spot-check a few pages before batch OCR.

Line segmentation (`pip install 'tmtrans[ocr]'` for surya + Pillow) is
recommended for wide palm-leaf / Samut Khoi folios where full-page inference
blurs small diacritics; whole-page mode is fine for printed or high-resolution
scans, and Qwen2.5-VL handles vertical column ordering natively.

## CLI guide

Everything runs through the single `tmtrans` command after activating the
environment:

```bash
cd ethnopharm-translate
source .venv/bin/activate        # or call .venv/bin/tmtrans directly
```

### 1. Point it at your model

```bash
export TMTRANS_BACKEND=openai_compat   # or: mock | nllb
export TMTRANS_BASE_URL=http://localhost:11434/v1   # Ollama
export TMTRANS_MODEL=qwen2.5:7b-instruct
# vLLM instead:
#   TMTRANS_BASE_URL=http://localhost:8000/v1  TMTRANS_MODEL=Qwen/Qwen2.5-7B-Instruct

tmtrans doctor     # checks endpoint reachability + glossary load
```

For OCR, set `TMTRANS_OCR_MODEL` (default `Qwen/Qwen2.5-VL-7B-Instruct`,
served with `vllm serve Qwen/Qwen2.5-VL-7B-Instruct --max-model-len 16384`);
it reuses `TMTRANS_BASE_URL` unless `TMTRANS_OCR_BASE_URL` is set.

No GPU handy? `export TMTRANS_BACKEND=mock TMTRANS_OCR_BACKEND=mock` runs the
entire pipeline offline for testing.

### 2. Subcommands

| Command | What it does |
|---|---|
| `tmtrans serve` | Web workbench at http://127.0.0.1:8765 (`--host/--port` to change) |
| `tmtrans translate <file>` | Translate txt/md/html/pdf/OCR-JSONL into bilingual exports |
| `tmtrans ocr <folder>` | OCR a folder of scans to JSONL, optionally chain into translation |
| `tmtrans export <doc_id>` | Re-export a document from the database |
| `tmtrans glossary import/stats/export` | Manage the bilingual dictionary |
| `tmtrans doctor` | Health check |

Global flags on any subcommand: `--db` (default `data/tmtrans.db`) and
`--dictionary path.csv` (repeatable; defaults to the seed glossaries).

### 3. Typical workflows

**Plain text file:**

```bash
tmtrans translate chapter.txt --lang lzh --variant classical --out outputs/
```

`--lang` accepts `zh, lzh, sa, pi, hi, ta, th, km, lo, my, vi, id, ms, tl`;
classical variants insert a classical→modern rewrite stage before English
translation. Output: `outputs/<doc_id>.jsonl`, `.csv` and `.json` with
per-segment validation reports; the doc ID is printed at the end.

**Manuscript scans (OCR → translate in one chained run):**

```bash
tmtrans ocr scans/ --lang lzh --reading-order rtl-columns --translate
# palm-leaf / Samut Khoi, line-crop mode for small diacritics:
tmtrans ocr palmleaf/ --lang sa --iast --line-segmentation surya --translate
```

Or stage them separately (sequential VRAM use on one GPU): drop `--translate`,
then later run `tmtrans translate outputs/ocr-<ts>.jsonl --lang lzh` — the
JSONL is a durable checkpoint, so you can retranslate without re-OCR'ing.

**Review and final export:** CLI translate writes its database to
`outputs/tmtrans-cli.db`, and approval is a human step done in the web UI —
open that same database in the workbench:

```bash
tmtrans serve --db outputs/tmtrans-cli.db
# ... approve/edit segments in the browser ...
tmtrans export <doc_id> --fmt xlsx --db outputs/tmtrans-cli.db            # colour-coded review sheet
tmtrans export <doc_id> --fmt jsonl --approved-only --db outputs/tmtrans-cli.db   # final corpus, approved only
```

The `--db` flag is the one gotcha: `export` defaults to `data/tmtrans.db`
(what `serve` uses), while CLI-translated documents live in the out-dir
database — pass the right one.

**Dictionary:**

```bash
tmtrans glossary stats                        # entries by language/category
tmtrans glossary import my_terms.csv          # appended to data/dictionary/custom.csv, effective immediately
tmtrans glossary export --out outputs/glossary.csv
```

The CLI never marks anything "approved" — that is deliberate. `auto_pass`
from the validation gates is not acceptance; only your approval in the review
UI promotes segments, and only approved pairs feed the RAG translation memory
and the `--approved-only` exports.

## The dictionary is the backbone

`data/dictionary/*.csv` — seed glossaries for TCM (~50 entries), Ayurveda
(~50), and SE-Asian traditions (~35), each with source form, variants, English
rendering, accepted binomial, family, tradition, and pharmacopoeia reference.
Columns:

```
entry_id, category, source_lang, source_form, variants(|), english,
binomial, inchikey, family, tradition, pharmacopoeia, notes
```

- Add your own curated entries to `data/dictionary/custom.csv` (or via
  `POST /api/glossary` / `tmtrans glossary import`). They take effect immediately.
- Unmatched terms encountered during translation accumulate in
  **Term candidates** in the UI — resolve them into curated entries rather than
  accepting model output.
- **NP-Alpha linkage:** export the accepted binomials from the Gate-A LOTUS
  registry (one per line) and point `paths.registry` at it in
  `config/default.yaml`. The hallucination gate then accepts registry-attested
  binomials, keeping translation consistent with the discovery chain's
  InChIKey-keyed universe. The `inchikey` column is reserved for this linkage.

## Measured model performance (Nov 2026)

FLORES-200 devtest, eng→tha and eng→zho_Hans, chrF++ (sacrebleu, word_order=2),
1012 segments each, temperature 0, run 2026-11-23. Full write-up:
`benchmarks/FLORES_COMPARISON.md`. Raw outputs: `benchmarks/results/flores/*.json`.
FLORES-200 text is not committed (CC-BY-SA-4.0); reproduce with
`benchmarks/run_flores.py` after `benchmarks/datasets/fetch_flores.sh`.

| Model (quantization) | eng→tha chrF++ | eng→zho_Hans chrF++ | Notes |
|---|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | 30.34 | 26.58 | general instruction LLM |
| ShizhenGPT-7B-LLM (Q4_K_M) | 28.92 | 24.14 | TCM-fine-tuned; ~no gain over Qwen on these dirs |
| **NLLB-200-3.3B** | **40.49** | 22.43 | dedicated MT; CC-BY-NC-4.0 (non-commercial) |
| NLLB-200 (published, eng→high-resource) | 54.9 | 54.9 | paper anchor; same setup not reproduced here |

How to read this:

- **No candidate model is adequate for unsupervised translation.** All three
  measured models sit 24–40 chrF++ — far below NLLB's published high-resource
  anchor (~54.9). These are quantized 3–7B models with a plain prompt; the
  gap is expected, not a bug.
- **NLLB wins Thai (+10 over the 7B LLMs) but loses Chinese (22.4 vs 26.6).**
  Do not assume "specialised MT beats general LLM" from the Thai number alone.
- **chrF++ is surface overlap, not safety.** It would not have caught the
  180°→185° dosage corruption — that is what the G6 gate is for. Model choice
  does not substitute for the validation gates or human review.
- **NLLB-200-3.3B is available as an optional backend** (`TMTRANS_BACKEND=nllb`,
  `pip install 'tmtrans[nllb]'`) but is CC-BY-NC-4.0 — non-commercial. It is a
  raw seq2seq model: it ignores the system prompt, the glossary block, and the
  JSON output contract, so binding glossary constraints do NOT apply to its
  output. Use it only for baseline/benchmark purposes or if your deployment is
  non-commercial; the OpenAI-compatible path remains the supported one.
- **ShizhenGPT-7B-LLM showed no measurable gain** over Qwen2.5-7B on these two
  directions; its TCM fine-tuning did not transfer to FLORES-style encyclopedic
  Thai/Chinese. Keep it only if the TCM-domain glossary adherence is what you
  need and you've verified it yourself.

Avoid zero-adoption community MT checkpoints for production. The prompt-level
glossary constraint does the heavy lifting; the model needs to be good at
following structured JSON instructions more than anything else.

## Validating the program (`tmtrans eval`)

Segment gates validate individual translations; **program validation** runs the
whole pipeline against held-out reference pairs and scores it. Three routes:

```bash
# 1. Classical→modern stage, scored against a public parallel set
#    (Gare/Classical_Chinese_to_Modern_Chinese, via the HF datasets-server API):
tmtrans eval classical-zh --limit 100

# 2. Any HF dataset with parallel fields — e.g. the en↔zh medical parallel set:
tmtrans eval hf:jundai2003/medical-insights-en-zh \
    --source-field narrative_zh --target-field narrative --lang zh --limit 50

# 3. Your own gold set (JSONL with source/target keys, or CSV) — the recommended
#    domain route: export human-approved segments, have an expert correct them,
#    and reuse it as a recurring regression suite:
tmtrans eval gold.jsonl --lang lzh --variant classical
```

Outputs: corpus **chrF++** and **BLEU** (zh tokenizer for Chinese), plus the
program's safety statistics — validation-gate outcome distribution,
**binomial-hallucination errors (G5 — must stay 0)**, reference-binomial recall
(of the Latin binomials in the reference, how many survive in the output),
length-ratio sanity, and a per-segment JSONL for error analysis
(`outputs/eval-*.segments.jsonl`).

Interpretation: chrF/BLEU measure fluency+adequacy against references; the
safety metrics measure what actually ruins a traditional-medicine corpus.
A run with high chrF but nonzero hallucination errors is a *failed* run.

Notes:
- Gated datasets (e.g. BhashaBench) work once you accept their terms on the
  HF page and `export HF_TOKEN` — the loader authenticates automatically.
- No `datasets` library needed; rows come from the datasets-server HTTP API
  with pagination (`--limit`).

## Evaluation resources (verified)

- `Gare/Classical_Chinese_to_Modern_Chinese` — public classical↔modern parallel
  data; the `classical-zh` adapter validates the classical stage end-to-end.
- `jundai2003/medical-insights-en-zh` — en↔zh parallel medical insights
  (`narrative` / `narrative_zh`); medical-domain MT validation via the `hf:`
  adapter.
- `michaelwzhu/ShenNong_TCM_Dataset` — **correction:** its HF release is
  `query`/`response` dialogue/instruction data, not a parallel translation
  test set. Useful for domain QA-style evaluation of the underlying model,
  not for scoring this pipeline's translations.
- `bharatgenai/BhashaBench-Ayur` / `-Multi` — gated (auto-approval) MCQ/QA
  benchmarks for Ayurvedic knowledge; evaluation of model knowledge, not MT.
- `FreedomIntelligence/TCM-Pretrain-Data-ShizhenGPT` + `TCM-Instruction-Tuning-ShizhenGPT` —
  domain corpora if you later fine-tune.
- ChiMed 2.0 (arXiv 2507.15275) is a pretraining/SFT/RLHF corpus that *includes*
  TCM classics — useful for domain adaptation, not a translation dataset.

## Validation philosophy

Gates are **deterministic**, not LLM-judged, so validation is reproducible.
`auto_pass` means "no gate fired", not "correct" — human review is the
acceptance step, and only human-approved pairs enter the RAG memory. This
keeps the retrieval loop from amplifying its own errors.

## Layout

```
src/tmtrans/
  ocr.py         manuscript OCR: VLM backends, reading order, surya line crops, JSONL
  segment.py     segmentation with CJK/Indic awareness + PDF/HTML/TXT/OCR-JSONL ingestion
  lang.py        language profiles, classical-stage decisions, IAST folding
  dictionary.py  bilingual terminology store (herbs/formulas/diseases/concepts)
  rag.py         TF-IDF char-ngram translation memory + glossary retrieval
  prompts.py     binding-glossary prompt construction, tolerant JSON parsing
  backend.py     OpenAI-compatible client (vLLM/Ollama/...) + mock + NLLB-200
  translate.py   orchestration, self-repair retries, classical stage
  validate.py    the seven deterministic gates
  db.py          SQLite: documents, segments, reports, term candidates
  service.py     background jobs, review→memory loop
  server.py      FastAPI app
  export.py      JSONL/JSON/CSV/XLSX/TXT with provenance
  evaluation.py  program validation: HF/local reference sets, chrF/BLEU + safety metrics
  schemas/       translation-record JSON Schema
  web/static/    single-page workbench UI
data/dictionary/ seed glossaries (TCM / Ayurveda / SE-Asian)
tests/           offline end-to-end suite (mock backend)
```

## Development

```bash
export TMTRANS_BACKEND=mock
pytest            # 49 offline tests (mock backends, no model needed)
```

Note: the 49 tests exercise the gates with the mock backend only; they do not
validate any model's translation quality. For model-level numbers see
`benchmarks/FLORES_COMPARISON.md` and `benchmarks/VALIDATION_REPORT_v3_2.md`,
including two unresolved P0 safety findings (G2 copy rate 42% on usda-dosage,
G6 numeric corruption class) that human review does not waive.

## Current status and known limitations (Nov 2026)

This project is in **active validation**, not production. Honest state of the
evidence, so nobody over-claims:

**Measured, same harness, three models on FLORES-200** (1012 segments × 2 dirs):

| Model | eng→tha chrF++ | eng→zho_Hans chrF++ |
|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | 30.34 | 26.58 |
| ShizhenGPT-7B-LLM (Q4_K_M) | 28.92 | 24.14 |
| NLLB-200-3.3B | 40.49 | 22.43 |

**Validation P0s open:** G2 non-empty/copy gate failed on usda-dosage (42%
verbatim copies — the gate now decomposes empty vs copy); G6 numeric-token
corruption class (180°→185°) is now fail-closed but the underlying model still
produces such errors — they are caught, not prevented.

**G5 (binomial hallucination) precision is poor** (0% NTREX / 40% adversarial,
single labeller). The gate currently operates as a block-on-detection, not a
discriminator; treat every G5 fire as "review needed", not "hallucination
proven".

**OCR layer is engineering-tested only**, not benchmark-validated (no CER/WER
yet). **Human review is the acceptance step** — `auto_pass` is not approval.
**Commercial use:** the optional NLLB backend and FLORES-200-derived artifacts
carry non-commercial licences; the core package does not.

If you are evaluating whether to adopt this: the pipeline is sound, the gates
catch real failures, and the honest ceiling on unconstrained translation is
"assist + human review". For anything dosage-bearing, that review is
mandatory, not optional.

## License

Apache-2.0, except where noted:

- `tmtrans[nllb]` optional extra pulls in Meta's NLLB-200 weights
  (**CC-BY-NC-4.0 — non-commercial use only**). The extra is optional and
  installing it does **not** relicense this repository, but NLLB inference in
  your deployment makes that deployment non-commercial. See
  `benchmarks/datasets/LICENSES_AND_ATTRIBUTION.md`.
- FLORES-200 (benchmark data) is fetched at runtime, never committed,
  CC-BY-SA-4.0; attribution in the same file.

Seed glossary entries are curated from public pharmacopoeial
nomenclature; verify against your regional pharmacopoeia before clinical use.
**Not for clinical decision-making.**
