"""Pipeline configuration.

Precedence (highest to lowest):
1. CLI arguments (applied by the CLI after construction)
2. Environment variables (PDF_OCR_*)
3. Config file (future work, with the save-state handler)
4. Hard-coded defaults (this module)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_PREFIX = "PDF_OCR_"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    return Path(raw).expanduser() if raw else default


@dataclass
class ScriberConfig:
    dpi: int = 200
    title_confidence_threshold: float = 0.5
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "pdf-ocr"
    )
    # Pages per layout+OCR batch.
    page_batch_size: int = 8
    # Optional hard cap on pages processed — handy for smoke-testing a
    # full novel PDF. None means all pages.
    max_pages: int | None = None

    @classmethod
    def from_env(cls) -> ScriberConfig:
        return cls(
            dpi=_env_int("DPI", cls.dpi),
            title_confidence_threshold=_env_float(
                "TITLE_CONFIDENCE_THRESHOLD", cls.title_confidence_threshold
            ),
            cache_dir=_env_path("CACHE_DIR", Path.home() / ".cache" / "pdf-ocr"),
            page_batch_size=_env_int("PAGE_BATCH_SIZE", cls.page_batch_size),
        )
