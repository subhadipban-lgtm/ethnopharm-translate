# FLORES-200 comparison anchor — tmtrans models vs published NLLB-200

Status: **in progress** — Qwen2.5-7B-AWQ measured; ShizhenGPT-7B pending.
See `benchmarks/results/flores/` for the raw outputs. Do not quote numbers
from this file until marked complete.

## What this is

The internal benchmarks (NTREX-128 subsets, MeSpEn glossary adherence,
usda-dosage, classical-zh) measure task fit and gate behavior. They do NOT
measure general translation quality against a published reference point, and
none of them is comparable to anything in the literature.

FLORES-200 (devtest, 1012 segments) is the standard benchmark used by NLLB-200
(NLLB Team et al., 2022, "No Language Left Behind", arXiv:2207.04672). Running
the same two directions for our models lets us state, in the same units
(chrF++, sacrebleu word_order=2), how far we are from a published,
human-anchored system — and, more importantly, whether the gap is consistent
with the models being general 7B LLMs rather than MT systems.

## Published anchor (NLLB-200, FLORES-200 devtest, chrF++)

From NLLB-200 paper, Table 33 (devtest, eng_Latn → xx):

| direction | bucket | chrF++ |
|---|---|---|
| eng → all (avg) | — | 45.3 |
| eng → all (avg), high-resource | high | 54.9 |
| eng → all (avg), low-resource | low | 41.9 |
| eng → all (avg), very low | v.low | 39.5 |

For context, Table 34 shows NLLB-200 vs Google Translate on low/very-low-resource
directions: Google 32.3 (low) / 27.0 (v.low) vs NLLB 30.3 / 25.7. Thai and
Simplified Chinese are **high-resource** languages in NLLB's taxonomy, so the
relevant anchor is closer to ~54.9 chrF++ for eng→xx high-resource, not the
low-resource rows.

## Our numbers (same devtest, same chrF++)

| model | eng→tha_Thai chrF++ | eng→zho_Hans chrF++ |
|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | 30.34 | 26.58 |
| ShizhenGPT-7B-LLM (Q4_K_M) | pending | pending |
| NLLB-200 (paper, eng→high-resource avg) | ~54.9 (reference) | ~54.9 (reference) |

## How to read this

- Our models are **general instruction-tuned LLMs**, not dedicated MT systems.
  A ~24-28 point gap to NLLB-200 on high-resource directions is expected and is
  consistent with the published gap between generic LLMs and purpose-built MT.
- The comparison is direction-asymmetric: eng→tha and eng→zho_Hans are
  **outbound** directions; the models are strongest into English.
- chrF++ rewards character n-gram overlap; it does not measure factual
  fidelity. A high score would not have caught the G6 dosage corruptions
  (180°→185°) that this project exists to prevent.
- Quantization: Qwen2.5-7B-AWQ is 4-bit AWQ; ShizhenGPT is Q4_K_M GGUF. Both
  are below the paper's fp16/bf16 baselines, which accounts for a portion of
  the gap.
- Prompt: plain "translate this text" system prompt, temperature 0, no
  few-shot, no domain glossary. Not an upper bound.

## What this does NOT show

- It does not validate the TCM/ethnopharmacology domain. FLORES is
  Wikipedia-domain news/general text.
- It does not license any claim about Lao, Khmer, or Pali, which NLLB rates
  low/very-low-resource and where we have no FLORES numbers.
- It does not absolve the P0 findings (G6 dosage, G2 copies). Those are gate
  failures, not benchmark failures, and they are orthogonal to chrF++.

## Reproducing

```
bash benchmarks/datasets/fetch_flores.sh
python benchmarks/run_flores.py --backend openai_compat \
  --model <model-id> --directions eng_Latn->tha_Thai,eng_Latn->zho_Hans \
  --out benchmarks/results/flores/<model>.json
```
FLORES-200 is CC-BY-SA-4.0 (Meta AI). The dataset is fetched at runtime and
never committed; only aggregate scores are committed.
