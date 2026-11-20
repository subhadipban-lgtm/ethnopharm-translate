# Validation Report v2 — ethnopharm-translate (tmtrans)

Branch: `validation/v2` · Date: 2026-11-21 · Pre-registered thresholds: `benchmarks/METRICS.md`

## 1. Executive summary

Real-model validation (`mlx-community/Qwen2.5-3B-Instruct-4bit`, temperature 0, seed 42) on 10 dataset rows / 209 segments: **G5_escaped = 0/63** (adversarial hallucination-check 10/10/0; non-adversarial rows 3–16 catches per row, 0 escapes). G3 glossary pass rates 0.90–1.00. G6 dosage pass 1.0 on 8/10 rows (0.80 glossary-adherence, 0.875 usda-dosage). chrF++ (95% bootstrap CI): glossary-adherence 81.66 [67.68, 94.06]; usda-dosage 64.75 [62.18, 67.1]; th→en 43.53 [38.32, 48.19]; en→th 24.56 [20.19, 28.41]; en→lo 5.44 [3.07, 8.02]; classical-zh 3.32 [0, 13.05] (n=3). Ablations: RAG off drops glossary-adherence chrF to 38.16; classical stage off drops classical-zh chrF to 0.0. Reproducibility delta 0.00. Recommendation: **approve with conditions** (see §10).

## 2. Environment

| Item | Value |
|---|---|
| Repository | https://github.com/subhadipban-lgtm/ethnopharm-translate |
| Base commit (main) | `8a39fcc` |
| Validation branch | `validation/v2` |
| Python | 3.15.2 (venv `.venv`, macOS 26.5.1 arm64, Apple GPU) |
| Real model | `mlx-community/Qwen2.5-3B-Instruct-4bit` (4-bit MLX quantization) |
| Endpoint | `http://localhost:8099/v1` (mlx-lm 0.32.2 server) |
| Temperature / seed | 0.0 / 42 (Python + NumPy); bootstrap 1,000 resamples |
| TCM-specific model | **not available** in this environment (no 7B GPU runtime) |
| Offline test count | **42** (pytest tail below) |

Commands (exact):

```bash
# offline suite
TMTRANS_BACKEND=mock TMTRANS_OCR_BACKEND=mock python -m pytest tests/ -q
# real-model main run (10 dataset rows)
export TMTRANS_BASE_URL=http://localhost:8099/v1 TMTRANS_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit TMTRANS_TEMPERATURE=0
python3 -u benchmarks/run_v2.py --backend real --model mlx-community/Qwen2.5-3B-Instruct-4bit --limit-mespen 30 --limit-ntrex 25
# ablations + reproducibility rerun
python3 -u benchmarks/stage2_ablations.py
# table assembly
python3 benchmarks/collect_v2.py
```

`pytest -q` tail:

```
..........................................                               [100%]
42 passed in 0.53s
```

## 3. Dataset table (license strings verbatim from HF API, 2026-11-20 audit)

| Dataset | HF API license string | Gated | Used for | n used |
|---|---|---|---|---|
| Gare/Classical_Chinese_to_Modern_Chinese | `"mit"` (cardData), `license:mit` (tag) | no | classical-zh (parallel, 3 pairs) | 3 |
| FrancophonIA/MeSpEn_Glossaries | `"cc-by-4.0"` | no | glossary-adherence + binding glossary | 30 |
| SEACrowd/ntrex_128 → MicrosoftTranslator/NTREX files | `"cc-by-sa-4.0"` | no | en→th/lo/km + reverse fluency floor | 25×6 |
| wirthal1990-tech/USDA-Phytochemical-Database-JSON | `"cc-by-4.0"` (**400-row free sample only**; full 76,907-row registry commercial, not used) | no | usda-dosage + G5 registry seed | 48 |
| hand-built adversarial set | n/a (authored for this validation) | — | hallucination-check | 10 |
| samuelyeh/HalluEntity | `"mit"` | no | listed only; not executed | — |
| AIX-Text/TerminologyDataset | `"mit"` | no | listed only; not executed | — |
| snskrt/Sanskrit-OCR-Parallel-Corpus | unverifiable (HF API **401 Unauthorized**) | unknown | **excluded** | 0 |
| DFKI-SLT/BotanicalNER | `"gpl-3.0"` (copyleft; corrects earlier "commercial-only") | no | **dropped** — GPL-3.0 incompatible with this Apache-2.0 repo; substituted by USDA CC BY 4.0 species list (334-name registry) | 0 |

