"""Retrieval-augmented context for translation.

Two retrieval channels are combined per segment:
1. Glossary hits (hard constraints on terminology).
2. Nearest-neighbour retrieval over previously human-approved segments
   (the translation memory), embedded with a local TF-IDF char-ngram index so
   the whole pipeline runs offline with no external embedding service.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from .dictionary import DictEntry, Glossary


@dataclass
class MemoryHit:
    segment_id: str
    source_text: str
    target_text: str
    score: float


class TranslationMemoryIndex:
    """Character 3-5-gram TF-IDF index over approved segment pairs.

    Char n-grams work across CJK, Indic and Latin scripts without a tokenizer,
    which is exactly what mixed traditional-medicine corpora need.
    """

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}
        self._df: Counter = Counter()
        self._vectors: dict[str, Counter] = {}
        self._norms: dict[str, float] = {}
        self._dirty = True

    @staticmethod
    def _ngrams(text: str) -> list[str]:
        t = re.sub(r"\s+", " ", text.lower()).strip()
        grams: list[str] = []
        for n in (3, 4, 5):
            grams.extend(t[i : i + n] for i in range(max(0, len(t) - n + 1)))
        return grams

    def add(self, segment_id: str, source_text: str, target_text: str) -> None:
        if segment_id in self._docs:
            self.remove(segment_id)
        tf = Counter(self._ngrams(source_text))
        self._docs[segment_id] = {"source": source_text, "target": target_text}
        self._vectors[segment_id] = tf
        for g in tf:
            self._df[g] += 1
        self._dirty = True

    def remove(self, segment_id: str) -> None:
        if segment_id not in self._docs:
            return
        for g in self._vectors[segment_id]:
            self._df[g] -= 1
            if self._df[g] <= 0:
                del self._df[g]
        del self._docs[segment_id]
        del self._vectors[segment_id]
        self._norms.pop(segment_id, None)
        self._dirty = True

    def _idf(self, gram: str) -> float:
        n = max(1, len(self._docs))
        return math.log((n + 1) / (1 + self._df.get(gram, 0))) + 1.0

    def _recompute_norms(self) -> None:
        for sid, tf in self._vectors.items():
            self._norms[sid] = math.sqrt(
                sum((c * self._idf(g)) ** 2 for g, c in tf.items())
            ) or 1.0
        self._dirty = False

    def search(self, text: str, top_k: int = 3, min_score: float = 0.15) -> list[MemoryHit]:
        if not self._docs:
            return []
        if self._dirty:
            self._recompute_norms()
        qtf = Counter(self._ngrams(text))
        qnorm = math.sqrt(sum((c * self._idf(g)) ** 2 for g, c in qtf.items())) or 1.0
        hits: list[MemoryHit] = []
        for sid, tf in self._vectors.items():
            dot = sum(
                qtf[g] * self._idf(g) * tf[g] * self._idf(g) for g in qtf if g in tf
            )
            score = dot / (qnorm * self._norms[sid])
            if score >= min_score:
                hits.append(
                    MemoryHit(
                        segment_id=sid,
                        source_text=self._docs[sid]["source"],
                        target_text=self._docs[sid]["target"],
                        score=round(score, 4),
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"docs": self._docs}, fh, ensure_ascii=False)

    def load(self, path: str) -> None:
        import os

        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for sid, doc in data.get("docs", {}).items():
            self.add(sid, doc["source"], doc["target"])


@dataclass
class RetrievedContext:
    glossary: list[DictEntry]
    memory: list[MemoryHit]

    def is_empty(self) -> bool:
        return not self.glossary and not self.memory


def retrieve(
    glossary: Glossary,
    memory: TranslationMemoryIndex,
    source_text: str,
    source_lang: str,
    top_k: int = 3,
) -> RetrievedContext:
    entries = glossary.find_in_text(source_text, source_lang)
    # Classical Chinese source segments are matched against both lzh and zh entries.
    if source_lang == "lzh":
        entries.extend(glossary.find_in_text(source_text, "zh"))
    hits = memory.search(source_text, top_k=top_k)
    return RetrievedContext(glossary=entries, memory=hits)
