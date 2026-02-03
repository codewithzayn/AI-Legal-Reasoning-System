# AI Legal Reasoning System

Finnish legal document analysis and reasoning platform using RAG (Retrieval-Augmented Generation).

## Architecture

```
User Query (Finnish)
    ↓
Hybrid Search (Vector + FTS + RRF)
    ↓
Cohere Re-ranking
    ↓
GPT-4o-mini (LLM Reasoning)
    ↓
Finnish Response with Citations
```

## Features

✅ **Full RAG Pipeline**
- Hybrid search (semantic + keyword)
- Cohere Rerank v4.0-fast for re-ranking
- GPT-4o-mini for cost-effective response generation
- Mandatory source citations
- Finnish language support

✅ **Refined Service Architecture**
- Modular services: `finlex/`, `case_law/`, `common/`, `retrieval/`
- AI-Enhanced Extraction: `src/services/case_law/extractor.py` (Structured Metadata & Citations)
- Incremental Ingestion Tracking

✅ **Document Processing**
- Finlex API integration (Statutes)
- Supreme Court Scraping + AI Extraction (Precedents)
- XML parsing (Akoma Ntoso format)
- Section-based chunking & embedding

✅ **Search & Retrieval**
- Vector search (pgvector)
- Full-text search (ts_rank)
- RRF ranking algorithm
- Anti-hallucination system

✅ **User Interface**
- Streamlit chat interface
- Real-time responses
- Citation display

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env`:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_key
COHERE_API_KEY=your_cohere_key  # For re-ranking
```

### 3. Setup Database

Run `scripts/migrations/case_law_tables.sql` in Supabase SQL Editor.

### 4. Ingest Documents

**Finlex Statutes (Bulk):**
```bash
python3 scripts/finlex_ingest/bulk_ingest.py
```

**Supreme Court Precedents (KKO):**
```bash
python3 scripts/case_law/supreme_court/ingest_precedents.py --year 2026
```

### 5. Run Application

```bash
streamlit run src/ui/app.py
```

Open http://localhost:8501

## Tech Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| **API** | Finlex Open Data API | ✅ Active |
| **Scraping** | Playwright (Case Law) | ✅ Active |
| **Extraction** | LangChain + GPT-4o-mini | ✅ Active |
| **Parsing** | XML (Akoma Ntoso) | ✅ Active |
| **Chunking** | Section-based | ✅ Active |
| **Embeddings** | OpenAI text-embedding-3-small | ✅ Active |
| **Vector DB** | Supabase pgvector | ✅ Active |
| **FTS** | PostgreSQL ts_rank (Finnish) | ✅ Active |
| **Ranking** | RRF (k=60) | ✅ Active |
| **Re-ranking** | Cohere Rerank v4.0-fast | ✅ Active |
| **LLM** | GPT-4o-mini | ✅ Active |
| **Workflow** | LangGraph | ✅ Active |
| **UI** | Streamlit | ⏳ Pending |

## Workflow

### Ingestion (Dual Pipeline)
1. **Statutes**: Finlex API → XML Parser → Chunker → Embedder → Supabase
2. **Case Law**: Scraper (Playwright) → AI Extractor (GPT-4o-mini) → Storage → Supabase

### Retrieval
```
Query → Embedding → Vector (50) + FTS (50) → RRF → Top 20
```

### Response
```
Top 20 → Cohere Rerank → Top 10 → GPT-4o-mini → Finnish Response + Citations
```

## System Prompt

The LLM is configured with strict rules:
- **Only** use provided context
- **Always** cite sources with [§X]
- **Never** hallucinate or use external knowledge
- **Always** respond in Finnish
- Include document URIs in citations

## Testing

```bash
# Test full pipeline
python3 test_rag_pipeline.py

# Test specific document
python3 test_finlex.py
```

## API Usage

```python
from src.agent.agent import process_query

response = process_query("Mitä työterveyshuollosta sanotaan?")
print(response)
```

## Performance

- **Ingestion:** ~1-2 docs/sec
- **Search:** ~500ms (hybrid + rerank)
- **LLM:** ~2-3s (GPT-4o-mini)
- **Total:** ~3-4s per query

## Notes

- **API-based:** Cohere Rerank via API (fast, $1/1000 queries)
- **Finnish:** Full Finnish language support
- **Citations:** Mandatory source citations prevent hallucinations
- **Idempotent:** Re-ingestion updates existing chunks
- **Tracking:** Real-time ingestion progress in `case_law_ingestion_tracking` table

## License

MIT
