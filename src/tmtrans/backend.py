"""LLM backends.

- openai_compat: any OpenAI-compatible /chat/completions endpoint — vLLM
  (http://localhost:8000/v1), Ollama (http://localhost:11434/v1), LM Studio,
  llama.cpp server, or a hosted provider.
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

    @classmethod
    def from_env(cls) -> "BackendConfig":
        return cls(
            kind=os.environ.get("TMTRANS_BACKEND", "openai_compat"),
            base_url=os.environ.get("TMTRANS_BASE_URL", "http://localhost:11434/v1"),
            model=os.environ.get("TMTRANS_MODEL", "qwen2.5:7b-instruct"),
            api_key=os.environ.get("TMTRANS_API_KEY", ""),
            temperature=float(os.environ.get("TMTRANS_TEMPERATURE", "0.1")),
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
    raise BackendError(f"Unknown backend kind: {cfg.kind}")
