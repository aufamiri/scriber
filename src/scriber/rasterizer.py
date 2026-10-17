"""Rasterizer: PDF -> per-page PNG images at a fixed DPI.

DPI is capped at 300 to reduce storage footprint.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from scriber.config import ScriberConfig
from scriber.domain import RenderedPage
from scriber.utils import JobIdUtil, stable_id

MAX_DPI = 300


class Rasterizer:
    def __init__(self, config: ScriberConfig, job_id_util: JobIdUtil) -> None:
        if not 72 <= config.dpi <= MAX_DPI:
            raise ValueError(
                f"dpi must be in [72, {MAX_DPI}] (got {config.dpi}); "
                "above 300 DPI adds no information from a scanned source"
            )
        self._config = config
        self._job_id_util = job_id_util

    def render(self, pdf_path: Path) -> list[RenderedPage]:
        """Render every page of the PDF to ``<cache_dir>/pages/<job_id>/``."""
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        job_id = self._job_id_util.get_job_id(pdf_path)
        out_dir = self._config.cache_dir / "pages" / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        pages: list[RenderedPage] = []
        with pymupdf.open(pdf_path) as doc:
            n_pages = len(doc)
            limit = (
                min(n_pages, self._config.max_pages)
                if self._config.max_pages is not None
                else n_pages
            )
            for i in range(limit):
                pix = doc[i].get_pixmap(dpi=self._config.dpi)
                dest = out_dir / f"page_{i:04d}.png"
                pix.save(dest)
                pages.append(
                    RenderedPage(
                        page_number=i,
                        image_path=dest,
                        width=pix.width,
                        height=pix.height,
                        id=stable_id(job_id, f"p{i}"),
                    )
                )
        return pages
