# Dataset files in benchmarks/datasets/ — licensing and attribution

This directory holds dataset extracts used by the validation harness
(`benchmarks/run_v2.py`). License strings below are verbatim from the HF API
audit (`benchmarks/results/v2/hf_license_audit.json`).

## Committed here (with attribution)

| File | Source | License (verbatim) | Attribution |
|---|---|---|---|
| `mespen_zh_en.tsv` | `FrancophonIA/MeSpEn_Glossaries` → `Chinese_English_medglossaries.tsv` | `"cc-by-4.0"` | MeSpEn medical bilingual glossaries (FrancophonIA/MeSpEn_Glossaries). © its authors. Licensed CC BY 4.0 — reuse with attribution. |
| `mespen_en_th.tsv` | same → `English_Thai_medglossaries.tsv` | `"cc-by-4.0"` | same |
| `usda_ethno_sample_400.json` | `wirthal1990-tech/USDA-Phytochemical-Database-JSON` → `ethno_sample_400.json` | `"cc-by-4.0"` | USDA Phytochemical & Ethnobotanical Database, free 400-row sample (v2.4.0). Licensed CC BY 4.0. The full 76,907-row registry is commercial and is NOT included or used. |
| `gare_cache.json` | `Gare/Classical_Chinese_to_Modern_Chinese` (3 parallel pairs) | `"mit"` | Gare classical→modern Chinese parallel data. MIT license. |
| `ntrex_128.py` | `SEACrowd/ntrex_128` loader script (Apache-2.0 per file header) | `"cc-by-sa-4.0"` (dataset) | script only; the data itself is not committed (below) |

## NOT committed — fetched at runtime by reproduce.sh / run_v2.py

| Files | Source | License (verbatim) | Why not committed |
|---|---|---|---|
| `ntrex_eng_src.txt`, `ntrex_tha.txt`, `ntrex_lao.txt`, `ntrex_khm.txt` | `MicrosoftTranslator/NTREX` (via SEACrowd/ntrex_128) | `"cc-by-sa-4.0"` | CC BY-SA 4.0 is share-alike/copyleft and is incompatible with committing the data into this Apache-2.0 repository (same reasoning as DFKI-SLT/BotanicalNER, `"gpl-3.0"`, which was dropped entirely). Per-segment **derived outputs** (benchmarks/results/v2/*.jsonl) are the validation evidence and are committed; the source references are fetched at runtime. |

To reproduce the NTREX runs, `benchmarks/reproduce.sh` downloads these four
files from `https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128/newstest2019-{src.eng,ref.tha,ref.lao,ref.khm}.txt`
(42k-word news test references, Federmann et al. 2022, CC BY-SA 4.0).

## Not used / not included

- `DFKI-SLT/BotanicalNER` (`"gpl-3.0"`): dropped — copyleft incompatible with
  this repo; substituted by the USDA CC BY 4.0 species list in
  `data/validation_registry.txt` (334 accepted names).
- `snskrt/Sanskrit-OCR-Parallel-Corpus`: HF API returns 401 — license
  unverifiable; excluded.
- `deliciosodemente/holistic` (gated) and `xs12345/TCM-Ancient-Modern-Open`
  (parallel content not public): not used.
## FLORES-200 devtest (NOT committed — fetched at runtime)

| Item | Value |
|---|---|
| File | `flores200_dataset/` (devtest/ & dev/, 204 languages each) |
| Source | `https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz` (Meta AI, NLLB, arXiv:2207.04672) |
| License | FLORES-200 is released by Meta for research use; attribution required. Redistribution in this repo is intentionally avoided. |
| Fetch | `benchmarks/datasets/fetch_flores.sh` |
| Use | `benchmarks/run_flores.py` — computes chrF++ / spBLEU / BLEU / TER against eng_Latn source |

No FLORES-200 text is committed. Only derived metrics (chrF++, spBLEU) are reported, in aggregate.

## NLLB-200 model weights (NOT committed — optional backend)

| Item | Value |
|---|---|
| Model | `facebook/nllb-200-3.3B` (and -600M / -1.3B / -54B) |
| License | **CC-BY-NC-4.0 — non-commercial use only** |
| Fetched | at install/run time from the Hugging Face Hub; never committed |
| Used by | `tmtrans[nllb]` optional backend (`TMTRANS_BACKEND=nllb`) |
| Implication | Using the NLLB backend makes that deployment **non-commercial**. The rest of this repository remains Apache-2.0; installing the extra does not relicense the project, but it obliges you to comply with the model licence for anything produced with it. |
| Citation | NLLB Team, "No Language Left Behind: Scaling Human-Centered Machine Translation", arXiv:2207.04672 |
