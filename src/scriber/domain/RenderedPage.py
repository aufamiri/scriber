from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenderedPage:
    """A single PDF page rendered to a PNG on disk (Rasterizer)."""

    page_number: int
    image_path: Path
    width: int
    height: int