Gare split check: HF datasets-server reports `config=default, split=train` with feature `text`; rows alternate `古文：…` / `现代文：…` — **a genuine parallel (source, reference) corpus**, but only 6 rows = 3 pairs.

## 4. Results table (Part C; chrF++/BLEU with 95% bootstrap CI, seed=42, B=1000)

| dataset | model | n | chrF++ | CI | BLEU | CI | TER | G3 | G4 | G5 gen/caught/escaped | G6 | G7 | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classical-zh | Qwen2.5-3B-4bit | 3 | 3.32 | [0, 13.05] | 0.00 | [0, 0] | 100.00 | n/a | n/a | 0/0/0 | 1.0 | 1.0 | classical→modern vs 现代文 refs; n=3 |
| glossary-adherence | Qwen2.5-3B-4bit | 30 | 81.66 | [67.68, 94.06] | 55.82 | [30.82, 81.05] | 37.84 | 0.90 | 0.933 | 3/3/0 | 0.80 | 1.0 | MeSpEn zh→en terms |
| hallucination-check | Qwen2.5-3B-4bit | 10 | 39.68 | [30.54, 48.39] | 2.29 | [1.38, 3.42] | 139.62 | 0.90 | 1.0 | **10/10/0** | 1.0 | 0.9 | adversarial: escaped=0 is the criterion |
| ntrex-128-en-th | Qwen2.5-3B-4bit | 25 | 24.56 | [20.19, 28.41] | 2.72 | [0.9, 4.58] | 120.31 | 1.0 | n/a | 0/0/0 | 1.0 | 1.0 | news domain |
| ntrex-128-th-en | Qwen2.5-3B-4bit | 25 | 43.53 | [38.32, 48.19] | 16.82 | [10.57, 23.26] | 80.65 | 1.0 | 1.0 | 15/15/0 | 1.0 | 1.0 | G5 over-blocking (false positives) |
| ntrex-128-en-lo | Qwen2.5-3B-4bit | 25 | 5.44 | [3.07, 8.02] | 0.27 | [0.11, 0.45] | 483.04 | 1.0 | n/a | 5/5/0 | 1.0 | 1.0 | Lao output weak |
| ntrex-128-lo-en | Qwen2.5-3B-4bit | 25 | 23.41 | [21.63, 25.13] | 4.76 | [1.94, 7.41] | 100.61 | 1.0 | 1.0 | 16/16/0 | 1.0 | 1.0 | G5 over-blocking |
| ntrex-128-en-km | Qwen2.5-3B-4bit | 25 | 15.44 | [13.52, 17.59] | 1.56 | [0.93, 2.52] | 104.35 | 1.0 | n/a | 0/0/0 | 1.0 | 1.0 | |
| ntrex-128-km-en | Qwen2.5-3B-4bit | 25 | 27.09 | [24.46, 29.53] | 3.96 | [2.07, 5.76] | 102.85 | 1.0 | 1.0 | 14/14/0 | 1.0 | 1.0 | G5 over-blocking |
| usda-dosage | Qwen2.5-3B-4bit | 48 | 64.75 | [62.18, 67.10] | 33.50 | [28.81, 37.91] | 112.55 | 1.0 | 1.0 | 0/0/0 | **0.875** | 1.0 | dosage probes; 48 rows with dosage fields |

