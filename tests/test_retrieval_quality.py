"""Retrieval quality evaluation - measures MRR, Recall@K.
Run from project root: python -m pytest tests/test_retrieval_quality.py -v
Or: python tests/test_retrieval_quality.py (after path fix below)
"""

import asyncio
import os
import sys
from pathlib import Path

# Match main app log format (message only, no JSON)
os.environ.setdefault("LOG_FORMAT", "simple")

# Add project root so "src" is importable when run as script
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.config.logging_config import setup_logger
from src.services.retrieval.search import HybridRetrieval

logger = setup_logger(__name__)

# Test queries with known-correct cases
EVAL_QUERIES = [
    {
        "query": "Milloin palvelusrikos on törkeä?",
        "expected_cases": ["KKO:2025:58"],
        "query_type": "conditions",
        "notes": "When is service offense aggravated",
    },
    {
        "query": "Millä edellytyksillä rikoslain 6 luvun 3 §:n 3 kohdan rangaistuksen lieventämisperustetta (oma-aloitteinen rikoksensa selvittämisen edistäminen) voidaan soveltaa?",
        "expected_cases": ["KKO:1998:162"],
        "query_type": "statute_interpretation",
        "notes": "RL 6 ch 3 §(3) mitigation; KKO:1998:162 is the leading case",
    },
]


async def evaluate_retrieval():
    """Measure retrieval quality metrics"""
    retrieval = HybridRetrieval()

    metrics = {
        "mrr": [],  # Mean Reciprocal Rank
        "recall_at_3": [],  # How often the right case is in top 3
        "recall_at_5": [],  # How often the right case is in top 5
        "recall_at_10": [],  # How often the right case is in top 10
    }

    for item in EVAL_QUERIES:
        logger.info("")
        logger.info("Query: %s", item["query"])
        logger.info("Expected: %s", item["expected_cases"])
        logger.info("Type: %s", item["query_type"])

        # Run retrieval
        results = await retrieval.hybrid_search_with_rerank(item["query"], final_limit=15)

        # Extract case IDs from results
        retrieved_cases = [(r.get("metadata") or {}).get("case_id", "") for r in results]

        # Calculate MRR (Mean Reciprocal Rank)
        found_at = None
        for i, case_id in enumerate(retrieved_cases):
            if case_id in item["expected_cases"]:
                found_at = i + 1
                break

        if found_at:
            mrr_score = 1 / found_at
            metrics["mrr"].append(mrr_score)
            logger.info("✓ Found at rank %s (MRR: %.3f)", found_at, mrr_score)
        else:
            metrics["mrr"].append(0)
            logger.info("✗ Not found in top 15")

        # Calculate Recall@K
        top3_cases = set(retrieved_cases[:3])
        top5_cases = set(retrieved_cases[:5])
        top10_cases = set(retrieved_cases[:10])
        expected = set(item["expected_cases"])

        metrics["recall_at_3"].append(1 if (top3_cases & expected) else 0)
        metrics["recall_at_5"].append(1 if (top5_cases & expected) else 0)
        metrics["recall_at_10"].append(1 if (top10_cases & expected) else 0)

        # Show top 5 results
        logger.info("")
        logger.info("Top 5 results:")
        for i, r in enumerate(results[:5], 1):
            meta = r.get("metadata", {})
            case_id = meta.get("case_id", "?")
            title = meta.get("title", "")
            score = r.get("blended_score", 0)
            marker = "✓✓✓" if case_id in item["expected_cases"] else ""
            logger.info("  %s. %s %s", i, case_id, marker)
            logger.info("     Score: %.4f | %s", score, (title or "")[:60])

    # Overall metrics
    n = len(metrics["mrr"]) or 1
    logger.info("")
    logger.info("OVERALL METRICS:")
    logger.info("Mean Reciprocal Rank: %.3f", sum(metrics["mrr"]) / n)
    logger.info("Recall@3:  %.1f%%", sum(metrics["recall_at_3"]) / n * 100)
    logger.info("Recall@5:  %.1f%%", sum(metrics["recall_at_5"]) / n * 100)
    logger.info("Recall@10: %.1f%%", sum(metrics["recall_at_10"]) / n * 100)

    return metrics


if __name__ == "__main__":
    asyncio.run(evaluate_retrieval())
