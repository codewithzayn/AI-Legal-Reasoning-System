"""
Test provision extraction on sample KKO cases.

This script fetches random KKO cases and tests the extraction logic,
showing what provisions are being extracted and their quality.

Usage:
    python scripts/case_law/core/test_provision_extraction.py [--sample-size 10] [--min-text-length 1000]
"""

import sys
from argparse import ArgumentParser

from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger
from src.services.case_law.regex_extractor import _extract_applied_provisions_from_text

logger = setup_logger(__name__)


class ProvisionExtractionTester:
    """Test provision extraction on sample cases."""

    def __init__(self) -> None:
        """Initialize tester."""
        self.sb = get_supabase_client()

    def test_random_samples(self, sample_size: int = 10, min_text_length: int = 1000) -> None:
        """Test extraction on random KKO cases.

        Args:
            sample_size: Number of random cases to test.
            min_text_length: Minimum full_text length to consider.
        """
        logger.info(f"🧪 Testing extraction on {sample_size} random KKO cases (min_text_length={min_text_length})")

        try:
            response = (
                self.sb.table("case_law")
                .select("case_id, full_text, applied_provisions, case_year")
                .eq("court_code", "KKO")
                .limit(sample_size * 3)  # Fetch more to account for filtering
                .execute()
            )
            all_cases = response.data if response.data else []

            # Randomly sample in Python
            import random

            cases = random.sample(all_cases, min(sample_size, len(all_cases)))
            logger.info(f"Fetched {len(cases)} random KKO cases")
        except Exception as e:
            logger.error(f"Failed to fetch cases: {e}")
            return

        if not cases:
            logger.warning("No KKO cases found")
            return

        stats = {
            "total": 0,
            "extracted": 0,
            "already_populated": 0,
            "empty_fulltext": 0,
            "failed": 0,
            "avg_extraction_length": 0.0,
            "extraction_lengths": [],
        }

        for i, case in enumerate(cases, 1):
            case_id = case.get("case_id", "")
            full_text = case.get("full_text", "") or ""
            existing_provisions = case.get("applied_provisions", "") or ""
            year = case.get("case_year", "")

            stats["total"] += 1

            # Check if already populated
            if existing_provisions and existing_provisions.strip():
                logger.info(
                    f"[{i}/{len(cases)}] {case_id} ({year}) | ✅ Already populated: {existing_provisions[:80]}..."
                )
                stats["already_populated"] += 1
                continue

            # Check text length
            if not full_text or len(full_text) < min_text_length:
                logger.warning(f"[{i}/{len(cases)}] {case_id} ({year}) | ⏭  Empty/short text ({len(full_text)} chars)")
                stats["empty_fulltext"] += 1
                continue

            # Extract
            try:
                extracted = _extract_applied_provisions_from_text(full_text)

                if extracted:
                    stats["extracted"] += 1
                    stats["extraction_lengths"].append(len(extracted))
                    logger.info(
                        f"[{i}/{len(cases)}] {case_id} ({year}) | ✅ Extracted ({len(extracted)} chars): {extracted[:100]}..."
                    )
                else:
                    logger.warning(
                        f"[{i}/{len(cases)}] {case_id} ({year}) | ⚠️  No provisions found in {len(full_text)} chars"
                    )
            except Exception as e:
                logger.error(f"[{i}/{len(cases)}] {case_id} ({year}) | ❌ Extraction failed: {e}")
                stats["failed"] += 1

        # Print summary
        self._print_test_summary(stats)

    def test_specific_case(self, case_id: str) -> None:
        """Test extraction on a specific case.

        Args:
            case_id: Case ID to test (e.g., 'KKO:2024:76').
        """
        logger.info(f"🧪 Testing extraction for case: {case_id}")

        try:
            response = (
                self.sb.table("case_law")
                .select("case_id, full_text, applied_provisions, case_year")
                .eq("case_id", case_id)
                .execute()
            )
            cases = response.data if response.data else []
        except Exception as e:
            logger.error(f"Failed to fetch case: {e}")
            return

        if not cases:
            logger.error(f"Case not found: {case_id}")
            return

        case = cases[0]
        full_text = case.get("full_text", "") or ""
        existing_provisions = case.get("applied_provisions", "") or ""
        year = case.get("case_year", "")

        logger.info(f"Case: {case_id} ({year})")
        logger.info(f"Full text length: {len(full_text)} chars")
        logger.info(f"Already in DB: {existing_provisions if existing_provisions else '(empty)'}")
        logger.info("")

        if not full_text:
            logger.warning("No full_text available for this case")
            return

        # Extract
        try:
            extracted = _extract_applied_provisions_from_text(full_text)
            logger.info(f"Extracted ({len(extracted)} chars):")
            logger.info(f"  {extracted}")

            if not extracted:
                logger.warning("No provisions extracted - checking full_text structure...")
                self._debug_text_structure(full_text, case_id)

        except Exception as e:
            logger.error(f"Extraction failed: {e}")

    @staticmethod
    def _debug_text_structure(full_text: str, case_id: str) -> None:
        """Debug text structure to understand why extraction failed."""
        import re

        lines = full_text.split("\n")
        logger.info(f"First 50 lines of {case_id}:")

        # Find section headers
        section_patterns = [
            r"Reasoning|Perustelut",
            r"Judgment|Tuomiolauselma",
            r"Background|Asian tausta",
            r"Lower court|Asian käsittely",
        ]

        for i, line in enumerate(lines[:50], 1):
            # Highlight section headers
            is_header = any(re.search(p, line, re.IGNORECASE) for p in section_patterns)
            marker = ">>> " if is_header else "    "
            logger.info(f"{marker}[{i}] {line[:100]}")

    def _print_test_summary(self, stats: dict) -> None:
        """Print test summary."""
        logger.info("=" * 70)
        logger.info("EXTRACTION TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total cases tested:        {stats['total']}")
        logger.info(f"Already populated in DB:   {stats['already_populated']}")
        logger.info(f"Empty/short text:          {stats['empty_fulltext']}")
        logger.info(f"Successfully extracted:    {stats['extracted']}")
        logger.info(f"Failed extractions:        {stats['failed']}")

        if stats["extraction_lengths"]:
            avg_len = sum(stats["extraction_lengths"]) / len(stats["extraction_lengths"])
            logger.info(f"Avg extraction length:     {avg_len:.0f} chars")
            logger.info(f"Min extraction length:     {min(stats['extraction_lengths'])} chars")
            logger.info(f"Max extraction length:     {max(stats['extraction_lengths'])} chars")

        extraction_rate = (stats["extracted"] / max(1, stats["total"])) * 100 if stats["total"] > 0 else 0
        logger.info(f"Extraction success rate:   {extraction_rate:.1f}%")
        logger.info("=" * 70)

        if extraction_rate < 50:
            logger.warning("⚠️  Low extraction rate detected! Check text structure or patterns may need refinement.")


async def main() -> None:
    """Main entry point."""
    parser = ArgumentParser(description="Test provision extraction on KKO cases")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of random cases to test (default: 10)",
    )
    parser.add_argument(
        "--min-text-length",
        type=int,
        default=1000,
        help="Minimum full_text length to consider (default: 1000)",
    )
    parser.add_argument(
        "--case-id",
        type=str,
        help="Test specific case ID (e.g., KKO:2024:76)",
    )
    args = parser.parse_args()

    tester = ProvisionExtractionTester()

    if args.case_id:
        tester.test_specific_case(args.case_id)
    else:
        tester.test_random_samples(sample_size=args.sample_size, min_text_length=args.min_text_length)


if __name__ == "__main__":
    try:
        import asyncio

        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
