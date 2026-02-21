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

**Full RAG Pipeline**
- Hybrid search (semantic + keyword)
- Cohere Rerank v4.0-fast for re-ranking
- GPT-4o-mini for cost-effective response generation
- Mandatory source citations
- Finnish language support

**Refined Service Architecture**
- Modular services: `finlex/`, `case_law/`, `common/`, `retrieval/`, `drive/`
- AI-Enhanced Extraction: hybrid regex + LLM fallback (`hybrid_extractor.py`)
- Incremental Ingestion Tracking
- Google Drive PDF backup pipeline (OAuth2 user auth)

**Document Processing**
- **Finlex (API):** Documented Open Data API -- statutes, XML (Akoma Ntoso), section-based chunking.
- **Case law (no API):** Court websites -- scraping (Playwright) + regex/LLM extraction for precedents.
- **PDF/Drive backup:** Convert case law to PDF and upload to Google Drive for archival.

**Search & Retrieval**
- Vector search (pgvector) + full-text search (ts_rank) + RRF merge
- **Cohere reranking** -- scores candidates by relevance; we send the top `CHUNKS_TO_LLM` (default 10) to the LLM. See [docs/RETRIEVAL_AND_RERANK.md](docs/RETRIEVAL_AND_RERANK.md).
- Anti-hallucination (citations required)

**Code Quality**
- Ruff linting (18 rule categories) and formatting enforced via pre-commit hooks
- Complexity limits: max 15 cyclomatic complexity, max 60 statements, max 15 branches per function
- All code formatted with Black-compatible Ruff formatter

**User Interface**
- Streamlit chat interface
- Real-time responses
- Citation display

## Quick Start

### 1. Virtual environment (recommended)

```bash
./setup.sh
# or manually:
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS; on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`.venv/` is in `.gitignore` -- do not commit it.

### 2. Configure Environment

Create `.env` (never commit it; copy from `.env.example`):

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_key
COHERE_API_KEY=your_cohere_key

# Google Drive backup (optional)
GOOGLE_OAUTH_CLIENT_SECRET=client_secret_xxx.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=your_folder_id
```

### 3. Setup Database

Run `scripts/migrations/case_law_tables.sql` in Supabase SQL Editor.

### 4. Ingest Documents

```bash
# Supreme Court Precedents (KKO)
make ingest-precedents YEAR=2026

# Finlex Statutes (Bulk)
make ingest-finlex

# Historical batch (all years)
make ingest-history START=2020 END=2026

# PDF backup to Google Drive (after ingestion)
make export-pdf-drive YEAR=2026
```

### 5. Run Application

```bash
make run
```

Open http://localhost:8501

### 6. Run tests

```bash
make test
```

### 7. All commands

```bash
make help
```

See `docs/` for more documentation.

## Project Structure

```
.
├── src/                          # Application code
│   ├── agent/                    # LangGraph agent (graph, nodes, state, stream)
│   ├── api/                      # FastAPI ingest API
│   ├── config/                   # Settings, logging
│   ├── services/
│   │   ├── case_law/             # Scraper, extractor, regex, hybrid, storage, PDF export
│   │   ├── common/               # Chunker, embedder, PDF extractor
│   │   ├── drive/                # Google Drive uploader (OAuth2 / service account)
│   │   ├── finlex/               # Finlex API client, XML parser, ingestion, storage
│   │   └── retrieval/            # Search, reranker, LLM generator
│   ├── ui/                       # Streamlit chat app
│   └── utils/                    # Shared helpers
├── scripts/
│   ├── case_law/
│   │   ├── core/                 # Shared: ingestion manager, PDF/Drive export, history runner
│   │   ├── supreme_court/        # KKO: ingest precedents, rulings, leaves
│   │   └── supreme_administrative_court/  # KHO ingestion
│   ├── finlex_ingest/            # Bulk statute ingestion
│   └── migrations/               # SQL schema files
├── tests/                        # Unit and integration tests
├── docs/                         # Architecture docs, conventions
├── data/                         # Runtime cache (gitignored)
├── Makefile                      # All project commands
├── pyproject.toml                # Ruff linting/formatting config
├── .pre-commit-config.yaml       # Pre-commit hooks (ruff check + format)
└── requirements.txt              # Python dependencies
```

## Tech Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| **API** | Finlex Open Data API | Active |
| **Scraping** | Playwright (Case Law) | Active |
| **Extraction** | Regex + LLM fallback (GPT-4o-mini) | Active |
| **Parsing** | XML (Akoma Ntoso) | Active |
| **Chunking** | Section-based | Active |
| **Embeddings** | OpenAI text-embedding-3-small | Active |
| **Vector DB** | Supabase pgvector | Active |
| **FTS** | PostgreSQL ts_rank (Finnish) | Active |
| **Ranking** | RRF (k=60) | Active |
| **Re-ranking** | Cohere Rerank v4.0-fast | Active |
| **LLM** | GPT-4o-mini | Active |
| **Workflow** | LangGraph | Active |
| **Drive Backup** | Google Drive API (OAuth2) | Active |
| **Linting** | Ruff + pre-commit hooks | Active |
| **UI** | Streamlit | Active |

## Workflow

### Ingestion (Dual Pipeline)
1. **Statutes**: Finlex API -> XML Parser -> Chunker -> Embedder -> Supabase
2. **Case Law**: Scraper (Playwright) -> Hybrid Extraction (regex + LLM fallback) -> Storage -> Supabase

### PDF/Drive Backup (Separate Pipeline)
```
JSON cache -> PDF generation -> Local export + Google Drive upload
```

### Retrieval
```
Query -> Embedding -> Vector (50) + FTS (50) -> RRF -> Top 20
```

### Response
```
Top 20 -> Cohere Rerank -> Top 10 -> GPT-4o-mini -> Finnish Response + Citations
```

## System Prompt

The LLM is configured with strict rules:
- **Only** use provided context
- **Always** cite sources with [source_number]
- **Never** hallucinate or use external knowledge
- **Always** respond in Finnish
- Include document URIs in citations

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
- **Pre-commit:** Ruff linter + formatter run automatically before every commit

## License

MIT
