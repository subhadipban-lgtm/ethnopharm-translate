"""LLM backends.

- openai_compat: any OpenAI-compatible /chat/completions endpoint — vLLM
  (http://localhost:8000/v1), Ollama (http://localhost:11434/v1), LM Studio,
  llama.cpp server, or a hosted provider.
- nllb: Meta NLLB-200-3.3B, a dedicated massively-multilingual translation
  model. Unlike the chat backends it is a raw seq2seq MT model — it does NOT
  follow instructions, cannot apply a glossary, and does not emit the JSON
  contract. Use it as a drop-in quality probe / baseline, not as a drop-in
  for the glossary-bound pipeline. Requires the optional ``nllb`` extra
  (``pip install tmtrans[nllb]``) and acceptance of its non-commercial
  license (CC-BY-NC-4.0).
- mock: deterministic offline backend for tests and pipeline dry-runs. It
  echoes the source and applies glossary constraints so the full validation
  and review path can be exercised without a GPU.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx


class BackendError(RuntimeError):
    pass


@dataclass
class BackendConfig:
    kind: str = "openai_compat"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:7b-instruct"
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout: float = 180.0
    # NLLB-specific: source and target FLORES-200 codes. src_lang is optional;
    # when unset, the prose language is used as-is and the model uses its own
    # language token routing via `src_lang`.
    src_lang: str = ""       # e.g. "zho_Hans"; empty => derive from message source hint
    tgt_lang: str = "eng_Latn"
    nllb_model: str = "facebook/nllb-200-3.3B"

    @classmethod
    def from_env(cls) -> "BackendConfig":
        return cls(
            kind=os.environ.get("TMTRANS_BACKEND", "openai_compat"),
            base_url=os.environ.get("TMTRANS_BASE_URL", "http://localhost:11434/v1"),
            model=os.environ.get("TMTRANS_MODEL", "qwen2.5:7b-instruct"),
            api_key=os.environ.get("TMTRANS_API_KEY", ""),
            temperature=float(os.environ.get("TMTRANS_TEMPERATURE", "0.1")),
            max_tokens=int(os.environ.get("TMTRANS_MAX_TOKENS", "2048")),
            timeout=float(os.environ.get("TMTRANS_TIMEOUT", "180")),
            src_lang=os.environ.get("TMTRANS_SRC_LANG", ""),
            tgt_lang=os.environ.get("TMTRANS_TGT_LANG", "eng_Latn"),
            nllb_model=os.environ.get("TMTRANS_NLLB_MODEL", "facebook/nllb-200-3.3B"),
        )


class LLMBackend:
    def complete(self, messages: list[dict]) -> str:
        raise NotImplementedError


class OpenAICompatBackend(LLMBackend):
    def __init__(self, cfg: BackendConfig) -> None:
        self.cfg = cfg

    def complete(self, messages: list[dict]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=self.cfg.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise BackendError(f"LLM request failed: {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise BackendError(f"Malformed LLM response: {json.dumps(data)[:300]}") from exc

    def health(self) -> dict:
        url = self.cfg.base_url.rstrip("/") + "/models"
        headers = {}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                models = [m.get("id") for m in resp.json().get("data", [])]
                return {"ok": True, "models": models}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class NLLBBackend(LLMBackend):
    """Meta NLLB-200-3.3B translation backend (CC-BY-NC-4.0, non-commercial).

    NLLB is a dedicated encoder-decoder MT model: it takes a source string and
    a target language token and returns a translation. It does NOT follow
    instructions, does NOT apply a glossary, and does NOT emit JSON — so this
    backend translates the raw passage and wraps the result in the same JSON
    envelope the rest of the pipeline expects. Glossary adherence, binding
    constraints, and term annotation are therefore NOT enforced here; the
    validation gates downstream (G3/G5/G6) still run and will flag failures.

    Use for: benchmarking, baseline comparison, bulk draft translation where
    no glossary is required. Do NOT use for production TM or clinical output.
    """

    def __init__(self, cfg: BackendConfig) -> None:
        self.cfg = cfg
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except Exception as exc:
            raise BackendError(
                "NLLB backend requires the 'nllb' extra: "
                "pip install 'tmtrans[nllb]'  (torch + transformers + sentencepiece). "
                f"Import failed: {exc}"
            ) from exc
        self._tok = AutoTokenizer.from_pretrained(self.cfg.nllb_model)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.cfg.nllb_model)
        self._model.eval()

    def _flores(self, lang: str) -> str:
        # Accept either a FLORES-200 code (contains '_') or an internal code.
        if "_" in lang:
            return lang
        from .lang import flores_code
        return flores_code(lang)

    @staticmethod
    def _extract_source(messages: list[dict]) -> str:
        user = next((m["content"] for m in messages if m.get("role") == "user"), "")
        if '"""' in user:
            return user.split('"""')[1].strip()
        return user.strip()

    def complete(self, messages: list[dict]) -> str:
        self._load()
        src_text = self._extract_source(messages)
        if not src_text:
            raise BackendError("NLLBBackend received an empty source passage")

        src = self.cfg.src_lang or self._extract_source_lang_hint(messages)
        src_code = self._flores(src)
        tgt_code = self._flores(self.cfg.tgt_lang)

        self._tok.src_lang = src_code
        try:
            import torch
            inputs = self._tok(src_text, return_tensors="pt", truncation=True, max_length=512)
            forced_bos = self._tok.convert_tokens_to_ids(tgt_code)
            with torch.no_grad():
                gen = self._model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    max_new_tokens=min(self.cfg.max_tokens, 256),
                    num_beams=4,
                )
            text = self._tok.batch_decode(gen, skip_special_tokens=True)[0].strip()
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(f"NLLB generation failed: {exc}") from exc

        return json.dumps(
            {"translation": text, "terms": [], "notes": "nllb-200 output; glossary not applied"},
            ensure_ascii=False,
        )

    @staticmethod
    def _extract_source_lang_hint(messages: list[dict]) -> str:
        # Default to Chinese if the prompt carries no explicit hint; the caller
        # should set TMTRANS_SRC_LANG for anything else.
        return os.environ.get("TMTRANS_SRC_LANG", "zho_Hans") or "zho_Hans"

    def health(self) -> dict:
        try:
            self._load()
            return {"ok": True, "model": self.cfg.nllb_model}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class MockBackend(LLMBackend):
    """Echo backend: applies glossary constraints verbatim, keeps the rest of
    the source. Produces schema-valid responses so the pipeline, validation
    gates and review UI can be exercised without an LLM."""

    def complete(self, messages: list[dict]) -> str:
        user = next(m["content"] for m in messages if m["role"] == "user")
        system = next(m["content"] for m in messages if m["role"] == "system")
        source = user.split('"""')[1].strip() if '"""' in user else user
        if "philologist" in system:
            return json.dumps({"modern": f"[modern] {source}"}, ensure_ascii=False)
        glossary: dict[str, dict] = {}
        in_glossary = False
        for line in user.splitlines():
            if line.startswith("GLOSSARY"):
                in_glossary = True
                continue
            if in_glossary:
                if not line.strip():
                    break
                # format: - id=X | category=Y | "源" -> "english" | binomial: B
                try:
                    entry_id = line.split("id=")[1].split(" |")[0]
                    src = line.split('"')[1]
                    eng = line.split('-> "')[1].split('"')[0]
                    binomial = ""
                    if "binomial:" in line:
                        binomial = line.split("binomial:")[1].split("|")[0].strip()
                    glossary[src] = {"english": eng, "binomial": binomial, "entry_id": entry_id}
                except IndexError:
                    continue
        translation = source
        terms = []
        # Longest-first so formula names (桂枝汤) are substituted before their
        # component herbs (桂枝).
        for src in sorted(glossary, key=len, reverse=True):
            info = glossary[src]
            translation = translation.replace(src, info["english"])
            terms.append({"source": src, "status": "matched", **info})
        return json.dumps(
            {
                "translation": f"[mock] {translation}",
                "terms": terms,
                "notes": "mock backend: source echoed with glossary substitutions",
            },
            ensure_ascii=False,
        )


def get_backend(cfg: BackendConfig | None = None) -> LLMBackend:
    cfg = cfg or BackendConfig.from_env()
    if cfg.kind == "mock":
        return MockBackend()
    if cfg.kind == "openai_compat":
        return OpenAICompatBackend(cfg)
    if cfg.kind == "nllb":
        return NLLBBackend(cfg)
    raise BackendError(f"Unknown backend kind: {cfg.kind} (expected one of: openai_compat, nllb, mock)")
