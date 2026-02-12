"""
Extended chunk inspector – shows ALL chunks with keyword matching.

Run from project root: python3 scripts/inspect_case_chunks.py
"""

import asyncio
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

os.environ.setdefault("LOG_FORMAT", "simple")

from src.config.logging_config import setup_logger
from src.services.retrieval.search import HybridRetrieval

logger = setup_logger(__name__)


async def inspect_all_chunks() -> None:
    retrieval = HybridRetrieval()
    chunks = await retrieval.fetch_case_chunks("KKO:1995:213")

    logger.info("Total chunks: %s", len(chunks))
    logger.info("")

    keywords = [
        "osakkeenomistaja",
        "puuttua",
        "oikeudenkäyntiin",
        "välitulo",
        "puhevalta",
        "intervene",
        "edellytykset",
    ]

    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("text", "")
        section_type = chunk.get("metadata", {}).get("type", "?")
        matches = [kw for kw in keywords if kw in text.lower()]

        logger.info("CHUNK %s | Type: %s | Keywords: %s/%s", i, section_type, len(matches), len(keywords))
        if matches:
            logger.info("  Keywords found: %s", ", ".join(matches))
        else:
            logger.info("  No keywords found")
        logger.info("%s", text)
        logger.info("")


if __name__ == "__main__":
    asyncio.run(inspect_all_chunks())