Raw numbers: `benchmarks/results/v2/summary.csv` (+ per-segment JSONL per row).
CI method: nonparametric bootstrap over segments, 1,000 resamples, seed 42 — `benchmarks/METRICS.md`.
**BLEU threshold decision:** `BLEU ≥ 5` removed as pass/fail criterion; BLEU reported descriptively only (no defensible NLLB/M2M baseline exists for these pairs — see METRICS.md).

### Pass/fail vs pre-registered thresholds (per dataset × criterion)

| dataset | chrF≥40 | G3=1.0 | G4≥0.95 | G5 claim (gen=0) | G5 safety (esc=0) | G6=1.0 | G7≥0.95 |
|---|---|---|---|---|---|---|---|
| classical-zh (n=3) | **FAIL** (3.32) | n/a | n/a | PASS (0/0/0) | PASS | PASS | PASS |
| glossary-adherence | PASS (81.66) | **FAIL** (0.90) | **FAIL** (0.933) | **FAIL** (gen=3) | PASS (esc=0) | **FAIL** (0.80) | PASS |
| hallucination-check | — (adversarial) | **FAIL** (0.90) | PASS | n/a (adversarial) | **PASS** (esc=0/10) | PASS | **FAIL** (0.90) |
| ntrex-128-en-th | **FAIL** (24.56) | PASS | n/a | PASS (0/0/0) | PASS | PASS | PASS |
| ntrex-128-th-en | PASS (43.53) | PASS | PASS | **FAIL** (gen=15) | PASS (esc=0) | PASS | PASS |
| ntrex-128-en-lo | **FAIL** (5.44) | PASS | n/a | **FAIL** (gen=5) | PASS (esc=0) | PASS | PASS |
| ntrex-128-lo-en | **FAIL** (23.41) | PASS | PASS | **FAIL** (gen=16) | PASS (esc=0) | PASS | PASS |
| ntrex-128-en-km | **FAIL** (15.44) | PASS | n/a | PASS (0/0/0) | PASS | PASS | PASS |
| ntrex-128-km-en | **FAIL** (27.09) | PASS | PASS | **FAIL** (gen=14) | PASS (esc=0) | PASS | PASS |
| usda-dosage | PASS (64.75) | PASS | PASS | PASS (0/0/0) | PASS | **FAIL** (0.875) | PASS |

Notes: (a) The two G5 columns are distinct pre-registered rules. **G5 safety (G5_escaped = 0) holds on every row, including the adversarial set — the core zero-tolerance property.** The G5 claim rule (G5_generated = 0 on non-adversarial rows) fails on 5/10 rows; per ERROR_ANALYSIS.md §2 the "generated" candidates on the ×→en rows are predominantly regex false positives (sentence-boundary pairs such as "Congress said"), not species-name inventions — the claim-threshold failure is confounded by detector imprecision and is listed as Recommendation condition 1. (b) `hallucination-check` G3 = 0.90 and G7 = 0.90 **fail** their thresholds (G3 = 1.0 zero-tolerance; G7 ≥ 0.95) — one glossary-binding miss and one length-ratio outlier in the 10-row adversarial set; its own zero-tolerance rule (G5_escaped = 0) still passes. (c) G3 = 1.0 fails on glossary-adherence (0.90) because 3/30 rows produced candidates the gate flagged; per-row binding is enforced via `failed` status, corpus rate 0.90. (d) chrF≥40 fails on 6/8 scoreable rows — **the quality floor is not met by the 3B model**; this is a model-size limitation, recorded in Limitations and the Recommendation conditions. (e) Reproducibility: delta 0.00 ≤ 2.0 — PASS.

### Part A — G5 framing, explicitly

