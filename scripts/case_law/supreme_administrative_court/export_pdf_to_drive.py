"""
Supreme Administrative Court (KHO): Export JSON → PDF → Google Drive (no scraping).

Thin wrapper around the court-agnostic core pipeline.

Equivalent to running:
  python scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court ...

Usage:
  python scripts/case_law/supreme_administrative_court/export_pdf_to_drive.py --year 2025
  python scripts/case_law/supreme_administrative_court/export_pdf_to_drive.py --start 2020 --end 2026
  python scripts/case_law/supreme_administrative_court/export_pdf_to_drive.py --type precedent --year 2025
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os

os.environ.setdefault("LOG_FORMAT", "simple")

# Inject --court into argv so the core main() picks up KHO without the caller needing to type it
if "--court" not in sys.argv:
    sys.argv.insert(1, "--court")
    sys.argv.insert(2, "supreme_administrative_court")

from scripts.case_law.core.export_pdf_to_drive import main

if __name__ == "__main__":
    sys.exit(main())
