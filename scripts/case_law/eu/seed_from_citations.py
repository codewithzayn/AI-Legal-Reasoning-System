#!/usr/bin/env python3
"""
Seed EU case law from existing cited_eu_cases in Finnish decisions.

Queries all unique cited_eu_cases from existing KKO/KHO data,
resolves them to CELEX numbers via EUR-Lex SPARQL, and ingests
bilingual (EN+FI) via EUIngestionManager.

Usage:
    python scripts/case_law/eu/seed_from_citations.py
"""

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from supabase import create_client

from src.config.logging_config import setup_logger
from src.config.settings import config  # noqa: F401 – triggers load_dotenv

logger = setup_logger(__name__)


async def main() -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_KEY required")
        sys.exit(1)

    sb = create_client(url, key)

    # 1. Collect all unique cited_eu_cases from existing Finnish decisions
    logger.info("Querying existing cited_eu_cases from KKO/KHO decisions...")
    resp = sb.table("case_law").select("cited_eu_cases").not_.is_("cited_eu_cases", "null").execute()

    all_citations: set[str] = set()
    for row in resp.data or []:
        citations = row.get("cited_eu_cases") or []
        for cite in citations:
            if cite and isinstance(cite, str) and cite.strip():
                all_citations.add(cite.strip())

    if not all_citations:
        logger.info("No EU case citations found in existing data.")
        return

    logger.info("Found %s unique EU case citations", len(all_citations))

    # 2. Extract case numbers (C-xxx/xx patterns) from citations
    case_numbers: set[str] = set()
    for cite in all_citations:
        m = re.search(r"[CT]-\d+/\d{2,4}", cite)
        if m:
            case_numbers.add(m.group(0))

    logger.info("Extracted %s EU case numbers from citations", len(case_numbers))

    # 3. Convert case numbers to CELEX numbers directly
    # CELEX format: 6{YYYY}{COURT}{NNNN} where COURT=CJ (C-) or TJ (T-)
    celex_numbers: list[str] = []

    for case_num in sorted(case_numbers):
        m = re.match(r"([CT])-(\d+)/(\d{2,4})", case_num)
        if not m:
            logger.warning("  %s → cannot parse", case_num)
            continue
        court_letter, num_str, year_str = m.group(1), m.group(2), m.group(3)
        # Resolve 2-digit year
        if len(year_str) == 2:
            yr = int(year_str)
            full_year = 1900 + yr if yr >= 50 else 2000 + yr
        else:
            full_year = int(year_str)
        court_code = "CJ" if court_letter == "C" else "TJ"
        celex = f"6{full_year}{court_code}{num_str.zfill(4)}"
        celex_numbers.append(celex)
        logger.info("  %s → CELEX %s", case_num, celex)

    if not celex_numbers:
        logger.info("No CELEX numbers resolved. Nothing to ingest.")
        return

    logger.info("Resolved %s CELEX numbers. Starting bilingual ingestion...", len(celex_numbers))

    # 4. Ingest bilingual
    from scripts.case_law.eu.eu_ingestion_manager import EUIngestionManager

    manager = EUIngestionManager()
    failed = await manager.ingest_by_celex(celex_numbers, languages=["EN", "FI"])

    if failed:
        logger.error("Failed: %s", failed)
    else:
        logger.info("All seeded cases ingested successfully.")


if __name__ == "__main__":
    asyncio.run(main())
