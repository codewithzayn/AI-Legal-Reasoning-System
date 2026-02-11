"""
Extended chunk inspector - shows ALL chunks with keyword matching
"""

import asyncio
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.services.retrieval.search import HybridRetrieval


async def inspect_all_chunks():
    retrieval = HybridRetrieval()
    chunks = await retrieval.fetch_case_chunks("KKO:1995:213")

    print(f"Total chunks: {len(chunks)}\n")

    # Keywords to look for
    keywords = ["osakkeenomistaja", "puuttua", "oikeudenkäyntiin", "välitulo", "puhevalta", "intervene", "edellytykset"]

    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("text", "")
        section_type = chunk.get("metadata", {}).get("type", "?")

        # Count keyword matches
        matches = [kw for kw in keywords if kw in text.lower()]

        print(f"\n{'=' * 60}")
        print(f"CHUNK {i} | Type: {section_type} | Keywords: {len(matches)}/{len(keywords)}")
        print("=" * 60)

        if matches:
            print(f"✓ Keywords found: {', '.join(matches)}\n")
        else:
            print("✗ No keywords found\n")

        # Show full text (not truncated)
        print(text)
        print()


asyncio.run(inspect_all_chunks())
