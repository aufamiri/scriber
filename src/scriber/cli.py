"""CLI entry point.

Usage:
    scriber <pdf> [options]

Runs Rasterizer -> LayoutDetector -> OCREngine -> block processing and
writes a JSON dump of the per-page results.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scriber.config import ScriberConfig
from scriber.pipeline import Pipeline, dump_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scriber",
        description="OCR a scanned PDF (core flow: rasterize, layout, "
                    "OCR, block processing). Outputs a JSON dump of page results.",
    )
    parser.add_argument("pdf", type=Path, help="source PDF file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="path for the JSON result dump "
             "(default: <cache-dir>/results/<job-id>.json)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="render DPI, 72-300 (default: 200)",
    )
    parser.add_argument(
        "--title-confidence-threshold",
        type=float,
        default=None,
        help="OCR confidence below which Title/SectionHeader blocks are "
             "flagged for image embedding (default: 0.5)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="cache directory for page images and crops "
             "(default: ~/.cache/pdf-ocr)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="process only the first N pages (smoke-testing a full novel)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="pages per layout+OCR batch (default: 8)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    config = ScriberConfig.from_env()
    if args.dpi is not None:
        config.dpi = args.dpi
    if args.title_confidence_threshold is not None:
        config.title_confidence_threshold = args.title_confidence_threshold
    if args.cache_dir is not None:
        config.cache_dir = args.cache_dir
    if args.pages is not None:
        config.max_pages = args.pages
    if args.batch_size is not None:
        config.page_batch_size = args.batch_size

    try:
        pipeline = Pipeline(config)
        results = pipeline.run(args.pdf)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    output = args.output
    if output is None:
        output = config.cache_dir / "results" / f"{pipeline.job_id(args.pdf)}.json"

    try:
        dump_json(args.pdf, results, output, config)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    kept = sum(
        1 for page in results for block in page.blocks if not block.dropped
    )
    dropped = sum(1 for page in results for block in page.blocks if block.dropped)
    images = sum(
        1 for page in results for block in page.blocks if block.embed_as_image
    )
    print(
        f"result: {len(results)} page(s), {kept} kept blocks "
        f"({images} image-embedded), {dropped} dropped"
    )
    print(f"JSON dump written to {output}")


if __name__ == "__main__":
    main()
