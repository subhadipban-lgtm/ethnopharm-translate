"""OCR ingestion for manuscript scans: woodblock Chinese, Devanagari palm
leaves, Thai Samut Khoi folding books, and modern printed pharmacopoeias.

Architecture (designed for a single 24GB GPU):
  1. Line segmentation first (optional surya) so small diacritics — Thai Sara,
     Devanagari matras — are never blurred by full-page downscaling.
  2. Line/page recognition through an OpenAI-compatible vision endpoint
     (vLLM serving Qwen2.5-VL-7B, PaddleOCR-VL, GLM-OCR, DeepSeek-OCR, or a
     script-specific fine-tune).
  3. Script-aware reading-order stitching (vertical columns right-to-left for
     classical Chinese; horizontal lines for Thai/Latin).
  4. JSONL output — OCR runs first and exits, then the translation model gets
     the full VRAM buffer. `tmtrans translate pages.jsonl` picks up from there.

The OCR backend is deliberately pluggable: the same vision endpoint accepts
any HF vision checkpoint that vLLM can serve, so swapping
Qwen2.5-VL-7B-Instruct for Sanskrit-Qwen2.5-VL-7B-Instruct-OCR (or a Thai
DeepSeek-OCR LoRA merge) is a one-env-var change.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .lang import profile

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

READING_ORDERS = ("auto", "rtl-columns", "ltr-lines")

# Transcription prompts per script family. Deliberately conservative: output
# only what is written, preserve line structure, never translate or normalise.
_OCR_PROMPTS = {
    "lzh": (
        "This image is a page of classical Chinese text, possibly woodblock print "
        "in vertical columns read top-to-bottom and right-to-left. Transcribe ALL "
        "text exactly as written, one transcription line per visual line/column, "
        "in correct reading order. Output only the transcription. Do not translate, "
        "do not add punctuation that is not present, do not skip columns, seals or "
        "marginalia notes — include them on separate lines."
    ),
    "sa": (
        "This image shows Sanskrit text in Devanagari (manuscript or print). "
        "Transcribe ALL text exactly as written, line by line, in reading order. "
        "Output only the transcription. Preserve conjuncts; do not emend or "
        "normalise the text, and do not translate."
    ),
    "pi": (
        "This image shows Pali text in a traditional script (often Khmer or "
        "Tham). Transcribe all text line by line in reading order. Output only "
        "the transcription; do not translate."
    ),
    "th": (
        "This image shows Thai text, possibly from a Samut Khoi folding book "
        "with historical handwriting. Transcribe ALL text exactly as written, "
        "line by line, in reading order. Preserve tone marks and vowels above "
        "and below the baseline. Output only the transcription; do not translate."
    ),
    "km": (
        "This image shows Khmer text, possibly a palm-leaf manuscript "
        "(sastra sleuk rith). Transcribe all text line by line in reading "
        "order, preserving subscripts and diacritics. Output only the "
        "transcription; do not translate."
    ),
    "lo": (
        "This image shows Lao text, possibly from a palm-leaf manuscript "
        "(nithan)。 Transcribe all text line by line in reading order. Output "
        "only the transcription; do not translate."
    ),
    "my": (
        "This image shows Burmese text, possibly parabaik manuscript. "
        "Transcribe all text line by line in reading order. Output only the "
        "transcription; do not translate."
    ),
    "ta": (
        "This image shows Tamil text, possibly palm-leaf (olai chuvadi) "
        "manuscript. Transcribe all text line by line in reading order. Output "
        "only the transcription; do not translate."
    ),
}

_GENERIC_PROMPT = (
    "Transcribe ALL text in this image exactly as written, line by line, in "
    "reading order. The text is {langname}. Output only the transcription; do "
    "not translate."
)

IAST_SUFFIX = (
    " Render the output in IAST (International Alphabet of Sanskrit "
    "Transliteration) instead of the source script."
)


class OCRError(RuntimeError):
    pass


@dataclass
class OCRBackendConfig:
    kind: str = "vlm"  # vlm | mock
    base_url: str = ""  # defaults to the translation backend URL
    model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: float = 300.0

    @classmethod
    def from_env(cls, fallback_base_url: str = "", fallback_api_key: str = "") -> "OCRBackendConfig":
        return cls(
            kind=os.environ.get("TMTRANS_OCR_BACKEND", "vlm"),
            base_url=os.environ.get("TMTRANS_OCR_BASE_URL", fallback_base_url),
            model=os.environ.get("TMTRANS_OCR_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
            api_key=os.environ.get("TMTRANS_OCR_API_KEY", fallback_api_key),
        )


@dataclass
class Line:
    text: str
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h


@dataclass
class PageResult:
    image: str
    page: int
    lines: list[Line] = field(default_factory=list)
    backend: str = ""
    model: str = ""

    @property
    def text(self) -> str:
        return stitch([ln.text for ln in self.lines], "\n")


def _is_cjk_text(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def stitch(line_texts: list[str], separator: str = "\n") -> str:
    """Join recognised lines. CJK lines are concatenated without spaces so
    sentence segmentation downstream sees continuous text."""
    out: list[str] = []
    for t in line_texts:
        t = t.strip()
        if not t:
            continue
        if out and _is_cjk_text(t[-1] + out[-1][-1]):
            out[-1] += t
        else:
            out.append(t)
    return separator.join(out).strip()


def order_lines(lines: list[Line], reading_order: str) -> list[Line]:
    """Sort line boxes into reading order.

    rtl-columns: classical Chinese woodblock — columns top-to-bottom,
    right-to-left, so sort by descending x then ascending y.
    ltr-lines: Thai/Latin/Devanagari — sort by ascending y then x.
    Lines without boxes keep their given order (VLM already emitted them in
    reading order).
    """
    if reading_order not in READING_ORDERS:
        raise OCRError(f"unknown reading order {reading_order!r}")
    boxed = [ln for ln in lines if ln.bbox]
    unboxed = [ln for ln in lines if not ln.bbox]
    if not boxed:
        return lines
    if reading_order == "rtl-columns":
        boxed.sort(key=lambda ln: (-ln.bbox[0], ln.bbox[1]))
    else:
        boxed.sort(key=lambda ln: (round(ln.bbox[1], 1), ln.bbox[0]))
    return boxed + unboxed


def discover_images(folder: str | Path) -> list[Path]:
    p = Path(folder)
    if not p.is_dir():
        raise OCRError(f"not a directory: {p}")
    def natural_key(path: Path):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name)]
    files = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES]
    files.sort(key=natural_key)
    if not files:
        raise OCRError(f"no images found in {p}")
    return files


def segment_lines_surya(image_path: str | Path) -> list[Line]:
    """Optional CPU/low-VRAM line detection via surya. Install with
    `pip install tmtrans[ocr]`. Returns lines without text (bbox only)."""
    try:
        from surya.detection import DetectionPredictor
    except ImportError as exc:  # pragma: no cover
        raise OCRError(
            "surya line segmentation requires: pip install 'tmtrans[ocr]'"
        ) from exc
    predictor = DetectionPredictor()
    predictions = predictor([image_path])
    lines = []
    for pred in predictions:
        for row in pred.bboxes:
            x, y, w, h = row
            lines.append(Line(text="", bbox=(float(x), float(y), float(w), float(h))))
    return lines


class VLMOCRBackend:
    """Any vision-language model behind an OpenAI-compatible endpoint.

    Verified model options (Nov 2026, all HF):
      Unified:   Qwen/Qwen2.5-VL-7B-Instruct (5.2M dl) or Qwen/Qwen3-VL-8B-Instruct
      Compact:   PaddlePaddle/PaddleOCR-VL-1.6 (0.9B), zai-org/GLM-OCR
      Sanskrit:  diabolic6045/Sanskrit-Qwen2.5-VL-7B-Instruct-OCR
      Thai:      DeepSeek-OCR base (sthaps/DeepSeek-ocr-Thai as LoRA source)
    Serve with: vllm serve <model> --max-model-len 16384
    """

    def __init__(self, cfg: OCRBackendConfig) -> None:
        self.cfg = cfg

    @property
    def model(self) -> str:
        return self.cfg.model

    def ocr_image(self, image_path: str | Path, lang: str, iast: bool = False) -> str:
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode()
        prompt = _OCR_PROMPTS.get(lang) or _GENERIC_PROMPT.format(
            langname=profile(lang).name
        )
        if iast:
            prompt += IAST_SUFFIX
        payload = {
            "model": self.cfg.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=self.cfg.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise OCRError(f"OCR request failed for {path.name}: {exc}") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise OCRError(f"Malformed OCR response: {json.dumps(data)[:300]}") from exc
        return content.strip()

    def health(self) -> dict:
        url = self.cfg.base_url.rstrip("/") + "/models"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return {"ok": True, "models": [m.get("id") for m in resp.json().get("data", [])]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class MockOCRBackend:
    """Deterministic offline OCR for tests and dry-runs: emits a fixed sample
    passage per language (seeded by filename for variety)."""

    SAMPLES = {
        "lzh": "桂枝湯主治風寒表虛證。甘草二兩，桂枝三兩。",
        "zh": "桂枝汤主治风寒表虚证。甘草二两，桂枝三两。",
        "sa": "आमलकी फलं रसायनम्। ज्वरस्य चिकित्सा॥",
        "th": "ขมิ้นชัน รักษาโรคผิวหนัง ใบบัวบก เย็นต่อร่างกาย",
        "vi": "rau má chữa bỏng, nghệ chữa đau dạ dày",
        "id": "kunyit untuk luka, pegagan untuk kesehatan",
    }
    FALLBACK = "A plant-based remedy is described. Dose: 3 g."

    def __init__(self) -> None:
        self.model = "mock-ocr"

    def ocr_image(self, image_path: str | Path, lang: str, iast: bool = False) -> str:
        seed = sum(ord(c) for c in Path(image_path).name)
        samples = self.SAMPLES.get(lang)
        if not samples:
            return self.FALLBACK
        lines = samples.split(". ") if lang not in ("zh", "lzh") else [
            s + "。" for s in samples.replace("。", "").split("，")
        ]
        return "\n".join(lines[seed % len(lines):] + lines[: seed % len(lines)])


def get_ocr_backend(cfg: OCRBackendConfig | None = None) -> "VLMOCRBackend | MockOCRBackend":
    cfg = cfg or OCRBackendConfig.from_env()
    if cfg.kind == "mock":
        return MockOCRBackend()
    if cfg.kind == "vlm":
        if not cfg.base_url:
            raise OCRError(
                "vlm OCR backend needs TMTRANS_OCR_BASE_URL (or TMTRANS_BASE_URL)"
            )
        return VLMOCRBackend(cfg)
    raise OCRError(f"Unknown OCR backend kind: {cfg.kind}")


def _ocr_by_lines(img: Path, backend, lang: str, iast: bool, reading_order: str) -> list[Line]:
    """Line-segmentation-first recognition: detect line boxes with surya, crop
    each line, OCR the crop, and stitch in reading order. Falls back to
    whole-page OCR when detection finds nothing."""
    import tempfile

    detected = [ln for ln in segment_lines_surya(img) if ln.bbox]
    if not detected:
        text = backend.ocr_image(img, lang, iast)
        return [Line(text=t) for t in text.splitlines() if t.strip()]
    detected = order_lines(detected, "rtl-columns" if reading_order == "rtl-columns" else "ltr-lines")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise OCRError("line cropping requires Pillow: pip install 'tmtrans[ocr]'") from exc
    lines: list[Line] = []
    with tempfile.TemporaryDirectory() as td, Image.open(img) as im:
        for j, ln in enumerate(detected):
            x, y, w, h = ln.bbox
            crop_path = Path(td) / f"line-{j:03d}.png"
            im.crop((max(0, int(x)), max(0, int(y)), int(x + w) + 1, int(y + h) + 1)).save(crop_path)
            text = backend.ocr_image(crop_path, lang, iast)
            if text.strip():
                lines.append(Line(text=text.strip(), bbox=ln.bbox))
    return lines


def ocr_folder(
    folder: str | Path,
    lang: str,
    backend,
    reading_order: str = "auto",
    iast: bool = False,
    line_segmentation: str = "none",  # none | surya
    progress=None,
) -> list[PageResult]:
    """OCR every image in a folder (natural page order).

    line_segmentation='surya' crops line boxes first (palm leaves, Samut Khoi)
    so small diacritics survive at full resolution; each crop is OCR'd
    individually and lines are stitched in reading order.
    """
    images = discover_images(folder)
    model = getattr(backend, "model", "unknown")
    pages: list[PageResult] = []
    for i, img in enumerate(images, start=1):
        if line_segmentation == "surya":
            lines = _ocr_by_lines(img, backend, lang, iast, reading_order)
        else:
            text = backend.ocr_image(img, lang, iast)
            lines = [Line(text=t.strip()) for t in text.splitlines() if t.strip()]
        pages.append(
            PageResult(image=img.name, page=i, lines=lines, backend=type(backend).__name__, model=model)
        )
        if progress:
            progress(i, len(images), img.name)
    return pages


def write_jsonl(pages: list[PageResult], path: str | Path, lang: str, reading_order: str, iast: bool) -> None:
    import json as _json

    with open(path, "w", encoding="utf-8") as fh:
        for p in pages:
            fh.write(
                _json.dumps(
                    {
                        "image": p.image,
                        "page": p.page,
                        "lang": lang,
                        "reading_order": reading_order,
                        "iast": iast,
                        "backend": p.backend,
                        "model": p.model,
                        "text": p.text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def segments_from_jsonl(path: str | Path):
    """Turn an OCR JSONL file into pipeline segments (page-aware)."""
    from .segment import Segment, segment_text

    segments = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            page = rec.get("page")
            for seg in segment_text(rec.get("text", ""), page=page):
                seg.index = len(segments)
                segments.append(seg)
    return segments
