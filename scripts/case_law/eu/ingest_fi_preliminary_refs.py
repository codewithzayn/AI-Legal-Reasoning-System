#!/usr/bin/env python3
"""
Ingest all CJEU preliminary rulings referred by Finnish courts.

Uses EUR-Lex SPARQL to find cases where referring_member_state = 'FIN',
then ingests bilingual (EN+FI) versions.

Usage:
    python scripts/case_law/eu/ingest_fi_preliminary_refs.py
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
    logger.info("Ingesting Finnish preliminary references from CJEU...")
    failed = await manager.ingest_finland_references()

    if failed:
        logger.error("Failed cases (%s): %s", len(failed), failed)
        sys.exit(1)
    else:
        logger.info("All Finnish preliminary references ingested successfully.")


if __name__ == "__main__":
    asyncio.run(main())
