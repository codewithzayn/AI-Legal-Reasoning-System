# Backfill vote_strength, judges_*, exceptions, weighted_factors in case_law from existing JSON
# (no full re-ingestion). Run from project root.
#
# Usage:
#   python scripts/case_law/core/backfill_vote_strength.py
#   python scripts/case_law/core/backfill_vote_strength.py --court supreme_court --start 2020 --end 2026

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")

from scripts.case_law.core.shared import get_supabase_client, load_documents_from_json, resolve_json_path
from src.config.logging_config import setup_logger
from src.services.case_law.regex_extractor import (
    _extract_applied_provisions_from_text,
    _extract_distinctive_facts_from_text,
    _extract_exceptions_from_text,
    _extract_reasoning_excerpt,
    _extract_ruling_instruction_from_text,
    _extract_vote_from_text,
)

logger = setup_logger(__name__)

COURTS = ["supreme_court", "supreme_administrative_court"]
PRECEDENT_SUBTYPE = "precedent"

_EXTRACTORS: list[tuple[str, object]] = [
    ("exceptions", _extract_exceptions_from_text),
    ("ruling_instruction", _extract_ruling_instruction_from_text),
    ("distinctive_facts", _extract_distinctive_facts_from_text),
    ("applied_provisions", _extract_applied_provisions_from_text),
]


def _build_doc_payload(full_text: str) -> dict[str, object]:
    """Extract all depth-analysis fields from full_text into a Supabase update payload."""
    payload: dict[str, object] = {}
    total, dissenting, strength = _extract_vote_from_text(full_text)
    if strength:
        payload["vote_strength"] = strength
        payload["judges_dissenting"] = dissenting
        payload["judges_total"] = total
    weighted_factors = _extract_reasoning_excerpt(full_text, max_chars=1500)
    if weighted_factors:
        payload["weighted_factors"] = weighted_factors
    for column, extractor in _EXTRACTORS:
        value = extractor(full_text)
        if value:
            payload[column] = value
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill vote_strength, judges_*, exceptions, weighted_factors in case_law from JSON"
    )
    parser.add_argument("--court", choices=COURTS, default=None, help="Limit to one court (default: both)")
    parser.add_argument("--start", type=int, default=1926, help="Start year")
    parser.add_argument("--end", type=int, default=2026, help="End year")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase")
    args = parser.parse_args()

    try:
        client = get_supabase_client()
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)

    courts = [args.court] if args.court else COURTS
    updated = 0
    skipped = 0
    errors = 0

    for court in courts:
        for year in range(args.start, args.end + 1):
            json_path = resolve_json_path(court, year, PRECEDENT_SUBTYPE, PROJECT_ROOT)
            if not json_path.exists():
                continue
            docs = load_documents_from_json(json_path)
            for doc in docs:
                full_text = getattr(doc, "full_text", None) or ""
                if not full_text.strip():
                    skipped += 1
                    continue
                payload = _build_doc_payload(full_text)
                if not payload:
                    skipped += 1
                    continue
                if args.dry_run:
                    logger.info("[DRY-RUN] %s -> %s", doc.case_id, payload)
                    updated += 1
                    continue
                try:
                    r = client.table("case_law").update(payload).eq("case_id", doc.case_id).execute()
                    if r.data and len(r.data) > 0:
                        updated += 1
                        logger.info("%s -> %s", doc.case_id, list(payload.keys()))
                except Exception as e:
                    errors += 1
                    logger.warning("%s update failed: %s", doc.case_id, e)

    logger.info("Done: updated=%s skipped=%s errors=%s", updated, skipped, errors)


if __name__ == "__main__":
    main()