| dataset | adversarial? | G5_generated | G5_caught | G5_escaped | escape rate |
|---|---|---|---|---|---|
| classical-zh | no | 0 | 0 | 0 | n/a (gen=0) |
| glossary-adherence | no | 3 | 3 | 0 | 0/3 = 0.0 |
| hallucination-check | **yes** | 10 | 10 | 0 | 0/10 = 0.0 |
| ntrex-128-en-th | no | 0 | 0 | 0 | n/a (gen=0) |
| ntrex-128-th-en | no | 15 | 15 | 0 | 0/15 = 0.0 |
| ntrex-128-en-lo | no | 5 | 5 | 0 | 0/5 = 0.0 |
| ntrex-128-lo-en | no | 16 | 16 | 0 | 0/16 = 0.0 |
| ntrex-128-en-km | no | 0 | 0 | 0 | n/a (gen=0) |
| ntrex-128-km-en | no | 14 | 14 | 0 | 0/14 = 0.0 |
| usda-dosage | no | 0 | 0 | 0 | n/a (gen=0) |

Corrected statement replacing the previous "zero on 3/5; 1/5 had hallucinations":
- Non-adversarial: G5_escaped = 0/53 (3 rows have gen=0; 5 rows generated 3–16 unattested binomial-shaped candidates, all caught).
- Adversarial: G5_escaped = 0/10 (criterion G5_escaped = 0 — **met**; criterion G5_generated = 0 not applicable here).
- Phrase used: "zero escapes", not "zero hallucinations" (hallucinations were generated on 6/10 rows).
- **Definition fix + verification:** the accounting was corrected mid-run to treat glossary *English renderings* as attested (not only glossary binomials + registry), per the v2 definition. All 18 JSONL files were re-scored with the corrected definition; counts are identical (total generated 63 → 63, caught 63 → 63, escaped 0 → 0). The tables above use the corrected definition.

## 5. Ablation table (Part D)

| dataset | condition | chrF++ | BLEU | G3 | G4 | G5 gen/caught/escaped | G6 |
|---|---|---|---|---|---|---|---|
| classical-zh | baseline (RAG+binding+classical) | 3.32 | 0.00 | n/a | n/a | 0/0/0 | 1.0 |
| classical-zh | rag_off | 3.32 | 0.00 | n/a | n/a | 0/0/0 | 1.0 |
| classical-zh | binding_off | 3.32 | 0.00 | n/a | n/a | 0/0/0 | 1.0 |
| classical-zh | classical_off | **0.00** | 0.00 | n/a | n/a | 0/0/0 | 1.0 |
| glossary-adherence | baseline | **81.66** | 55.82 | 0.90 | 0.933 | 3/3/0 | 0.80 |
| glossary-adherence | rag_off | **38.16** | 14.21 | 1.00 | 1.00 | 2/2/0 | 0.867 |
| glossary-adherence | binding_off | 82.61 | 56.00 | 0.90 | 0.933 | 4/4/0 | 0.767 |

Interpretation: RAG glossary retrieval is the dominant quality mechanism (chrF −43.5 when off). The classical→modern stage is necessary for literary Chinese (chrF 3.32 → 0.00 without). Binding constraints at the prompt level show no measurable effect on this term-level dataset beyond what RAG retrieval already provides (82.61 vs 81.66 within noise), but both keep G5_escaped = 0.

## 6. Human review (Part E)

**Human review: not validated in this run.** No human reviewer scored segments; no adequacy (1–5) / fluency (1–5) ratings, acceptance rate, or edit distance were measured. One potential reviewer only (repo author); no review session was conducted, so inter-annotator agreement is not applicable and is not reported.

## 7. Error analysis

Full taxonomy with real outputs: `benchmarks/ERROR_ANALYSIS.md`. Headline categories and where they surfaced: terminology miss (glossary-adherence, 5+ examples), hallucinated binomial caught (glossary-adherence + hallucination-check, 3+ examples), dosage corruption (glossary-adherence + usda-dosage, 4 examples), untranslated span/code-switching (en→th), G5 over-blocking false positives (th/lo/km→en, 15/16/14 rows), JSON protocol failure on Thai output. Segmentation errors and OCR failures: not measured/not run.

