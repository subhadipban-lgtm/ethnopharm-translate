# FLORES-200 vs NLLB-200 — where our models actually stand

**Date:** 2026-11-23 · **Status:** complete (three models measured, same harness, same devtest) · **Data:** FLORES-200 devtest (1012 segments), CC-BY-SA-4.0, not committed; fetch with `benchmarks/datasets/fetch_flores.sh`.

## Headline

On eng→tha and eng→zho_Hans, our two 7B instruction LLMs land at **24–30 chrF++**,
while NLLB-200-3.3B — a dedicated translation model — scores **40.5** (tha) and
**22.4** (zho_Hans). NLLB wins Thai decisively (+10 over Qwen, +11.6 over
ShizhenGPT) but **loses** on Chinese (22.4 vs Qwen's 26.6, ShizhenGPT's 24.1).
Neither result is near the published NLLB high-resource anchor (~54.9 chrF++),
which tells you these FLORES subsets are hard for everyone under this prompting
setup, or that the published anchor reflects a different prompting/training regime.

## Numbers (FLORES-200 devtest, chrF++ via sacrebleu word_order=2, temp=0)

| model | eng→tha chrF++ | eng→tha BLEU | eng→zho_Hans chrF++ | eng→zho_Hans BLEU |
|---|---|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | 30.34 | 3.63 | 26.58 | 2.10 |
| ShizhenGPT-7B-LLM (Q4_K_M, GGUF) | 28.92 | 3.65 | 24.14 | 2.78 |
| **NLLB-200-3.3B** | **40.49** | **5.44** | **22.43** | **1.44** |
| NLLB-200 (paper, eng→high-resource avg) | 54.9 | — | 54.9 | — |
| NLLB-200 (paper, eng→all avg) | 45.3 | 27.1 | 45.3 | 27.1 |
| NLLB-200 (paper, eng→low-resource avg) | 41.9 | 23.1 | 41.9 | 23.1 |

Raw outputs: `benchmarks/results/flores/{qwen28awq,shizhen,nllb3b}_flores.json`.

## How to read this honestly

1. **NLLB wins Thai, loses Chinese.** Thai (+10 chrF++) is the expected NLLB
   advantage — it is a dedicated seq2seq MT model with far more parallel Thai
   data than a general chat model. Chinese is high-resource *for NLLB's
   training*, yet NLLB scores *below* our 7B chat models here. Do not
   extrapolate "NLLB is better" from the Thai number; on this run it is not.
2. **All three are far below the published 54.9 high-resource anchor.** Part of
   the gap is prompting: we used a plain system prompt for the LLMs and NLLB's
   default greedy/beam setup, not NLLB's published beam config or the paper's
   exact inference settings. Part is that these are 4-bit/7B models. Treat the
   absolute numbers as a floor, not a verdict on NLLB-200 as a system.
3. **chrF++ is surface overlap, not adequacy.** None of these numbers measures
   whether dosages, species names, or route-of-administration survive — which
   is the entire point of G5/G6 in this repo. A high chrF++ would not have
   caught the 180°→185° corruption. Do not use this table to argue safety.
4. **Thai and Chinese are both classed high-resource** in NLLB's taxonomy, so
   the ~54.9 anchor is the right reference, not the 41.9 low-resource row.
   Both our LLMs and our NLLB run sit well below it — consistent with a
   generic-prompt, quantized, 3–7B setup rather than a tuned MT system.
5. **TER is reported but uninformative here** (119–356 across rows); it is
   dominated by output-length differences between chat-style and seq2seq models.
6. **BLEU (1.4–5.4) is near floor for all rows.** Reported for completeness
   only; chrF++ is the primary metric (see METRICS.md).

## What this changes, and what it does not

- **Changes:** If the target product ever needs raw FLORES-style translation
  quality, NLLB-200-3.3B is a strictly better Thai engine than our current
  default and is a legitimate candidate backend. It is also non-commercial
  (CC-BY-NC-4.0), which may rule it out for a shipped product — see
  `pyproject.toml` and `benchmarks/datasets/LICENSES_AND_ATTRIBUTION.md`.
- **Does not change:** the gate architecture, the G6 dosage-corruption
  problem, or the conclusion that these models are unsuitable for unreviewed
  clinical text. NLLB is also a raw seq2seq model: it ignores prompts, the
  glossary, and the JSON contract, so it cannot be dropped into the current
  pipeline without the translation-quality loss those stages exist to prevent.
- **Does not license a deployment decision.** All three models fail the
  human-review bar for dosage-bearing ethnobotanical text. This table ranks
  MT systems; it does not certify any of them.

## Reproduce

```
bash benchmarks/datasets/fetch_flores.sh   # FLORES-200, not committed (CC-BY-SA-4.0)
python benchmarks/run_flores.py --backend openai_compat --model Qwen/Qwen2.5-7B-Instruct-AWQ \
  --directions eng_Latn->tha_Thai,eng_Latn->zho_Hans --out results/flores/qwen28awq_flores.json
python benchmarks/run_flores.py --backend nllb --model facebook/nllb-200-3.3B \
  --src-lang eng_Latn --directions eng_Latn->tha_Thai,eng_Latn->zho_Hans \
  --out results/flores/nllb3b_flores.json
```
