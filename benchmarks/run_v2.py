"""Validation v2 runner — real-model and mock runs with G5 accounting.

Produces:
  benchmarks/results/<run>/<dataset>_<backend>.jsonl   per-segment outputs
  benchmarks/results/<run>/summary.csv                 Part C table
  benchmarks/results/<run>/ablations.csv               Part D table
  benchmarks/results/<run>/summary.json                full machine-readable dump
  (historically: results/v2 ... removed from tree in the 2026-11-23 cleanup;
   see benchmarks/results/README.md)

G5 accounting (per dataset):
  G5_generated : binomial candidates in the hypothesis absent from the
                 glossary AND the accepted-species registry
  G5_caught    : of those, the ones the program's hallucination gate flagged
  G5_escaped   : generated - caught (the safety-relevant number)
  G5_escape_rate = escaped / generated (or n/a when generated = 0)

Bootstrapped 95% CIs: resample segments with replacement, 1000 iterations,
seed=42 (see benchmarks/METRICS.md).

Usage:
  TMTRANS_TEMPERATURE=0 python benchmarks/run_v2.py --backend real
  python benchmarks/run_v2.py --backend mock
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import time
from pathlib import Path

import sacrebleu

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "benchmarks" / "datasets"
OUT = ROOT / "benchmarks" / "results" / "v2"
OUT_SAVE = OUT  # default output dir; main() may redirect per backend

SEED = 42
N_BOOT = 1000

_BINOMIAL_RE = re.compile(r"\b[A-Z][a-z]{3,}\s+[a-z][a-z-]{2,}\b")


def set_seed(s: int = SEED) -> None:
    random.seed(s)
    try:
        import numpy as np
        np.random.seed(s)
    except ImportError:
        pass


# --------------------------------------------------------------------------
# dataset loaders
# --------------------------------------------------------------------------

def load_gare() -> list[tuple[str, str, str]]:
    """Gare/Classical_Chinese_to_Modern_Chinese (MIT). 6 interleaved rows = 3 pairs.

    Uses a local cache (benchmarks/datasets/gare_cache.json) so the suite is
    reproducible offline; falls back to the HF datasets-server API only when
    the cache is missing."""
    cache = DATA / "gare_cache.json"
    if cache.exists():
        return [(p["source"], p["reference"], "lzh->zh") for p in json.loads(cache.read_text())]
    import urllib.request

    req = urllib.request.Request(
        "https://datasets-server.huggingface.co/rows?dataset=Gare%2FClassical_Chinese_to_Modern_Chinese"
        "&config=default&split=train&offset=0&length=100",
        headers={"User-Agent": "tmtrans-validation/2.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = [x["row"]["text"] for x in json.load(r)["rows"]]
    pairs = []
    pending = None
    for t in rows:
        if t.startswith("古文："):
            pending = t.split("：", 1)[1].strip()
        elif t.startswith("现代文：") and pending:
            pairs.append((pending, t.split("：", 1)[1].strip(), "lzh->zh"))
            pending = None
    cache.write_text(json.dumps(
        [{"source": s, "reference": r} for s, r, _ in pairs], ensure_ascii=False, indent=2))
    return pairs


def load_mespen(limit: int) -> list[tuple[str, str, str]]:
    """MeSpEn Chinese-English glossary (CC BY 4.0): term-level adherence set."""
    out = []
    with open(DATA / "mespen_zh_en.tsv", encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="	"):
            if len(row) < 2:
                continue
            src = row[0].strip()
            # first column is "<id> <term>"; strip leading numeric id
            src = re.sub(r"^\d+\s+", "", src).strip()
            ref = row[1].strip()
            if src and ref and len(src) <= 30:
                out.append((src, ref, "zh->en"))
            if len(out) >= limit:
                break
    return out


_NTREX_FILE = {"th": "tha", "lo": "lao", "km": "khm"}


def load_ntrex(lang: str, limit: int) -> list[tuple[str, str, str]]:
    """NTREX-128 (CC BY-SA 4.0): English source -> th/lo/km reference.
    `lang` is the ISO 639 code used in the workbench (th/lo/km).
    Reference files are fetched at runtime (not committed — see
    benchmarks/datasets/LICENSES_AND_ATTRIBUTION.md)."""
    src_path = DATA / "ntrex_eng_src.txt"
    ref_path = DATA / f"ntrex_{_NTREX_FILE[lang]}.txt"
    if not src_path.exists() or not ref_path.exists():
        import subprocess
        subprocess.run(["bash", str(DATA / "fetch_ntrex.sh")], check=True)
    src_lines = src_path.read_text(encoding="utf-8").splitlines()
    ref_lines = ref_path.read_text(encoding="utf-8").splitlines()
    n = min(len(src_lines), len(ref_lines), limit)
    return [(src_lines[i].strip(), ref_lines[i].strip(), f"en->{lang}") for i in range(n)]


def load_hallu() -> list[tuple[str, str, str]]:
    """Adversarial G5 set: fabricated binomials live in the SOURCE (the model
    sees them and may preserve or embellish them); references are honest
    renderings. Success criterion: G5_escaped = 0."""
    return [
        # fabricated Latin names in source — preservation => gate must catch
        ("使用 Curcuma fabricata 三克", "Use Curcuma fabricata three grams", "zh->en"),
        ("丹参二两，水煎服", "Danshen root is decocted", "zh->en"),
        ("某草药主治跌打损伤，名为 Herba fictitia", "An herb named Herba fictitia treats trauma", "zh->en"),
        ("用 Glycyrrhiza imaginaria 调和诸药", "Glycyrrhiza imaginaria harmonises the formula", "zh->en"),
        ("青蒿截疟", "Artemisia annua treats malaria", "zh->en"),
        ("某根类药材，学者称其为 Panax fictionalis", "A root herb scholars call Panax fictionalis", "zh->en"),
        ("黄连三钱", "Coptis chinensis is used at three qian", "zh->en"),
        # invention pressure: vernacular-only source, model asked to be specific
        ("某种姜科草药，若知学名请给出", "A ginger-family herb is used", "zh->en"),
        ("草药外敷，请给出该植物的学名", "The herb is applied externally", "zh->en"),
        # real, attested binomials in source — must NOT trip the gate
        ("Curcuma longa 三克", "Curcuma longa three grams", "zh->en"),
    ]


def load_usda(limit: int) -> list[tuple[str, str, str]]:
    """USDA sample (CC BY 4.0, 400-row free sample only): dosage-preservation probes."""
    rows = json.loads((DATA / "usda_ethno_sample_400.json").read_text(encoding="utf-8"))
    out = []
    for r in rows:
        dosage = r.get("dosage")
        species = r.get("plant_species")
        if dosage and species:
            src = f"Preparation of {species} with dosage {dosage}"
            ref = f"{species} at {dosage}"
            out.append((src, ref, "en->en"))
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# G5 accounting
# --------------------------------------------------------------------------

def g5_account(hypothesis: str, glossary_binomials: set[str], registry: set[str],
               gate_detail: str, glossary_renderings: set[str] | None = None) -> dict:
    from tmtrans.validate import _STOPWORDS

    # Per the v2 definition, a candidate is "generated" only if absent from
    # the glossary (binomials AND English renderings) AND the registry.
    known = glossary_binomials | registry | (glossary_renderings or set())
    # Same candidate filter as tmtrans.validate's hallucination gate: reject
    # candidates containing stopwords (sentence-initial English words etc.),
    # and accept any candidate that is attested or a prefix of an attested name.
    def is_unattested(candidate: str) -> bool:
        if any(part in _STOPWORDS for part in candidate.split()):
            return False
        if candidate in known or any(k.startswith(candidate + " ") for k in known):
            return False
        return True

    candidates = [c for c in _BINOMIAL_RE.findall(hypothesis) if is_unattested(c)]
    generated = candidates
    caught = [c for c in generated if c in gate_detail]
    escaped = [c for c in generated if c not in gate_detail]
    return {
        "generated": len(generated),
        "caught": len(caught),
        "escaped": len(escaped),
        "generated_names": sorted(set(generated)),
        "escaped_names": sorted(set(escaped)),
    }


# --------------------------------------------------------------------------
# translation with ablation options (harness-side; src code untouched)
# --------------------------------------------------------------------------

def build_messages(source: str, ctx, binding: bool = True, target_lang: str = "en") -> list[dict]:
    from tmtrans.lang import profile
    from tmtrans.prompts import build_glossary_block, build_memory_block

    target_name = "English" if target_lang == "en" else profile(target_lang).name
    system = (
        "You are a specialist translator of traditional medicine literature "
        "(TCM, Ayurveda, Southeast Asian ethnopharmacology).\n"
        f"Translate faithfully into {target_name}; do not summarise or add commentary.\n"
    )
    if binding:
        system += (
            "GLOSSARY TERMS ARE BINDING. Use the exact English rendering given for "
            "each glossary term. NEVER invent a scientific binomial; if a name is not "
            "in the glossary keep the source term and mark it untranslated.\n"
        )
    else:
        system += (
            "A glossary is provided as suggestions; use your judgement. "
            "Translate naturally.\n"
        )
    system += 'Output JSON only: {"translation": "...", "terms": [], "notes": ""}'
    user = (
        f"Translate the following passage into {target_name}.\n\n"
        f"{build_glossary_block(ctx)}{build_memory_block(ctx)}"
        f'Source passage:\n"""\n{source}\n"""\n\n'
        'Return JSON with keys "translation", "terms", "notes".'
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def translate_segment_v2(translator, source, source_lang, variant, *, rag: bool = True,
                         binding: bool = True, classical: bool = True,
                         target_lang: str = "en") -> dict:
    """Run one segment with ablation flags. Uses program gates for scoring."""
    from tmtrans.prompts import parse_translation_response
    from tmtrans.rag import retrieve
    from tmtrans.segment import Segment
    from tmtrans.validate import validate_segment

    seg = Segment(index=0, text=source, start=0, end=len(source), page=None)
    modern_text = None
    src = source
    if classical and translator.backend and __import__("tmtrans.lang", fromlist=["requires_classical_stage"]).requires_classical_stage(source_lang, variant):
        modern_text = translator.modernize(source, source_lang)
        if modern_text:
            src = modern_text

    ctx = retrieve(translator.glossary, translator.memory, src, source_lang) if rag else None
    if ctx is None:
        from tmtrans.rag import RetrievedContext
        ctx = RetrievedContext(glossary=[], memory=[])

    messages = build_messages(src, ctx, binding=binding, target_lang=target_lang)
    raw = translator.backend.complete(messages)
    try:
        parsed = parse_translation_response(raw)
        hyp, terms = parsed["translation"], parsed.get("terms", [])
    except Exception as e:
        hyp, terms = f"[parse-error] {e}", []

    report = validate_segment(
        segment_id="v2", source_text=src, translation=hyp, terms=terms,
        expected_glossary=ctx.glossary, source_lang=source_lang,
        glossary=translator.glossary, registry=translator.registry,
    )
    halluc_detail = next((r.detail for r in report.results if r.gate == "hallucination"), "")
    # G4 (residual source script) is only meaningful when the target is
    # English: the gate detects source-script leftovers in a Latin-script
    # target. For th/lo/km/zh targets, mark it n/a rather than false-failed.
    gates_out = []
    for r in report.results:
        passed = r.passed
        if r.gate == "untranslated" and target_lang != "en":
            passed = None  # n/a — gate not applicable to this direction
        gates_out.append({"gate": r.gate, "passed": passed, "severity": r.severity,
                          "detail": r.detail if passed is not False else r.detail})
    return {
        "source": source, "modern_text": modern_text, "hypothesis": hyp,
        "terms": terms, "status": report.status,
        "gates": gates_out,
        "hallucination_detail": halluc_detail,
    }


# --------------------------------------------------------------------------
# metrics with bootstrap CIs
# --------------------------------------------------------------------------

def bootstrap_ci(scores_per_segment_fn, items, n_boot=N_BOOT, seed=SEED):
    """Resample segment indices with replacement; return (point, lo, hi)."""
    set_seed(seed)
    n = len(items)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = scores_per_segment_fn(items)
    stats = []
    for _ in range(n_boot):
        idx = [random.randrange(n) for _ in range(n)]
        resampled = [items[i] for i in idx]
        try:
            stats.append(scores_per_segment_fn(resampled))
        except Exception:
            pass
    if not stats:
        return point, point, point
    stats.sort()
    lo = stats[int(0.025 * (len(stats) - 1))]
    hi = stats[int(0.975 * (len(stats) - 1))]
    return point, lo, hi


def corpus_metrics(hyps: list[str], refs: list[str]) -> tuple[float, float, float]:
    """chrF++ , BLEU (13a), TER. Lower TER is better."""
    chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
    bleu = sacrebleu.corpus_bleu(hyps, [refs], tokenize="13a").score
    try:
        from sacrebleu.metrics import TER
        ter = TER().corpus_score(hyps, [refs]).score
    except Exception:
        ter = float("nan")
    return chrf, bleu, ter


def metrics_with_ci(rows: list[dict]) -> dict:
    hyps = [r["hypothesis"] for r in rows]
    refs = [r["reference"] for r in rows]

    def chrf_fn(items):
        return sacrebleu.corpus_chrf([i["hypothesis"] for i in items], [[i["reference"] for i in items]], word_order=2).score

    def bleu_fn(items):
        return sacrebleu.corpus_bleu([i["hypothesis"] for i in items], [[i["reference"] for i in items]], tokenize="13a").score

    c, c_lo, c_hi = bootstrap_ci(chrf_fn, rows)
    b, b_lo, b_hi = bootstrap_ci(bleu_fn, rows)
    _, _, ter = corpus_metrics(hyps, refs)
    return {
        "chrf": round(c, 2), "chrf_ci": [round(c_lo, 2), round(c_hi, 2)],
        "bleu": round(b, 2), "bleu_ci": [round(b_lo, 2), round(b_hi, 2)],
        "ter": round(ter, 2),
    }


def gate_rates(rows: list[dict]) -> dict:
    """G3 / G4 / G6 / G7 pass rates from the program's own gate outputs.
    Gates marked passed=None are n/a for that row and excluded from the rate."""
    totals = {"glossary": 0, "glossary_pass": 0, "untranslated": 0, "untranslated_pass": 0,
              "numbers": 0, "numbers_pass": 0, "length": 0, "length_pass": 0,
              "non_empty": 0, "non_empty_pass": 0}
    for r in rows:
        for g in r["gates"]:
            key = g["gate"]
            if key not in ("glossary", "untranslated", "numbers", "length", "non_empty"):
                continue
            if g["passed"] is None:
                continue  # n/a for this direction
            totals[key] += 1
            if g["passed"]:
                totals[key + "_pass"] += 1
    def rate(k):
        return round(totals[k + "_pass"] / totals[k], 4) if totals[k] else None
    return {
        "G3_glossary_pass_rate": rate("glossary"),
        "G4_untranslated_pass_rate": rate("untranslated"),
        "G6_numbers_pass_rate": rate("numbers"),
        "G7_length_pass_rate": rate("length"),
        "G2_nonempty_pass_rate": rate("non_empty"),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def make_translator(backend_kind: str, model: str | None, extra_glossary: str | None = None):
    from tmtrans.backend import BackendConfig, MockBackend, OpenAICompatBackend
    from tmtrans.dictionary import DictEntry, Glossary
    from tmtrans.rag import TranslationMemoryIndex
    from tmtrans.translate import Translator

    glossary = Glossary()
    for name in ("seed_tcm.csv", "seed_ayurveda.csv", "seed_seasian.csv"):
        p = ROOT / "data" / "dictionary" / name
        if p.exists():
            glossary.load_csv(p)
    if extra_glossary == "mespen":
        # Load the same MeSpEn zh-en terms used as the glossary-adherence test
        # set, so G3 has binding terms and the binding ablation has an effect.
        import csv as _csv
        with open(DATA / "mespen_zh_en.tsv", encoding="utf-8") as fh:
            for i, row in enumerate(_csv.reader(fh, delimiter="	")):
                if len(row) < 2 or i >= 200:
                    continue
                src = re.sub(r"^\d+\s+", "", row[0].strip()).strip()
                if src and row[1].strip():
                    glossary.add(DictEntry(
                        entry_id=f"mespen-{i:04d}", category="concept", source_lang="zh",
                        source_form=src, english=row[1].strip(), tradition="mespen"))
    registry_path = ROOT / "data" / "validation_registry.txt"
    registry = set()
    if registry_path.exists():
        registry = {ln.strip() for ln in registry_path.read_text().splitlines() if ln.strip()}
    if backend_kind == "mock":
        backend = MockBackend()
    else:
        cfg = BackendConfig.from_env()
        if model:
            cfg.model = model
        cfg.temperature = 0.0
        backend = OpenAICompatBackend(cfg)
    return Translator(backend=backend, glossary=glossary, memory=TranslationMemoryIndex(),
                      registry=registry)


def run_dataset(translator, pairs, dataset_id: str, model_tag: str, *, rag=True,
                binding=True, classical=True, source_lang=None, label=None) -> dict:
    from tmtrans.validate import validate_segment

    rows = []
    gl_binomials = {e.binomial for e in translator.glossary.entries.values() if e.binomial}
    gl_renderings = {e.english for e in translator.glossary.entries.values() if e.english}
    registry = translator.registry or set()
    for src, ref, direction in pairs:
        if direction.startswith("lzh"):
            # classical -> modern stage: the scoreable artifact is the modern
            # rewrite (compared against the 现代文 reference); G5 accounting
            # applies to the English output, where binomials can appear.
            res = translate_segment_v2(translator, src, "zh", "classical",
                                       rag=rag, binding=binding, classical=classical,
                                       target_lang="en")
            scored_hyp = res["modern_text"] or ""
            report = validate_segment(
                segment_id="v2", source_text=src, translation=scored_hyp, terms=[],
                expected_glossary=[], source_lang="zh", glossary=translator.glossary,
                registry=translator.registry)
            gates = []
            for r in report.results:
                passed = r.passed
                if r.gate in ("glossary", "untranslated"):
                    # scored artifact is a modern-Chinese rewrite: G3 (English
                    # renderings) and G4 (Latin-target residual script) are n/a
                    passed = None
                gates.append({"gate": r.gate, "passed": passed, "severity": r.severity,
                              "detail": r.detail})
            g5_artifact = res["hypothesis"]
        else:
            src_lang = direction.split("->")[0]
            tgt = direction.split("->")[1]
            res = translate_segment_v2(translator, src, src_lang, None,
                                       rag=rag, binding=binding, classical=False,
                                       target_lang=tgt)
            scored_hyp = res["hypothesis"]
            gates = res["gates"]
            g5_artifact = res["hypothesis"]
        g5 = g5_account(g5_artifact, gl_binomials, registry, res["hallucination_detail"],
                        glossary_renderings=gl_renderings)
        rows.append({"source": src, "reference": ref, "hypothesis": scored_hyp,
                     "raw_output": res["hypothesis"], "modern_text": res.get("modern_text"),
                     "status": res["status"], "gates": gates, "terms": res.get("terms", []),
                     "g5": g5, "direction": direction})
    # G5 totals
    gen = sum(r["g5"]["generated"] for r in rows)
    caught = sum(r["g5"]["caught"] for r in rows)
    escaped = sum(r["g5"]["escaped"] for r in rows)
    out = {
        "dataset": dataset_id, "model": model_tag, "n_segments": len(rows),
        **metrics_with_ci(rows), **gate_rates(rows),
        "G5_generated": gen, "G5_caught": caught, "G5_escaped": escaped,
        "G5_escape_rate": round(escaped / gen, 4) if gen else "n/a",
    }
    # save per-segment
    fname = f"{label or dataset_id}_{model_tag.replace('/', '_')}.jsonl"
    with open(OUT_SAVE / fname, "w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps({"idx": i, **r}, ensure_ascii=False) + "\n")
    out["_rows"] = rows
    out["_file"] = fname
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["real", "mock"], default="real")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit-mespen", type=int, default=40)
    ap.add_argument("--limit-ntrex", type=int, default=30)
    ap.add_argument("--limit-usda", type=int, default=48)
    args = ap.parse_args()

    set_seed()
    OUT.mkdir(parents=True, exist_ok=True)
    # Quarantine non-real runs so they never clobber real-model evidence.
    out_dir = OUT if args.backend == "real" else (OUT / args.backend)
    out_dir.mkdir(parents=True, exist_ok=True)
    global OUT_SAVE
    OUT_SAVE = out_dir
    model_tag = args.model or ("mock" if args.backend == "mock" else "openai_compat")
    translator = make_translator(args.backend, args.model, extra_glossary="mespen")
    print(f"[v2] backend={args.backend} model={model_tag} out={out_dir}")

    datasets: dict[str, list] = {}
    datasets["classical-zh"] = load_gare()
    datasets["glossary-adherence"] = load_mespen(args.limit_mespen)
    for lg in ("th", "lo", "km"):
        fwd = load_ntrex(lg, args.limit_ntrex)                          # en -> X
        rev = [(r, s, f"{lg}->en") for s, r, _ in fwd]                 # X -> en
        datasets[f"ntrex-128-en-{lg}"] = fwd
        datasets[f"ntrex-128-{lg}-en"] = rev
    datasets["hallucination-check"] = load_hallu()
    datasets["usda-dosage"] = load_usda(args.limit_usda)

    summary = []
    for name, pairs in datasets.items():
        t0 = time.time()
        print(f"[v2] {name}: {len(pairs)} pairs ...")
        res = run_dataset(translator, pairs, name, model_tag)
        res["elapsed_s"] = round(time.time() - t0, 1)
        summary.append(res)
        print(f"    chrf={res['chrf']}[{res['chrf_ci']}] bleu={res['bleu']}[{res['bleu_ci']}] "
              f"G5={res['G5_generated']}/{res['G5_caught']}/{res['G5_escaped']} ({res['elapsed_s']}s)")

    # ---- ablations (classical-zh + glossary-adherence, real model) ----
    ablations = []
    abl_specs = [
        ("classical-zh", "baseline", dict(rag=True, binding=True, classical=True)),
        ("classical-zh", "rag_off", dict(rag=False, binding=True, classical=True)),
        ("classical-zh", "binding_off", dict(rag=True, binding=False, classical=True)),
        ("classical-zh", "classical_off", dict(rag=True, binding=True, classical=False)),
        ("glossary-adherence", "baseline", dict(rag=True, binding=True, classical=True)),
        ("glossary-adherence", "rag_off", dict(rag=False, binding=True, classical=True)),
        ("glossary-adherence", "binding_off", dict(rag=True, binding=False, classical=True)),
    ]
    for name, cond, flags in abl_specs:
        t0 = time.time()
        print(f"[v2] ablation {name}/{cond} ...")
        res = run_dataset(translator, datasets[name], name, model_tag,
                          label=f"abl_{name}_{cond}", **flags)
        res["ablation_condition"] = cond
        res["elapsed_s"] = round(time.time() - t0, 1)
        ablations.append(res)
        print(f"    chrf={res['chrf']} G3={res['G3_glossary_pass_rate']} "
              f"G5={res['G5_generated']}/{res['G5_caught']}/{res['G5_escaped']}")

    # ---- reproducibility: rerun classical-zh, report chrF delta ----
    if args.backend == "real":
        print("[v2] reproducibility rerun (classical-zh) ...")
        rerun = run_dataset(translator, datasets["classical-zh"], "classical-zh", model_tag,
                            label="repro_classical-zh_run2")
        delta = abs(rerun["chrf"] - summary[0]["chrf"])
        repro = {"dataset": "classical-zh", "run1_chrf": summary[0]["chrf"],
                 "run2_chrf": rerun["chrf"], "abs_delta": round(delta, 2)}
    else:
        repro = {"dataset": "classical-zh", "note": "mock runs are deterministic"}

    # ---- write CSVs ----
    cols = ["dataset", "model", "n_segments", "chrf", "chrf_ci", "bleu", "bleu_ci", "ter",
            "G3_glossary_pass_rate", "G4_untranslated_pass_rate",
            "G5_generated", "G5_caught", "G5_escaped", "G5_escape_rate",
            "G6_numbers_pass_rate", "G7_length_pass_rate", "notes"]

    def row_dict(r):
        return {
            "dataset": r["dataset"], "model": r["model"], "n_segments": r["n_segments"],
            "chrf": r["chrf"], "chrf_ci": f"[{r['chrf_ci'][0]},{r['chrf_ci'][1]}]",
            "bleu": r["bleu"], "bleu_ci": f"[{r['bleu_ci'][0]},{r['bleu_ci'][1]}]",
            "ter": r["ter"],
            "G3_glossary_pass_rate": r["G3_glossary_pass_rate"],
            "G4_untranslated_pass_rate": r["G4_untranslated_pass_rate"],
            "G5_generated": r["G5_generated"], "G5_caught": r["G5_caught"],
            "G5_escaped": r["G5_escaped"], "G5_escape_rate": r["G5_escape_rate"],
            "G6_numbers_pass_rate": r["G6_numbers_pass_rate"],
            "G7_length_pass_rate": r["G7_length_pass_rate"],
            "notes": r.get("ablation_condition", ""),
        }

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in summary:
            w.writerow(row_dict(r))

    with open(out_dir / "ablations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in ablations:
            w.writerow(row_dict(r))

    slim = [{k: v for k, v in r.items() if not k.startswith("_")} for r in summary]
    slim_a = [{k: v for k, v in r.items() if not k.startswith("_")} for r in ablations]
    with open(out_dir / "summary.json", "w", encoding="utf-8") as fh:
        json.dump({"backend": args.backend, "model": model_tag,
                   "seed": SEED, "n_boot": N_BOOT,
                   "summary": slim, "ablations": slim_a, "reproducibility": repro},
                  fh, ensure_ascii=False, indent=2)
    print(f"\n[v2] wrote summary.csv, ablations.csv, summary.json to {OUT}")


if __name__ == "__main__":
    main()