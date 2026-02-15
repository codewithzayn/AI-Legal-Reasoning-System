"""
© 2026 Crest Advisory Group LLC. All rights reserved.

PROPRIETARY AND CONFIDENTIAL

This file is part of the Crest Pet System and contains proprietary
and confidential information of Crest Advisory Group LLC.
Unauthorized copying, distribution, or use is strictly prohibited.
"""

"""Retrieval quality evaluation - measures Recall@K.

Run: python tests/test_retrieval_quality.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("LOG_FORMAT", "simple")

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.config.logging_config import setup_logger
from src.services.retrieval.search import HybridRetrieval

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# 25 test questions — diverse scenarios, 2-3 per topic area.
# Each expected_cases must appear in top-15 reranked results.
# ---------------------------------------------------------------------------
EVAL_QUERIES = [
    # --- 1. Compound word (prefix-matching fix) ---
    {
        "query": "Onko vahingonkorvauslain 7 luvun 4 §:n oikeuspaikkasäännös pakottava vai tahdonvaltainen?",
        "expected_cases": ["KKO:1987:135"],
        "query_type": "compound_word",
    },
    # --- 2-3. Employment law ---
    {
        "query": "Milloin työsopimus katsotaan purkautuneeksi TSL 8 luvun 3 §:n nojalla?",
        "expected_cases": ["KKO:2026:8"],
        "query_type": "employment",
    },
    {
        "query": "Mitä TSL 8 luvun 3 § säätää työsopimuksen purkautuneena pitämisestä?",
        "expected_cases": ["KKO:2026:8"],
        "query_type": "statute_ref",
    },
    # --- 4-5. Criminal law ---
    {
        "query": "Milloin palvelusrikos on törkeä sotilasrikoksena?",
        "expected_cases": ["KKO:2026:5"],
        "query_type": "conditions",
    },
    {
        "query": "Miten raiskausrikoksen tunnusmerkistö on muuttunut rikoslain uudistuksessa?",
        "expected_cases": ["KKO:2026:3", "KKO:2025:61"],
        "query_type": "criminal",
    },
    # --- 6-7. Sentencing ---
    {
        "query": "Miten vapaudenmenetysaika vähennetään rangaistuksesta KKO:n oikeuskäytännön mukaan?",
        "expected_cases": ["KKO:2026:7"],
        "query_type": "sentencing",
    },
    {
        "query": "Otetaanko Ruotsissa annettu vankeustuomio huomioon yhteistä rangaistusta määrättäessä Suomessa RL 7 luvun mukaan?",
        "expected_cases": ["KKO:2025:5"],
        "query_type": "sentencing",
    },
    # --- 8-10. Tort / Damages ---
    {
        "query": "Mitä VahL 5 luvun 5 § säätää korvattavasta vahingosta?",
        "expected_cases": ["KKO:2026:2"],
        "query_type": "statute_ref",
    },
    {
        "query": "Milloin syyttömästi pidätetylle maksetaan korvausta kärsimyksestä?",
        "expected_cases": ["KKO:2026:6"],
        "query_type": "damages",
    },
    {
        "query": "Miten turvaamistoimenpiteestä aiheutunut vahinko korvataan ja mikä on kanneaika?",
        "expected_cases": ["KKO:2025:88"],
        "query_type": "damages",
    },
    # --- 11-12. Corporate law ---
    {
        "query": "Mikä on osakeyhtiön toimitusjohtajan vastuu ja asema OYL 6 luvun 26 ja 28 §:n mukaan?",
        "expected_cases": ["KKO:2026:9"],
        "query_type": "corporate",
    },
    {
        "query": "Milloin asunto-osakeyhtiön yhtiökokouksen päätös voidaan moittia AsOYL 1 luvun 10 §:n yhdenvertaisuusperiaatteen nojalla?",
        "expected_cases": ["KKO:2025:89"],
        "query_type": "corporate",
    },
    # --- 13-14. Procedural law ---
    {
        "query": "Voidaanko työtuomioistuimen tuomiota moittia kantelulla OK 31 luvun nojalla väittämistaakan laiminlyönnin perusteella?",
        "expected_cases": ["KKO:2026:11"],
        "query_type": "procedural",
    },
    {
        "query": "Miten asiakirjan esittämisvelvollisuus toteutetaan oikeudenkäynnissä OK 17 luvun mukaan?",
        "expected_cases": ["KKO:2025:96", "KKO:2025:62"],
        "query_type": "procedural",
    },
    # --- 15-16. Property / Real estate ---
    {
        "query": "Miten lunastuskorvaus ja kohteenkorvaus määritetään lunastuslain 30 §:n mukaan?",
        "expected_cases": ["KKO:2025:19"],
        "query_type": "property",
    },
    {
        "query": "Mitä maakaari säätää lainhuudatuksesta ja kirjaamismenettelystä?",
        "expected_cases": ["KKO:2025:40"],
        "query_type": "property",
    },
    # --- 17. Coercive measures ---
    {
        "query": "Millä edellytyksillä vakuustakavarikko voidaan määrätä PakkokeinoL 6 luvun mukaan?",
        "expected_cases": ["KKO:2025:15"],
        "query_type": "coercive",
    },
    # --- 18-19. Insurance ---
    {
        "query": "Onko työtapaturman jälkeinen masennus korvattava tapaturmavakuutuksesta syy-yhteyden perusteella?",
        "expected_cases": ["KKO:2026:4"],
        "query_type": "insurance",
    },
    {
        "query": "Korvaako liikennevakuutus ansionmenetyksen loukkaantumisen jälkeen?",
        "expected_cases": ["KKO:2025:59"],
        "query_type": "insurance",
    },
    # --- 20-21. Case ID lookups ---
    {
        "query": "Kerro tapauksesta KKO:2026:1",
        "expected_cases": ["KKO:2026:1"],
        "query_type": "case_lookup",
    },
    {
        "query": "Mitä KKO:2025:35 koskee?",
        "expected_cases": ["KKO:2025:35"],
        "query_type": "case_lookup",
    },
    # --- 22. Insolvency ---
    {
        "query": "Mitä yrityssaneerauslain YSL 27 § säätää saneerausvelasta?",
        "expected_cases": ["KKO:2025:77"],
        "query_type": "insolvency",
    },
    # --- 23. Construction ---
    {
        "query": "Miten rakennusurakan YSE-sopimusehtoja sovelletaan?",
        "expected_cases": ["KKO:2025:3"],
        "query_type": "construction",
    },
    # --- 24. Criminal - specific ---
    {
        "query": "Onko yhtiön varojen siirtäminen toiseen yhtiöön osakkaana toimineen henkilön toimesta törkeä kavallus?",
        "expected_cases": ["KKO:2025:16"],
        "query_type": "criminal",
    },
    # --- 25. Sanctions / Regulation ---
    {
        "query": "Mitä säännöstelyrikos ja pakoteasiaan liittyvä laillisuusperiaate tarkoittavat?",
        "expected_cases": ["KKO:2026:1"],
        "query_type": "sanctions",
    },
]


async def evaluate_retrieval():
    """Run all test queries and report pass/fail."""
    retrieval = HybridRetrieval()
    total = len(EVAL_QUERIES)
    passed_at_5 = 0
    passed_at_10 = 0
    passed_at_15 = 0
    failures: list[dict] = []

    print(f"\n{'=' * 70}")
    print(f"RETRIEVAL QUALITY TEST — {total} queries")
    print(f"{'=' * 70}\n")

    for idx, item in enumerate(EVAL_QUERIES, 1):
        query = item["query"]
        expected = item["expected_cases"]
        qtype = item["query_type"]

        t0 = time.time()
        try:
            results = await retrieval.hybrid_search_with_rerank(query, initial_limit=30, final_limit=15)
        except Exception as exc:
            print(f"[{idx:2d}/{total}] ERROR  {qtype:18s} | {query[:50]}...")
            print(f"         Exception: {exc}")
            failures.append({"idx": idx, "query": query, "reason": str(exc)})
            continue

        elapsed = time.time() - t0
        retrieved = [(r.get("metadata") or {}).get("case_id", "") for r in results]

        found_rank = None
        for i, cid in enumerate(retrieved):
            if cid in expected:
                found_rank = i + 1
                break

        in_top5 = found_rank is not None and found_rank <= 5
        in_top10 = found_rank is not None and found_rank <= 10
        in_top15 = found_rank is not None and found_rank <= 15

        if in_top5:
            passed_at_5 += 1
        if in_top10:
            passed_at_10 += 1
        if in_top15:
            passed_at_15 += 1

        status = "PASS" if in_top15 else "FAIL"
        rank_str = f"rank #{found_rank}" if found_rank else "NOT FOUND"

        print(f"[{idx:2d}/{total}] {status:4s}  {qtype:18s} | {rank_str:14s} | {elapsed:4.1f}s | {query[:55]}")

        if not in_top15:
            failures.append(
                {
                    "idx": idx,
                    "query": query,
                    "expected": expected,
                    "got_top5": retrieved[:5],
                    "reason": rank_str,
                }
            )

    # Summary
    r5 = passed_at_5 / total * 100
    r10 = passed_at_10 / total * 100
    r15 = passed_at_15 / total * 100
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed_at_15}/{total} passed (Recall@15)")
    print(f"  Recall@5:  {passed_at_5}/{total} ({r5:.0f}%)")
    print(f"  Recall@10: {passed_at_10}/{total} ({r10:.0f}%)")
    print(f"  Recall@15: {passed_at_15}/{total} ({r15:.0f}%)")
    print(f"{'=' * 70}")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  [{f['idx']}] {f['query'][:70]}")
            if "expected" in f:
                print(f"       Expected: {f['expected']}")
                print(f"       Got top5: {f.get('got_top5', [])}")

    overall = "PASS" if r15 >= 0.60 else "FAIL"
    print(f"\nOVERALL: {overall} (threshold: 60% Recall@15)")
    return {"recall_at_5": r5, "recall_at_10": r10, "recall_at_15": r15, "failures": failures}


if __name__ == "__main__":
    asyncio.run(evaluate_retrieval())
