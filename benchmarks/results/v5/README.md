# v5 — gate-fixed re-run of the 7B probe (2026-11-23)

Same harness, same Qwen2.5-7B-Instruct-AWQ (vLLM on L4), same three datasets,
temperature 0. Purpose: measure the effect of the two gate fixes landed after
the v4 probe — G6 numbers gate is now fail-closed (severity=error) and the G4
residual-script gate no longer mis-fires on Latin sources.

## Results (chrF / BLEU / TER)

| dataset | v4 (pre-fix) | v5 (post-fix) | Δ |
|---|---|---|---|
| classical-zh (n=3) | 4.28 / 0.0 / 100.0 | 4.28 / 0.0 / 100.0 | 0.0 |
| glossary-adherence (n=30) | 89.21 / 61.6 / 32.43 | 89.21 / 61.61 / 32.43 | 0.0 |
| ntrex-128-en-th (n=25) | 29.93 / 3.65 / 92.97 | 29.78 / 3.65 / 92.97 | -0.15 |

chrF/BLEU/TER are properties of the model output and are unchanged by the
gate fixes (the −0.15 on en-th is vLLM run-to-run jitter, not a code change).

## What the gate fix changes: downstream segment disposition

Fail-closed G6 converts silent numeric corruption into explicit failure:

| dataset | auto_pass | failed | G6 failures |
|---|---|---|---|
| classical-zh (n=3) | 2 | 1 | 0 |
| glossary-adherence (n=30) | 20 | 10 | 6 (idx 1, 5, 12, 15, 18, 27) |
| ntrex-128-en-th (n=25) | 24 | 1 | 1 (idx 10: source "2017" dropped) |

Before the fix, the 6 glossary-adherence numeric corruptions passed the gate
silently into the output. Now those segments are marked failed and route to
review instead of shipping. This is the intended effect of the fail-closed
change; it is not a regression in model quality — chrF is unchanged.

## Caveats

- n is small; classical-zh n=3 tells us nothing about quality change.
- The same G6 failures persist (locant/angle tokens the model drops). The gate
  now catches them deterministically; it does not make the model stop making
  them.
- en-th chrF ~30 remains far below usable quality for unsupervised release.
