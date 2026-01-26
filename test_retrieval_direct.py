import asyncio
import os
from src.services.retrieval import HybridRetrieval
from src.config.logging_config import setup_logger

logger = setup_logger("test")

async def test():
    print("Initializing HybridRetrieval...")
    try:
        retrieval = HybridRetrieval()
        query = "Mitä KKO 2026:5 koskee?"
        print(f"Searching for: {query}")
        
        results = await retrieval.hybrid_search_with_rerank(
            query, 
            initial_limit=20, 
            final_limit=5
        )
        
        print(f"\nFound {len(results)} results:")
        for i, res in enumerate(results):
            source = res.get('source', 'unknown')
            score = res.get('score', 0)
            text = res.get('text', '')[:100].replace('\n', ' ')
            metadata = res.get('metadata', {})
            title = "Unknown"
            if source == 'case_law':
                title = f"{metadata.get('court')} {metadata.get('case_id')}"
            else:
                title = metadata.get('title') or res.get('document_title')
                
            print(f"{i+1}. [{source.upper()}] {title} (CombinedScore: {score:.4f})")
            print(f"    Text: {text}...")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
