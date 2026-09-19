"""Pipeline orchestration.
"""

from __future__ import annotations

import time
from pathlib import Path

from surya.inference import SuryaInferenceManager

from scriber.config import ScriberConfig
from scriber.domain import PageResult
from scriber.layout import LayoutDetector
from scriber.ocr import OCREngine
from scriber.processing import process_page
from scriber.rasterizer import Rasterizer
from scriber.utils import JobIdUtil


class Pipeline:
    def __init__(self, config: ScriberConfig | None = None) -> None:
        self._config = config or ScriberConfig.from_env()
        self._job_id_util = JobIdUtil()
        self._rasterizer = Rasterizer(self._config, self._job_id_util)

        # One manager per process — it owns the (heavy) llama.cpp backend
        # and is shared by layout and OCR.
        surya_manager = SuryaInferenceManager()
        self._layout = LayoutDetector(surya_manager)
        self._ocr = OCREngine(surya_manager, language=self._config.language)

    @property
    def config(self) -> ScriberConfig:
        return self._config

    def job_id(self, pdf_path: Path) -> str:
        return self._job_id_util.get_job_id(pdf_path)

    def run(self, pdf_path: Path) -> list[PageResult]:
        """Run the full flow over a PDF and return per-page results."""
        pdf_path = Path(pdf_path)
        started = time.time()

        rendered = self._rasterizer.render(pdf_path)
        print(f"rasterized {len(rendered)} page(s) at {self._config.dpi} DPI")

        page_results: list[PageResult] = []
        batch_size = max(1, self._config.page_batch_size)
        for start in range(0, len(rendered), batch_size):
            batch = rendered[start: start + batch_size]

            layout_blocks = self._layout.detect(batch)

            ocr_results = self._ocr.recognize(batch, layout_blocks)

            for page, blocks, ocr in zip(
                    batch, layout_blocks, ocr_results, strict=True
            ):
                processed = process_page(page, blocks, ocr, self._config)
                result = PageResult(
                    page_number=page.page_number,
                    image_path=page.image_path,
                    width=page.width,
                    height=page.height,
                    blocks=processed,
                )
                page_results.append(result)

            done = start + len(batch)
            print(
                f"processed pages {batch[0].page_number}-{batch[-1].page_number} "
                f"({done}/{len(rendered)})"
            )

        elapsed = time.time() - started
        print(f"done: {len(page_results)} page(s) in {elapsed:.1f}s")
        return page_results


def dump_json(
        pdf_path: Path,
        pages: list[PageResult],
        dest: Path,
        config: ScriberConfig,
) -> None:
    """Serialize pipeline results to JSON for inspection and debugging."""
    import json

    payload = {
        "source": str(pdf_path),
        "generated_at": time.time(),
        "config": {
            "dpi": config.dpi,
            "title_confidence_threshold": config.title_confidence_threshold,
            "page_batch_size": config.page_batch_size,
        },
        "pages": [page.as_dict() for page in pages],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise OSError(f"failed to write JSON dump {dest}: {e}") from e
