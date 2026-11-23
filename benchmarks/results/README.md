# benchmarks/results — what's kept, what was removed

Kept (the validation evidence this repository stands on):

- `flores/` — FLORES-200 devtest measurements for Qwen2.5-7B-AWQ, ShizhenGPT-7B-LLM and NLLB-200-3.3B (chrF++/BLEU/TER). See `../FLORES_COMPARISON.md`.
- `v3.2/` — final validation round: restored ablations, G4 revert, reclassified G5 `fp_class`, G2 rename+`G2_fail_mechanism`, `_provenance.csv`, reproducibility check. See `../VALIDATION_REPORT_v3_2.md`.

Removed 2026-11-23 (kept reachable in pushed git history; see `git log -- benchmarks/results`):

- `v2/` — first real-model run (241 segments). Superseded by v3/v3.2. Its per-segment JSONLs were the source evidence for the G6/G2/G5 findings; the findings and citations live on in `../METRICS.md`, `../ERROR_ANALYSIS.md`, `../VALIDATION_REPORT_v3*.md`.
- `v3/` — correction round; its ablations export defect was repaired in v3.2 (`_provenance.csv`).
- `v3.1/` — rejected round; three data-integrity defects retracted in v3.2.
- `v4/` — 7B probe (Qwen2.5-7B-AWQ and ShizhenGPT). Its headline conclusions (7B does not fix G6; ShizhenGPT does not beat Qwen on FLORES) are recorded in `../FLORES_COMPARISON.md` and the v4 commit messages.
- `v5/` — gate-fixed re-run of the 7B probe (fail-closed G6 routing only; identical metrics).
- `results.json` — stale duplicate of v2 `summary.json`.
- `repro_*` JSONLs (in v2/v3) — reproducibility probes; the reproducibility contract (deltas, byte-identical behaviour) is enforced by `benchmarks/reproduce_v3.sh` and recorded in v3.2's `reproducibility.json` / `script_tests.md`.

Nothing validated depends on the removed directories at runtime: `reproduce_v3.sh` reads `results/v3.2/` (or a `TMTRANS_P0_CSV`/`TMTRANS_P0_BASELINE` you supply) and `results/v2/` only for the optional label-completeness audit, which now fails closed with a pointer to this file when v2 is absent.
