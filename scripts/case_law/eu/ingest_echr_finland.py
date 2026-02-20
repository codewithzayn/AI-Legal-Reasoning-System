#!/usr/bin/env python3
"""
Ingest all ECHR cases involving Finland as respondent.

Uses HUDOC API to find cases with respondent='FIN', then ingests them.

Usage:
    python scripts/case_law/eu/ingest_echr_finland.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


async def main() -> None:
    from scripts.case_law.eu.eu_ingestion_manager import EUIngestionManager

    manager = EUIngestionManager()
    logger.info("Ingesting ECHR cases involving Finland...")
    failed = await manager.ingest_echr_finland()

    if failed:
        logger.error("Failed cases (%s): %s", len(failed), failed)
        sys.exit(1)
    else:
        logger.info("All ECHR Finland cases ingested successfully.")


if __name__ == "__main__":
    asyncio.run(main())
