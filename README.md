# AI Legal Reasoning System

Finnish legal document analysis and reasoning platform using RAG (Retrieval-Augmented Generation).

## Architecture

```
User Query
    ↓
Hybrid Search (Vector + FTS + RRF)
    ↓
Re-ranking (Cohere Rerank v3)
    ↓
LLM Reasoning (GPT-4o)
    ↓
Response with Citations
```

## Project Structure

```
AI Legal Reasoing system/
├── src/
│   ├── agent/                  # LangGraph agent
│   │   ├── agent.py           # Main agent interface
│   │   ├── graph.py           # Workflow definition
│   │   ├── nodes.py           # Processing nodes
│   │   └── state.py           # Agent state
│   ├── services/              # Core services
│   │   ├── finlex_api.py      # Finlex API client
│   │   ├── xml_parser.py      # XML document parser
│   │   ├── chunker.py         # Document chunking
│   │   ├── embedder.py        # OpenAI embeddings
│   │   ├── retrieval.py       # Hybrid search (Vector + FTS + RRF)
│   │   └── supabase.py        # Supabase storage
│   └── ui/
│       └── app.py             # Streamlit interface
├── scripts/
│   ├── setup_supabase.sql     # Database schema
│   └── ingest_documents.py    # Document ingestion
├── test_rag_pipeline.py       # RAG testing
└── requirements.txt           # Dependencies
```

## Setup

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_key
COHERE_API_KEY=your_cohere_key  # For re-ranking
```

### 3. Setup Database

Run `scripts/setup_supabase.sql` in Supabase SQL Editor.

### 4. Ingest Documents

```bash
python3 scripts/ingest_documents.py
```

### 5. Test RAG Pipeline

```bash
python3 test_rag_pipeline.py
```

## Current Status

✅ **Ingestion Pipeline**
- Finlex API integration
- XML parsing (Finnish legal documents)
- Section-based chunking
- OpenAI embeddings (1536-dim)
- Supabase storage with idempotency

✅ **Hybrid Search**
- Vector search (pgvector cosine similarity)
- Full-text search (PostgreSQL ts_rank)
- RRF ranking (Reciprocal Rank Fusion)

⏳ **Re-ranking** (Next)
- Cohere Rerank v3.0 integration

⏳ **LLM Reasoning** (Pending)
- GPT-4o for legal analysis
- Citation generation

⏳ **UI** (Pending)
- Streamlit chat interface

## Tech Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| **API** | Finlex Open Data API | ✅ Active |
| **Parsing** | XML (Akoma Ntoso) | ✅ Active |
| **Chunking** | Section-based | ✅ Active |
| **Embeddings** | OpenAI text-embedding-3-small | ✅ Active |
| **Vector DB** | Supabase pgvector | ✅ Active |
| **FTS** | PostgreSQL ts_rank (Finnish) | ✅ Active |
| **Ranking** | RRF (k=60) | ✅ Active |
| **Re-ranking** | Cohere Rerank v3.0 | ⏳ Pending |
| **LLM** | GPT-4o | ⏳ Pending |
| **Workflow** | LangGraph | ✅ Active |
| **UI** | Streamlit | ⏳ Pending |

## Workflow

### Ingestion
```
Finlex API → XML Parser → Chunker → Embedder → Supabase
```

### Retrieval
```
Query → Embedding → Vector Search (50) + FTS (50) → RRF → Top 20
```

### Response (Coming Soon)
```
Top 20 → Cohere Rerank → Top 10 → GPT-4o → Response + Citations
```

## Testing

```bash
# Test hybrid search
python3 test_rag_pipeline.py

# Test specific document
python3 test_finlex.py
```

## MVP Scope

- **Year Range:** 2024-2025
- **Document Types:** Acts (statutes)
- **Language:** Finnish
- **Search:** Hybrid (semantic + keyword)
- **Re-ranking:** Cohere multilingual
- **LLM:** GPT-4o
