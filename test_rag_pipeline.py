"""
Test RAG Pipeline: Hybrid Search → Re-ranking → Response
Tests the complete retrieval flow end-to-end
"""

from src.services.retrieval import HybridRetrieval
from src.agent.agent import process_query

def test_hybrid_search():
    """Test hybrid search retrieval only"""
    print("TEST 1: HYBRID SEARCH (Vector + FTS + RRF)")
    
    retrieval = HybridRetrieval()
    query = "työterveyshuolto"
    
    print(f"\nQuery: {query}")
    print("\nRunning hybrid search...")
    
    results = retrieval.hybrid_search(query, limit=5)
    
    print(f"✓ Retrieved {len(results)} results\n")
    
    for i, result in enumerate(results, 1):
        print(f"[{i}] {result.get('section_number', 'N/A')}")
        print(f"    RRF: {result.get('rrf_score', 0):.4f} | "
              f"Vector: #{result.get('vector_rank', 'N/A')} | "
              f"FTS: #{result.get('fts_rank', 'N/A')}")
        text = result.get('chunk_text', '')[:100]
        print(f"    {text}...\n")


def test_reranking():
    """Test hybrid search + BGE reranking"""
    print("TEST 2: HYBRID SEARCH + BGE RERANKING")
    
    retrieval = HybridRetrieval()
    query = "työterveyshuolto"
    
    print(f"\nQuery: {query}")
    print("\nRunning hybrid search + reranking...")
    
    results = retrieval.hybrid_search_with_rerank(query, initial_limit=20, final_limit=5)
    
    print(f"✓ Retrieved {len(results)} reranked results\n")
    
    for i, result in enumerate(results, 1):
        print(f"[{i}] {result.get('section_number', 'N/A')}")
        print(f"    Rerank: {result.get('rerank_score', 0):.4f} | "
              f"RRF: {result.get('rrf_score', 0):.4f}")
        text = result.get('chunk_text', '')[:100]
        print(f"    {text}...\n")


def test_agent_pipeline():
    """Test full agent pipeline with retrieval"""
    print("TEST 2: AGENT PIPELINE (Analyze → Search → Reason → Respond)")
    
    query = "Mitä työterveyshuollosta sanotaan?"
    print(f"\nQuery: {query}\n")
    
    print("Processing through agent...")
    response = process_query(query)
    
    print("\nAgent Response:")
    print(response)


if __name__ == "__main__":
    # Run full pipeline test
    test_agent_pipeline()
    
    print("✅ Tests complete!")