## 8. Reproducibility

- Seed 42 (Python + NumPy); temperature 0; identical command run twice on classical-zh: run1 chrF = 3.32, run2 chrF = 3.32, **abs delta = 0.00** (≤ 2.0 threshold — pass).
- Command: `python3 -u benchmarks/stage2_ablations.py` (rerun block), model `mlx-community/Qwen2.5-3B-Instruct-4bit`, endpoint `http://localhost:8099/v1`.
- Caveat: deterministic on this MLX/backend version; not guaranteed across backend upgrades.

## 9. Limitations and threats to validity

Full list: `benchmarks/NOT_VALIDATED.md`. Key items:

1. **Model**: 3B 4-bit, not the 7B-class recommended configuration; classical-zh chrF 3.32 = failure-level for the classical stage at this size. No TCM-specific model column (ShizhenGPT not runnable here).
2. **classical-zh n = 3** — no statistical claim licensed; expert gold-set plan required (see NOT_VALIDATED §2).
3. **Human review** not validated (Part E).
4. **OCR** not validated; both Sanskrit OCR datasets inaccessible (401) or unlicensed for use.
5. **G5 over-blocking** on general prose (sentence-boundary false positives) — safety held (0 escapes) but review-queue precision is poor on non-domain text.
6. **USDA**: only the 400-row free sample (48 dosage rows) used; the full 76,907-row registry is commercial and was not used. G6 rests on 48 probes (plus 30 MeSpEn rows).
7. **BotanicalNER dropped** (GPL-3.0 copyleft vs Apache-2.0 repo); registry substituted from USDA CC BY 4.0 sample + curated glossary binomials (334 names).
8. **NTREX** is news-domain (fluency floor only, not ethnobotanical quality); 25 sentences per language of 1,997 available; other 124 languages not run.
9. **G3 n/a on classical-zh** (scored artifact is modern Chinese; English renderings not applicable).
10. **Gated/datasets-server gaps**: `deliciosodemente/holistic` gated (not pulled); `xs12345/TCM-Ancient-Modern-Open` excluded (parallel content not public).

## 10. Recommendation

**APPROVE WITH CONDITIONS** — details and the five conditions in `benchmarks/RECOMMENDATION.md`. The G5 zero-escape property is supported by this run's numbers; translation quality is conditional on a larger model, G5-precision and G6 fixes, human-review validation, and a larger classical-zh gold set.

## 11. Deliverables

| Deliverable | Path |
|---|---|
| Numeric results table (Part C) | `benchmarks/results/v2/summary.csv` |
| Ablation table (Part D) | `benchmarks/results/v2/ablations.csv` |
| Machine-readable dump | `benchmarks/results/v2/summary.json` |
| Per-segment outputs (10 main + 7 ablation + 1 rerun) | `benchmarks/results/v2/*.jsonl` |
| Metric/threshold document | `benchmarks/METRICS.md` |
| Error taxonomy with real examples | `benchmarks/ERROR_ANALYSIS.md` |
| Non-validated list | `benchmarks/NOT_VALIDATED.md` |
| Recommendation | `benchmarks/RECOMMENDATION.md` |
| Reproduction script | `benchmarks/reproduce.sh` |
| Harness code | `benchmarks/run_v2.py`, `benchmarks/collect_v2.py`, `benchmarks/stage2_ablations.py` |
| Dataset cards (exact license strings) | `benchmarks/cards/*.json` |
| HF license audit | `benchmarks/results/v2/hf_license_audit.json` |
| Accepted-species registry (334 names) | `data/validation_registry.txt` |
| New gold sets created | hand-built adversarial set (10 rows, in `run_v2.py:load_hallu`, authored for this validation — Apache-2.0, same repo) |