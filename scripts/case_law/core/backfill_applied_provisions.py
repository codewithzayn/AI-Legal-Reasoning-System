"""
Backfill applied_provisions for all KKO cases in Supabase.

This script:
1. Fetches all KKO cases from Supabase
2. Extracts applied_provisions using regex patterns
3. Updates the database with extracted provisions

Usage:
    python scripts/case_law/core/backfill_applied_provisions.py [--batch-size 10] [--dry-run]
"""

import asyncio
import sys
import time
from argparse import ArgumentParser

from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger
from src.services.case_law.regex_extractor import _extract_applied_provisions_from_text

logger = setup_logger(__name__)


class ProvisionsBackfiller:
    """Backfill applied_provisions for KKO cases."""

    def __init__(self) -> None:
        """Initialize backfiller."""
        self.sb = get_supabase_client()
        self.total_cases = 0
        self.updated_cases = 0
        self.failed_cases = 0
        self.skipped_cases = 0

    async def backfill_all(self, batch_size: int = 10, dry_run: bool = False) -> None:
        """Backfill all KKO cases.

        Args:
            batch_size: Number of cases to update per batch.
            dry_run: If True, only extract but don't write to database.
        """
        logger.info("🚀 Starting backfill of applied_provisions for KKO cases (dry_run=%s)", dry_run)

        # Fetch all KKO cases (order by case_year DESC for recent cases first)
        try:
            response = (
                self.sb.table("case_law")
                .select("id, case_id, full_text, applied_provisions, case_year")
                .eq("court_code", "KKO")
                .order("case_year", desc=True)
                .execute()
            )
            cases = response.data if response.data else []
            self.total_cases = len(cases)
            logger.info(f"📊 Found {self.total_cases} KKO cases in database")
        except Exception as e:
            logger.error(f"Failed to fetch KKO cases: {e}")
            return

        if self.total_cases == 0:
            logger.warning("No KKO cases found in database")
            return

        # Process in batches
        for i in range(0, self.total_cases, batch_size):
            batch = cases[i : i + batch_size]
            await self._process_batch(batch, dry_run)

        # Print summary
        self._print_summary(dry_run)

    async def _process_batch(self, batch: list[dict], dry_run: bool) -> None:
        """Process a batch of cases."""
        batch_num = (batch[0] if batch else {}).get("case_year", "unknown")
        logger.info(
            f"Processing batch [{len(batch)} cases, year={batch_num}] ({self.updated_cases + self.skipped_cases}/{self.total_cases})"
        )

        updates = []

        for case in batch:
            case_id = case.get("case_id", "")
            full_text = case.get("full_text", "") or ""
            existing_provisions = case.get("applied_provisions", "") or ""

            # Skip if already populated (unless empty)
            if existing_provisions and existing_provisions.strip():
                self.skipped_cases += 1
                logger.debug(f"⏭  SKIP {case_id} (already populated with {len(existing_provisions)} chars)")
                continue

            if not full_text or not full_text.strip():
                self.skipped_cases += 1
                logger.warning(f"⏭  SKIP {case_id} (empty full_text)")
                continue

            try:
                # Extract provisions using regex
                extracted = _extract_applied_provisions_from_text(full_text)

                if extracted:
                    logger.info(f"✅ {case_id} | Extracted {len(extracted)} chars | {extracted[:100]}...")
                    updates.append(
                        {
                            "id": case.get("id"),
                            "case_id": case_id,
                            "applied_provisions": extracted,
                        }
                    )
                    self.updated_cases += 1
                else:
                    logger.debug(f"⚠️  {case_id} | No provisions extracted from {len(full_text)} chars of full_text")
                    self.skipped_cases += 1

            except Exception as e:
                logger.error(f"❌ {case_id} | Extraction failed: {e}")
                self.failed_cases += 1

        # Write batch to database (if not dry run)
        if updates and not dry_run:
            await self._write_batch(updates)
        elif updates and dry_run:
            logger.info(f"[DRY RUN] Would update {len(updates)} cases (not writing to DB)")

    async def _write_batch(self, updates: list[dict]) -> None:
        """Write batch of updates to database."""
        try:
            for update in updates:
                case_id = update.get("case_id")
                try:
                    self.sb.table("case_law").update({"applied_provisions": update.get("applied_provisions")}).eq(
                        "id", update.get("id")
                    ).execute()
                    logger.debug(f"✅ Stored applied_provisions for {case_id}")
                except Exception as e:
                    logger.error(f"Failed to update {case_id} in database: {e}")
                    self.failed_cases += 1
                    self.updated_cases -= 1
        except Exception as e:
            logger.error(f"Batch write failed: {e}")

    def _print_summary(self, dry_run: bool) -> None:
        """Print summary statistics."""
        logger.info("=" * 60)
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total cases processed:   {self.total_cases}")
        logger.info(f"Successfully updated:    {self.updated_cases}")
        logger.info(f"Skipped (already filled): {self.skipped_cases}")
        logger.info(f"Failed extractions:      {self.failed_cases}")
        logger.info(f"Success rate:            {(self.updated_cases / max(1, self.total_cases)) * 100:.1f}%")
        logger.info("=" * 60)


async def main() -> None:
    """Main entry point."""
    parser = ArgumentParser(description="Backfill applied_provisions for KKO cases")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for updates (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't write to database")
    args = parser.parse_args()

    backfiller = ProvisionsBackfiller()
    start = time.time()
    await backfiller.backfill_all(batch_size=args.batch_size, dry_run=args.dry_run)
    elapsed = time.time() - start

    logger.info(f"⏱  Completed in {elapsed:.2f} seconds")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
