"""
Test RAG Pipeline: Hybrid Search → Re-ranking → Response
Tests the complete retrieval flow end-to-end
"""

from src.services.retrieval import HybridRetrieval
from src.agent.agent import process_query

def test_hybrid_search():
    """Test hybrid search retrieval only"""
    print("\n" + "="*70)
    print("TEST 1: HYBRID SEARCH (Vector + FTS + RRF)")
    print("="*70)
    
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


def test_agent_pipeline():
    """Test full agent pipeline with retrieval"""
    print("\n" + "="*70)
    print("TEST 2: AGENT PIPELINE (Analyze → Search → Reason → Respond)")
    print("="*70)
    
    query = "Mitä työterveyshuollosta sanotaan?"
    print(f"\nQuery: {query}\n")
    
    print("Processing through agent...")
    response = process_query(query)
    
    print("\nAgent Response:")
    print("-"*70)
    print(response)
    print("-"*70)


if __name__ == "__main__":
    # Run tests
    test_hybrid_search()
    # test_agent_pipeline()  # Uncomment when ready to test full pipeline
    
    print("\n" + "="*70)
    print("✅ Tests complete!")
    print("="*70)
