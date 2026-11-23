# FLORES-200 vs NLLB-200 — where our models actually stand

**Date:** 2026-11-23 · **Status:** complete (both models measured) · **Data:** FLORES-200 devtest (1012 segments), CC-BY-SA-4.0, not committed; fetch with `benchmarks/datasets/fetch_flores.sh`.

## Headline

Both 7B models we run score **~27–30 chrF++** on eng→tha and **~24–27 chrF++** on
eng→zho_Hans. NLLB-200, a dedicated translation model, scores **~45–55** on
high-resource eng→xx. The gap is not noise and not a prompt bug — it is the
expected difference between a general instruction-tuned LLM and a purpose-built
multilingual MT system, and it is the single most important number in this
repository for deciding what the system can and cannot do.

## Numbers (FLORES-200 devtest, chrF++ via sacrebleu word_order=2, temp=0)

| model | eng→tha chrF++ | eng→tha BLEU | eng→zho_Hans chrF++ | eng→zho_Hans BLEU |
|---|---|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | 30.34 | 3.63 | 26.58 | 2.10 |
| ShizhenGPT-7B-LLM (Q4_K_M, GGUF) | 28.92 | 3.65 | 24.14 | 2.78 |
| NLLB-200 (paper, eng→high-resource avg) | 54.9 | — | 54.9 | — |
| NLLB-200 (paper, eng→all avg) | 45.3 | 27.1 | 45.3 | 27.1 |
| NLLB-200 (paper, eng→low-resource avg) | 41.9 | 23.1 | 41.9 | 23.1 |

Thai and Simplified Chinese are **high-resource** in NLLB's taxonomy, so the
fair anchor is ~54.9, not the low-resource row.

## How to read this honestly

1. **The gap is real and large (~25–28 chrF++).** A 3-point difference between
   our two models is within run-to-run/prompt noise; a 25-point gap to NLLB is
   not.
2. **chrF++ is not adequacy.** A model can score 30 chrF++ and be fluent but
   wrong on dosages and species names — which is exactly what our G6/G5 gates
   exist to catch. These numbers bound *surface translation quality*, not
   *safety*.
3. **Not comparable to our earlier numbers.** NTREX en→th (29.93, 25 segments,
   news domain) and this FLORES number (30.34, 1012 segments) are consistent
   with each other but neither is comparable to the classical-zh or glossary
   numbers, which are different tasks.
4. **Not comparable to Google/NLLB headline figures without caveats.** We ran
   4-bit quantized general LLMs with a plain prompt, no few-shot, no
   domain glossary, no NLLB tokenizer. A properly prompted or fine-tuned run
   would likely do better; this is a floor, not a ceiling.
5. **BLEU is reported for completeness only.** The BLEU values (2–4) are far
   below chrF++ because BLEU is harsh on morphologically rich languages and
   short outputs; do not read them as "worse than the chrF++ suggests."
6. **TER ~100–190** indicates outputs roughly twice as long as references or
   heavily reordered — consistent with chatty, explanatory translations rather
   than faithful ones.

## What this changes (and what it does not)

- **Changes:** any claim that "the models are good enough for production
  translation" is not supported. They are not, for unconstrained text.
- **Does not change:** the gate architecture's value — G5/G6 catch failures
  regardless of chrF++. It also does not invalidate the constrained
  glossary-adherence setting, where output is short, templated, and checked.
- **Practical implication:** for open-ended translation, either accept heavy
  human post-editing, use NLLB/M2M100/Madlad as the base model, or restrict
  scope to term-level output with human review.

## Reproduce

```
bash benchmarks/datasets/fetch_flores.sh   # downloads FLORES-200 (not committed)
python benchmarks/run_flores.py --model <id> \
  --directions eng_Latn->tha_Thai,eng_Latn->zho_Hans \
  --out benchmarks/results/flores/<model>.json
```

Raw outputs: `benchmarks/results/flores/qwen28awq_flores.json`,
`benchmarks/results/flores/shizhen_flores.json`. FLORES-200 text is not in
this repo (CC-BY-SA-4.0); only aggregate metrics are.
