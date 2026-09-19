#!/usr/bin/env python
"""Patch surya-ocr's llamacpp grammar bug (datalab-to/surya#542).

surya <= 0.22.1 defines bbox JSON-schema patterns with `\\d{1,4}` escapes
(see `surya/inference/prompts.py`). The llamacpp inference backend converts
these schemas into llama.cpp GBNF grammars, and llama.cpp rejects `\\d` as an
unknown escape, causing:

    Inference error: Error code: 400 - ... Failed to initialize samplers:
    failed to parse grammar

This script replaces `\\d` with `[0-9]` (semantically identical in regex) in
the installed surya package so the generated grammar parses. It is idempotent
and safe to re-run after every `uv sync` / surya reinstall.

Usage:
    uv run python patch_surya.py
"""

import importlib
import sys
from pathlib import Path

BAD_PATTERN = r"^\d{1,4} \d{1,4} \d{1,4} \d{1,4}$"
GOOD_PATTERN = r"^[0-9]{1,4} [0-9]{1,4} [0-9]{1,4} [0-9]{1,4}$"
TARGET_REL = Path("surya") / "inference" / "prompts.py"


def find_prompts_py() -> Path:
    """Locate the installed surya/inference/prompts.py."""
    try:
        surya_inference = importlib.import_module("surya.inference.prompts")
    except ImportError as e:
        sys.exit(f"error: could not import surya.inference.prompts: {e}")

    # Prefer the real source file, not a frozen/embedded loader
    file = getattr(surya_inference, "__file__", None)
    if not file:
        sys.exit("error: surya.inference.prompts has no __file__; cannot patch")
    return Path(file).resolve()


def clear_stale_pyc(prompts_py: Path) -> None:
    """Remove cached bytecode so the patch takes effect immediately."""
    pyc_dir = prompts_py.parent / "__pycache__"
    if pyc_dir.is_dir():
        for pyc in pyc_dir.glob("prompts.cpython-*.pyc"):
            pyc.unlink(missing_ok=True)
            print(f"removed stale bytecode: {pyc}")


def main() -> None:
    prompts_py = find_prompts_py()

    # Sanity-check we're patching the expected package, not something else
    if prompts_py.parent.name != "inference" or prompts_py.stem != "prompts":
        sys.exit(f"error: unexpected path {prompts_py}; refusing to patch")

    text = prompts_py.read_text(encoding="utf-8")

    if GOOD_PATTERN in text and BAD_PATTERN not in text:
        print(f"already patched: {prompts_py}")
        clear_stale_pyc(prompts_py)
        return

    if BAD_PATTERN not in text:
        # Upstream may have fixed it with different syntax, or the file
        # changed significantly — flag it for manual review.
        sys.exit(
            f"error: expected pattern not found in {prompts_py}.\n"
            "surya may have changed; check if the upstream fix "
            "(datalab-to/surya#542) has been released and remove this patch."
        )

    patched = text.replace(BAD_PATTERN, GOOD_PATTERN)
    prompts_py.write_text(patched, encoding="utf-8")
    print(f"patched: {prompts_py}")
    print(f"  {text.count(BAD_PATTERN)} occurrence(s) of \\d -> [0-9]")
    clear_stale_pyc(prompts_py)

    # Verify the patched schema imports cleanly
    importlib.reload(importlib.import_module("surya.inference.prompts"))
    print("verified: surya.inference.prompts imports with patched schema")


if __name__ == "__main__":
    main()
