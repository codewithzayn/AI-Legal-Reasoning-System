#!/usr/bin/env python3
"""
CLI entry point for EU case law ingestion.

Usage:
    python scripts/case_law/eu/ingest_eu.py --court cjeu --year 2024
    python scripts/case_law/eu/ingest_eu.py --court echr --year 2023
    python scripts/case_law/eu/ingest_eu.py --celex 62018CJ0311 62019CJ0078 --languages EN FI
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest EU case law")
    parser.add_argument("--court", type=str, default="cjeu", help="Court type: cjeu, general_court, echr")
    parser.add_argument("--year", type=int, default=None, help="Year to ingest")
    parser.add_argument("--celex", nargs="+", default=None, help="Specific CELEX numbers to ingest")
    parser.add_argument("--languages", nargs="+", default=["EN", "FI"], help="Languages (default: EN FI)")
    parser.add_argument("--language", type=str, default="EN", help="Single language for year-based ingestion")
    args = parser.parse_args()

    from scripts.case_law.eu.eu_ingestion_manager import EUIngestionManager

    manager = EUIngestionManager()

    if args.celex:
        logger.info("Ingesting by CELEX: %s (languages: %s)", args.celex, args.languages)
        failed = await manager.ingest_by_celex(args.celex, languages=args.languages)
    elif args.year:
        logger.info("Ingesting by year: court=%s year=%s lang=%s", args.court, args.year, args.language)
        failed = await manager.ingest_by_year(court=args.court, year=args.year, language=args.language)
    else:
        parser.error("Either --year or --celex is required")
        return

    if failed:
        logger.error("Failed cases: %s", failed)
        sys.exit(1)
    else:
        logger.info("All cases ingested successfully.")


if __name__ == "__main__":
    asyncio.run(main())
