# v4 — larger-model probe (2026-11-22)

Two open-weight 7B models run through the SAME harness, prompts, gates and
G5 accounting as the 3B baseline. Not a new benchmark round; a scaling check.

| Model | Runtime | Quant | Notes |
|---|---|---|---|
| Qwen2.5-7B-Instruct-AWQ | vLLM on Colab L4 (24 GB) | AWQ (4-bit) | vLLM 0.34.0 |
| ShizhenGPT-7B-LLM (Apache-2.0, TCM fine-tune of Qwen2.5-7B) | llama.cpp on Colab L4 | Q4_K_M GGUF | llama-cpp-python 0.3.37 |

## Numbers (chrF / BLEU / TER)

| dataset            | Qwen2.5-3B (v3) | Qwen2.5-7B | ShizhenGPT-7B-LLM |
|--------------------|-----------------|------------|-------------------|
| classical-zh  (n=3) | 3.32 / 0.0 / 100 | 4.28 / 0.0 / 100 | **13.95 / 0.0 / 66.67** |
| glossary-adherence (n=30) | 81.66 / 55.8 / 37.84 | **89.21 / 61.6 / 32.43** | 78.28 / 73.8 / 35.14 |
| ntrex-128-en-th (n=25) | 24.56 / 2.72 / 120.31 | **29.93 / 3.65 / 92.97** | 26.50 / 5.50 / 102.34 |

Caveats:
- Classical-zh n=3 — no significance; the ShizhenGPT jump is suggestive only.
- Different quantization (AWQ vs Q4_K_M) and different serving stacks; small
  deltas (<2 chrF) are not meaningful.
- ShizhenGPT's training data includes TCM text, so its advantage on
  glossary-adjacent classical Chinese is expected, not a general capability win.
- G6 (numeric preservation) is unchanged in severity and still fails on the
  same chemical-locant cases — scaling did not fix the dominant corruption
  class. G6 is now fail-closed in code (see src/tmtrans/validate.py).
- chrF on en->th remains far below usable quality for all three models.

Artifacts: raw JSONL per segment + summary.json per model. Nothing here is
wired into the release path; all runs used the pre-fix G4 gate (reported as
n/a by the harness for non-English targets) and pre-fail-closed G6.
