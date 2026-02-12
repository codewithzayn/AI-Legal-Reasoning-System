"""
Manually update full_text for specific case IDs in precedent JSON files.
Use when the scraper fails to extract content but you have the text (e.g. from Finlex).

Run from project root:
  python3 scripts/case_law/supreme_court/update_case_full_text.py --year 1983 --case-id KKO:1983:II-68 --file content.txt
  python3 scripts/case_law/supreme_court/update_case_full_text.py --year 1983 --case-id KKO:1983:II-68 --stdin   # paste, then Ctrl+D
Or: make update-case-full-text YEAR=1983 CASE_ID=KKO:1983:II-68 FILE=content.txt
"""

import argparse
import json
import os
import sys
from pathlib import Path

# scripts/case_law/supreme_court/update_case_full_text.py -> project root = 4 levels up
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("LOG_FORMAT", "simple")

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)
JSON_DIR = PROJECT_ROOT / "data" / "case_law" / "supreme_court" / "precedents"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update full_text for a case in precedent JSON")
    parser.add_argument("--year", type=int, required=True, help="Year (e.g. 1983)")
    parser.add_argument("--case-id", type=str, required=True, help="Case ID (e.g. KKO:1983:II-68)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to file containing full_text")
    group.add_argument("--stdin", action="store_true", help="Read full_text from stdin")
    args = parser.parse_args()

    json_path = JSON_DIR / f"{args.year}.json"
    if not json_path.exists():
        logger.error("File not found: %s", json_path)
        return 1

    if args.stdin:
        full_text = sys.stdin.read().strip()
    else:
        path = args.file
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            logger.error("File not found: %s", path)
            return 1
        full_text = path.read_text(encoding="utf-8").strip()

    if not full_text:
        logger.error("full_text is empty")
        return 1

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    found = False
    for i, item in enumerate(data):
        if item.get("case_id") == args.case_id:
            data[i]["full_text"] = full_text
            found = True
            break

    if not found:
        logger.error("case_id %s not found in %s", args.case_id, json_path.name)
        return 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Updated %s in %s (%s chars)", args.case_id, json_path.name, len(full_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
