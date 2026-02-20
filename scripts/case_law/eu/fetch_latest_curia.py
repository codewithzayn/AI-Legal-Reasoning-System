#!/usr/bin/env python3
"""
Fetch latest CURIA decisions (last 14 days) and ingest into Supabase.

Usage:
    python scripts/case_law/eu/fetch_latest_curia.py [--days 14] [--language en]

Designed to run daily/weekly via cron.
"""

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.config.logging_config import setup_logger
from src.services.case_law.models import CaseLawDocument
from src.services.case_law.storage import CaseLawStorage
from src.services.eu_case_law.courts import EU_COURT_CODES, build_eu_case_url
from src.services.eu_case_law.curia_scraper import CuriaScraper
from src.services.eu_case_law.extractor import EUCaseExtractor

logger = setup_logger(__name__)


async def main(days: int = 14, language: str = "en") -> None:
    scraper = CuriaScraper()
    extractor = EUCaseExtractor()
    storage = CaseLawStorage()

    logger.info("Fetching latest CURIA decisions (last %s days, lang=%s)...", days, language)
    decisions = await scraper.fetch_recent_decisions(days=days, language=language)

    if not decisions:
        logger.info("No recent decisions found.")
        return

    stored = 0
    failed = 0
    for i, decision in enumerate(decisions, 1):
        case_number = decision.get("case_number", "")
        court_type = decision.get("court_type", "cjeu")
        logger.info("[%s/%s] %s", i, len(decisions), case_number)

        # Fetch full text if not already present
        full_text = decision.get("full_text", "")
        if not full_text and case_number:
            detail = await scraper.fetch_decision_by_case_number(case_number, language)
            if detail:
                full_text = detail.get("full_text", "")
                decision.update({k: v for k, v in detail.items() if v and not decision.get(k)})

        if not full_text:
            logger.warning("[%s/%s] %s: no full text, skipping", i, len(decisions), case_number)
            failed += 1
            continue

        ecli = decision.get("ecli", "")
        case_id = ecli if ecli else f"CURIA:{case_number}"

        # Parse year from date
        year = 0
        date_str = decision.get("date", "")
        if date_str:
            parts = date_str.split("/")
            if len(parts) == 3 and len(parts[2]) == 4:
                with contextlib.suppress(ValueError):
                    year = int(parts[2])

        sections = extractor.extract_cjeu(full_text, case_id, language.upper())

        doc = CaseLawDocument(
            case_id=case_id,
            court_type=court_type,
            court_code=EU_COURT_CODES.get(court_type, "CJEU"),
            decision_type="judgment",
            case_year=year,
            ecli=ecli or None,
            title=decision.get("title", case_number),
            full_text=full_text,
            url=decision.get("url", build_eu_case_url(court_type, case_number)),
            primary_language="English" if language == "en" else "Finnish",
            eu_case_number=case_number,
            language_of_case=language.upper(),
        )
        doc.ai_sections = sections

        result = storage.store_case(doc)
        if result:
            stored += 1
        else:
            failed += 1

    logger.info("CURIA fetch complete: %s stored, %s failed out of %s", stored, failed, len(decisions))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch latest CURIA decisions")
    parser.add_argument("--days", type=int, default=14, help="Days to look back (default: 14)")
    parser.add_argument("--language", type=str, default="en", help="Language (en/fi, default: en)")
    args = parser.parse_args()
    asyncio.run(main(days=args.days, language=args.language))
