"""Deterministic entity ids (uuid5) for stable run-to-run comparison.

Ids must stay stable across runs of the same PDF — two JSON dumps can be
diffed block-by-block when debugging OCR/layout changes — and they are
the future DB keys.
"""

from __future__ import annotations

import uuid

# Fixed namespace for all scriber uuid5 ids. Never change this value:
# every id ever persisted (DB, dumps, crops naming) would go stale.
# TODO: put this in the env / config later on
ID_NAMESPACE = uuid.UUID("0b6d6a9e-8b6f-4c3f-9f2e-1d5c7b9a3e21")


def stable_id(*parts: str) -> str:
    """uuid5 over the ":"-joined parts — same inputs, same id, always."""
    return str(uuid.uuid5(ID_NAMESPACE, ":".join(parts)))
