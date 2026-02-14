# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Ingest Supreme Court (KKO) cases by subtype.

Unified script that replaces the old separate ingest_leaves.py and ingest_rulings.py.
Defaults to "ruling" when called directly; pass --subtype to choose.

Usage:
  python scripts/case_law/supreme_court/ingest_rulings.py --year 2025
  python scripts/case_law/supreme_court/ingest_rulings.py --year 2025 --subtype leave_to_appeal
  python scripts/case_law/supreme_court/ingest_rulings.py --year 2025 --subtype ruling
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

VALID_SUBTYPES = ("ruling", "leave_to_appeal")


async def main(year: int, subtype: str):
    if subtype not in VALID_SUBTYPES:
        logger.error("Invalid subtype '%s'. Choose from: %s", subtype, VALID_SUBTYPES)
        sys.exit(1)
    logger.info("Starting KKO %s Ingestion for %s", subtype, year)
    manager = IngestionManager("supreme_court")
    await manager.ingest_year(year, subtype=subtype)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Rulings or Leaves to Appeal (unified script)")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument(
        "--subtype",
        choices=list(VALID_SUBTYPES),
        default="ruling",
        help="Decision subtype (default: ruling)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.year, args.subtype))
