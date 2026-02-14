# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Ingest Supreme Court (KKO) Leaves to Appeal (Valitusluvat).

Thin wrapper around the unified ingest_rulings.py script.
Equivalent to: python ingest_rulings.py --subtype leave_to_appeal --year YYYY
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.supreme_court.ingest_rulings import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Leaves to Appeal")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    args = parser.parse_args()
    asyncio.run(main(args.year, "leave_to_appeal"))
