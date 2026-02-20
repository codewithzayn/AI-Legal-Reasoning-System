"""
Supreme Administrative Court (KHO): Scrape → Save JSON → Generate PDF → Upload to Google Drive.

Thin wrapper around the court-agnostic core pipeline.
Targets KHO (korkein-hallinto-oikeus) with its three subtypes:
  - precedent  → Ennakkopäätökset
  - other      → Muut päätökset
  - brief      → Lyhyet ratkaisuselosteet

Equivalent to running:
  python scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court ...

But kept as a standalone script for clarity and Makefile ergonomics.

Usage:
  python scripts/case_law/supreme_administrative_court/scrape_json_pdf_drive.py --year 2025
  python scripts/case_law/supreme_administrative_court/scrape_json_pdf_drive.py --year 2025 --type precedent
  python scripts/case_law/supreme_administrative_court/scrape_json_pdf_drive.py --start 2020 --end 2023
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Re-use the court-agnostic core script with KHO pre-selected
import os

os.environ.setdefault("LOG_FORMAT", "simple")

# Inject --court into argv so the core main() picks up KHO without the caller needing to type it
if "--court" not in sys.argv:
    sys.argv.insert(1, "--court")
    sys.argv.insert(2, "supreme_administrative_court")

from scripts.case_law.core.scrape_json_pdf_drive import main

if __name__ == "__main__":
    sys.exit(main())
