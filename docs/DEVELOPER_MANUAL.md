# LexAI Developer Manual

Technical guide for developing, deploying, and maintaining the AI Legal Reasoning System.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Environment Setup](#3-environment-setup)
4. [Configuration Reference](#4-configuration-reference)
5. [Database Schema](#5-database-schema)
6. [Ingestion Pipelines](#6-ingestion-pipelines)
7. [Search & Retrieval](#7-search--retrieval)
8. [UI Layer (Streamlit)](#8-ui-layer-streamlit)
9. [Cloud Drive Integration](#9-cloud-drive-integration)
10. [Multi-Tenant System](#10-multi-tenant-system)
11. [Testing](#11-testing)
12. [Code Quality](#12-code-quality)
13. [Deployment](#13-deployment)
14. [Maintenance & Operations](#14-maintenance--operations)

---

## 1. Architecture Overview

```
User Query (Finnish/English)
    |
Hybrid Search (Vector + FTS + RRF)
    |
Cohere Re-ranking
    |
GPT-4o-mini (LLM Reasoning)
    |
Response with Citations
```

### Tech Stack

| Component | Technology |
|-----------|-----------|
| UI | Streamlit |
| Workflow | LangGraph |
| LLM (answers) | GPT-4o-mini |
| LLM (extraction) | GPT-4o |
| Embeddings | OpenAI text-embedding-3-small (1536d) |
| Re-ranking | Cohere Rerank v4.0-fast |
| Vector DB | Supabase pgvector |
| FTS | PostgreSQL ts_rank (Finnish) |
| Scraping | Playwright |
| Drive Backup | Google Drive API (OAuth2) |

### Data Flow

1. **Ingestion**: Source (Finlex API / Court scraping / Client upload) -> Extract -> Chunk -> Embed -> Store in Supabase
2. **Query**: User query -> Embed -> Hybrid search (vector + FTS) -> RRF merge -> Cohere rerank -> Top-K to LLM -> Stream response

---

## 2. Project Structure

```
.
├── src/                          # Application code (importable)
│   ├── agent/                    # LangGraph agent (graph, nodes, state, stream)
│   ├── api/                      # FastAPI ingest API
│   ├── config/                   # Settings, logging, translations
│   ├── services/
│   │   ├── case_law/             # Scraper, extractor, regex, hybrid, storage
│   │   ├── common/               # Chunker, embedder, PDF extractor
│   │   ├── drive/                # Cloud drive connectors + settings service
│   │   ├── finlex/               # Finlex API client, XML parser, ingestion
│   │   ├── ingestion/            # Client document ingestion pipeline
│   │   └── retrieval/            # Search, reranker, LLM generator
│   ├── ui/                       # Streamlit chat app + ingestion UI
│   └── utils/                    # Shared helpers
├── scripts/
│   ├── case_law/
│   │   ├── core/                 # Shared ingestion manager, PDF/Drive export
│   │   ├── supreme_court/        # KKO: ingest precedents, rulings, leaves
│   │   └── supreme_administrative_court/  # KHO ingestion
│   ├── finlex_ingest/            # Bulk statute ingestion
│   └── migrations/               # SQL schema files
├── tests/                        # Unit and integration tests
├── docs/                         # Architecture docs, conventions
├── data/                         # Runtime cache (gitignored)
├── Makefile                      # All project commands
└── requirements.txt              # Python dependencies
```

### Key Conventions

- **Application code** lives in `src/` only. Scripts go in `scripts/`.
- **Logging**: All modules use `from src.config.logging_config import setup_logger`. No `print()` in library code. Use `%s` placeholders.
- **Config**: All settings via environment variables loaded in `src/config/settings.py`. Secrets in `.env` (never committed).
- See [CONVENTIONS.md](CONVENTIONS.md) for full details.

---

## 3. Environment Setup

### Prerequisites

- Python 3.11+
- Supabase project with pgvector extension
- API keys: OpenAI, Cohere (optional)

### Installation

```bash
# Clone and setup
git clone <repo-url>
cd AI-Legal-Reasoning-System

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt

# Or use setup script
./setup.sh
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Required
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
OPENAI_API_KEY=sk-...

# Required if RERANK_ENABLED=true (default)
COHERE_API_KEY=...

# Multi-tenant client ingestion (optional)
LEXAI_TENANT_ID=my-tenant

# Google Drive OAuth for client ingestion (optional)
GOOGLE_DRIVE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=GOCSPX-xxx

# Microsoft OneDrive OAuth for client ingestion (optional)
MICROSOFT_CLIENT_ID=xxx
MICROSOFT_CLIENT_SECRET=xxx

# Google Drive backup (separate from client ingestion)
GOOGLE_OAUTH_CLIENT_SECRET=client_secret_xxx.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=xxx
```

### Running the App

```bash
make run            # Streamlit UI at http://localhost:8501
make run-cli        # CLI chat
make run-api        # FastAPI ingest API at http://0.0.0.0:8000
make test           # Run pytest
make help           # All available commands
```

---

## 4. Configuration Reference

All config lives in `src/config/settings.py` as a `Config` class reading from env vars.

### Retrieval Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VECTOR_SEARCH_TOP_K` | 25 | Vector search candidates |
| `FTS_SEARCH_TOP_K` | 25 | Full-text search candidates |
| `SEARCH_CANDIDATES_FOR_RERANK` | 50 | Candidates sent to Cohere |
| `RERANK_MAX_DOCS` | 50 | Max docs to reranker |
| `CHUNKS_TO_LLM` | 12 | Final chunks sent to LLM |
| `MATCH_THRESHOLD` | 0.3 | Minimum vector similarity |
| `RERANK_ENABLED` | true | Enable Cohere reranking |
| `RELEVANCY_CHECK_ENABLED` | false | Score-based relevancy check |

### Query Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `MULTI_QUERY_ENABLED` | true | Generate alternative queries for better recall |
| `MULTI_QUERY_SKIP_WHEN_CASE_ID` | true | Skip multi-query when user provides a case ID |
| `REFORMULATE_ENABLED` | true | Rewrite query on zero results (up to 2 attempts) |
| `YEAR_CLARIFICATION_ENABLED` | true | Ask for year range if not specified |
| `MAX_QUERY_LENGTH` | 2000 | Reject queries exceeding this length |

### Model Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_CHAT_MODEL` | gpt-4o-mini | Model for answer generation |
| `EXTRACTION_MODEL` | gpt-4o | Model for ingestion extraction |
| `EMBEDDING_MODEL` | text-embedding-3-small | Embedding model |
| `EMBEDDING_DIMENSIONS` | 1536 | Embedding vector dimensions |
| `USE_AI_EXTRACTION` | true | Use LLM for extraction (false = regex only) |

### Ingestion Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `INGESTION_SKIP_UNCHANGED` | false | Skip docs with matching content_hash |
| `CHUNK_SIZE` | 1000 | Target chunk size (chars) |
| `CHUNK_MIN_SIZE` | 100 | Minimum chunk size |
| `CHUNK_OVERLAP` | 50 | Overlap between chunks |

---

## 5. Database Schema

### Core Tables

Run `scripts/migrations/case_law_tables.sql` first, then additional migrations in order.

**`case_law`** -- Document metadata and full text
- `id` (UUID PK), `case_id`, `court_type`, `decision_type`, `case_year`
- `title`, `full_text`, `judgment`, `background_summary`
- `legal_domains` (text[]), `decision_outcome`, `cited_laws` (text[]), `cited_cases` (text[])
- `tenant_id` (TEXT, nullable) -- multi-tenant isolation
- `content_hash` -- idempotency for re-ingestion

**`case_law_sections`** -- Chunked content with embeddings
- `id` (UUID PK), `case_law_id` (FK), `section_type`, `content`
- `embedding` (vector(1536)), `fts_vector` (tsvector)
- `tenant_id` (TEXT, nullable)

**`legal_chunks`** -- Finlex statute chunks
- Similar structure with `document_title`, `document_uri`, `chunk_text`, `embedding`, `fts_vector`
- `tenant_id` (TEXT, nullable)

### Multi-Tenant Tables

Run `scripts/migrations/add_multi_tenant.sql`:

**`client_documents`** -- Tracks ingested client files
- `tenant_id`, `source_provider` (upload/google_drive/onedrive)
- `file_name`, `file_type`, `status`, `content_hash`, `chunks_stored`
- `case_law_id` (FK) -- links to parent case_law record

**`tenant_drive_connections`** -- OAuth tokens and folder config
- `tenant_id` + `provider` (UNIQUE)
- `access_token`, `refresh_token`, `token_expiry`
- `folder_id` -- selected root folder for ingestion

### UI Tables

Run `scripts/migrations/ui_tables.sql`:

**`conversations`** -- Saved chat conversations
- `id`, `title`, `messages` (JSONB), `lang`, `tenant_id`

**`feedback`** -- User ratings on responses
- `message`, `query`, `rating` (up/down), `lang`, `tenant_id`

### RPC Functions (Supabase)

All search functions accept an optional `p_tenant_id` parameter for multi-tenant isolation:

- `vector_search_case_law(query_embedding, match_threshold, match_count, p_tenant_id)`
- `fts_search_case_law(query_text, match_count, p_tenant_id)`
- `prefix_fts_search_case_law(query_text, match_count, p_tenant_id)`
- `search_case_law_metadata(query_text, match_count, p_tenant_id)`
- `vector_search(query_embedding, match_threshold, match_count, p_tenant_id)` -- legal_chunks
- `fts_search(query_text, match_count, p_tenant_id)` -- legal_chunks

Tenant isolation logic: `WHERE (tenant_id IS NULL OR tenant_id = p_tenant_id)` -- shared (NULL) data is always included.

---

## 6. Ingestion Pipelines

### Case Law (No API -- Scraping)

```
Court website -> Playwright scraper -> Regex + LLM extraction -> Storage -> Supabase
```

Commands:
```bash
make ingest-precedents YEAR=2026          # KKO precedents, single year
make ingest-history START=2020 END=2026   # Batch range
make ingest-kko                           # All KKO subtypes
make ingest-kho                           # KHO
```

Code: `src/services/case_law/`, `scripts/case_law/`

### Finlex Statutes (API)

```
Finlex Open Data API -> XML parser (Akoma Ntoso) -> Section chunking -> Supabase
```

Command: `make ingest-finlex`

Code: `src/services/finlex/`, `scripts/finlex_ingest/`

### Client Document Ingestion

```
File (upload/drive) -> Hash check -> Text extraction -> Chunking -> Embedding -> Supabase
```

Code: `src/services/ingestion/client_ingestion.py`, `src/services/ingestion/client_storage.py`

Pipeline stages:
1. **Hashing** -- SHA-256 for duplicate detection
2. **Extracting** -- PDF/DOCX/TXT text extraction
3. **Chunking** -- Section-based splitting
4. **Embedding** -- OpenAI text-embedding-3-small
5. **Storing** -- Upsert to `case_law` + `case_law_sections` with `tenant_id`

### PDF/Drive Backup

```
JSON cache -> PDF generation -> Local export + Google Drive upload
```

Commands:
```bash
make export-pdf-drive YEAR=2026
make export-pdf-drive-range START=2020 END=2026
```

---

## 7. Search & Retrieval

See [RETRIEVAL_AND_RERANK.md](RETRIEVAL_AND_RERANK.md) for detailed architecture.

### Pipeline

1. **Query embedding** via OpenAI text-embedding-3-small
2. **Hybrid search**: Vector (pgvector cosine) + FTS (PostgreSQL Finnish tsvector) + metadata FTS
3. **RRF merge** (k=60) to combine rankings
4. **Cohere rerank** (v4.0-fast) scores top 50 candidates
5. **Top 12 chunks** sent to GPT-4o-mini with system prompt enforcing citations

### Multi-Query Expansion

When enabled (`MULTI_QUERY_ENABLED=true`), the system generates 2 alternative phrasings of the user's query via LLM, runs 3 parallel searches, and merges results before reranking.

### Reformulation

On zero results (`REFORMULATE_ENABLED=true`), the query is rewritten up to 2 times with broader terms.

---

## 8. UI Layer (Streamlit)

### File Map

| File | Purpose |
|------|---------|
| `src/ui/app.py` | Main entry point, layout, sidebar, OAuth callback |
| `src/ui/ingestion.py` | Document ingestion sidebar (upload, drive, folder browser) |
| `src/ui/citations.py` | Source block parsing, citation rendering, copy button |
| `src/ui/feedback.py` | Thumbs up/down feedback buttons |
| `src/ui/suggestions.py` | Related question generation (GPT-4o-mini) |
| `src/ui/conversation_store.py` | Conversation CRUD via Supabase |
| `src/ui/chat_pdf_export.py` | PDF export with ReportLab |

### Session State Keys

Key session state variables:

| Key | Type | Purpose |
|-----|------|---------|
| `lang` | str | Current UI language (en/fi/sv) |
| `dark_mode` | bool | Dark mode toggle |
| `tenant_id` | str | Current tenant ID |
| `messages` | list | Chat history |
| `current_conversation_id` | str | Active conversation UUID |
| `pending_template` | str | Template waiting for edit/send |
| `gdrive_access_token` | str | Google Drive OAuth token |
| `onedrive_access_token` | str | OneDrive OAuth token |
| `gdrive_folder_id` | str | Selected Google Drive folder |
| `onedrive_folder_id` | str | Selected OneDrive folder |
| `{provider}_breadcrumb` | list | Folder navigation path |
| `{provider}_files` | list | Cached file list |
| `{provider}_folders` | list | Cached subfolder list |
| `filters_enabled` | bool | Search filters active |
| `filter_year_range` | tuple | Year range filter values |
| `filter_court_types` | list | Selected court types |
| `filter_legal_domains` | list | Selected legal domains |

### OAuth Callback Flow

1. User clicks "Connect Google Drive" / "Connect OneDrive"
2. `get_auth_url(redirect_uri)` generates OAuth URL with `state=provider_name`
3. User authorizes on provider's site
4. Provider redirects back with `?code=xxx&state=google_drive`
5. `_handle_oauth_callback()` in `app.py` detects `code` in `st.query_params`
6. Calls `connector.exchange_code(code, redirect_uri)` for tokens
7. Saves tokens via `DriveSettingsService.save_connection()`
8. Stores token in `st.session_state` for immediate use
9. Clears query params and shows success toast

---

## 9. Cloud Drive Integration

### Components

| File | Purpose |
|------|---------|
| `src/services/drive/base.py` | Abstract `BaseDriveConnector` interface |
| `src/services/drive/google_connector.py` | Google Drive OAuth2 + API connector |
| `src/services/drive/onedrive_connector.py` | OneDrive MSAL + Graph API connector |
| `src/services/drive/drive_settings.py` | Supabase CRUD for `tenant_drive_connections` |

### BaseDriveConnector Interface

```python
class BaseDriveConnector(ABC):
    def get_auth_url(self, redirect_uri: str) -> str
    def exchange_code(self, code: str, redirect_uri: str) -> dict
    def list_files(self, access_token: str, folder_id: str | None = None) -> list[dict]
    def download_file(self, access_token: str, file_id: str) -> bytes
    def list_folders(self, access_token: str, parent_id: str | None = None) -> list[dict]
```

### DriveSettingsService API

```python
service = DriveSettingsService()

# Save/update connection (upsert by tenant_id + provider)
service.save_connection(tenant_id, provider, access_token, refresh_token, token_expiry, folder_id)

# Load saved connection
conn = service.get_connection(tenant_id, provider)  # -> dict or None

# Update just the folder
service.update_folder(tenant_id, provider, folder_id)

# Disconnect
service.delete_connection(tenant_id, provider)
```

### Setting Up Google Drive OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable the **Google Drive API**
4. Create **OAuth 2.0 Client ID** (Web application type)
5. Add `http://localhost:8501` (and your production URL) as authorized redirect URIs
6. Copy Client ID and Client Secret to `.env`:
   ```
   GOOGLE_DRIVE_CLIENT_ID=xxx.apps.googleusercontent.com
   GOOGLE_DRIVE_CLIENT_SECRET=GOCSPX-xxx
   ```

### Setting Up OneDrive OAuth

1. Go to [Azure Portal > App registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps)
2. Register a new application
3. Under **Authentication**, add `http://localhost:8501` as a redirect URI (Web platform)
4. Under **Certificates & secrets**, create a new client secret
5. Under **API permissions**, add `Files.Read.All` (delegated)
6. Copy values to `.env`:
   ```
   MICROSOFT_CLIENT_ID=xxx
   MICROSOFT_CLIENT_SECRET=xxx
   ```

### Connection Persistence Flow

```
Page load
  -> _restore_saved_connections()
    -> DriveSettingsService.get_connection(tenant_id, provider)
    -> If found: restore access_token + folder_id to session_state

OAuth callback
  -> exchange_code() for tokens
  -> DriveSettingsService.save_connection()
  -> Store in session_state

Folder selection
  -> DriveSettingsService.update_folder()
  -> Update session_state

Disconnect
  -> DriveSettingsService.delete_connection()
  -> Clear session_state
```

---

## 10. Multi-Tenant System

### How It Works

- Each tenant is identified by `LEXAI_TENANT_ID` (set in `.env`)
- Client-uploaded documents are tagged with `tenant_id` in `case_law` and `case_law_sections`
- Search RPC functions filter by tenant: shared (NULL) data is always included, tenant-specific data is isolated
- Drive connections are per-tenant (`tenant_drive_connections` has UNIQUE on `tenant_id, provider`)

### Tenant Isolation

All Supabase RPC functions use:
```sql
WHERE (tenant_id IS NULL OR tenant_id = p_tenant_id)
```

This means:
- Public case law (tenant_id IS NULL) is visible to all tenants
- Tenant documents are only visible to that specific tenant
- Queries without a tenant_id see only public data

---

## 11. Testing

```bash
make test           # Run all tests
pytest tests/unit/  # Unit tests only
pytest -k "test_search"  # Run specific tests
```

Tests are in `tests/`, mirroring `src/` structure. Use pytest.

---

## 12. Code Quality

### Linting

```bash
make lint           # Check with Ruff (18 rule categories)
make lint-fix       # Auto-fix
make format         # Format with Ruff (Black-compatible)
```

### Pre-commit Hooks

Ruff linter + formatter run automatically on every commit via `.pre-commit-config.yaml`.

### Complexity Limits

Enforced via `pyproject.toml`:
- Max cyclomatic complexity: 15
- Max statements per function: 60
- Max branches per function: 15

---

## 13. Deployment

### Streamlit Cloud

1. Push to GitHub
2. Deploy on Streamlit Cloud
3. Set environment variables in Streamlit Cloud dashboard
4. Update OAuth redirect URIs to your production URL

### Docker (Manual)

```bash
# Build and run
docker build -t lexai .
docker run -p 8501:8501 --env-file .env lexai
```

### Important Notes

- Never commit `.env` -- use `.env.example` as template
- Run all migrations in Supabase SQL Editor before first use
- Set `PYTHONPATH` to project root if imports fail
- OAuth redirect URIs must match exactly (including trailing slashes)

---

## 14. Maintenance & Operations

### Ingestion Status Check

```bash
make check-ingestion-status
```

Or use the SQL queries in `docs/SUPABASE_QUERIES.sql`, section 9 (health checks).

### Re-processing Documents

```bash
# Re-ingest a single year
make ingest-precedents YEAR=2025

# Force re-process (reset content hashes first via SQL)
UPDATE case_law SET content_hash = NULL WHERE case_year = 2025;
```

### Metadata Backfill

SQL queries for backfilling metadata fields (judgment, background_summary, legal_domains, decision_outcome, etc.) are documented in `docs/SUPABASE_QUERIES.sql`, sections 8-10.

### Common Issues

| Issue | Solution |
|-------|----------|
| "Missing required env vars" on startup | Check `.env` has SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY |
| "COHERE_API_KEY is missing" | Set COHERE_API_KEY or set RERANK_ENABLED=false |
| OAuth redirect fails | Ensure redirect URI in provider console matches exactly |
| Drive token expired | User clicks Disconnect then reconnects |
| Import errors | Run `export PYTHONPATH=$(pwd)` from project root |
| Supabase timeout on large queries | Increase `statement_timeout` (see SUPABASE_QUERIES.sql section 1) |

### Make Commands Reference

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make run` | Streamlit UI (localhost:8501) |
| `make run-cli` | CLI chat |
| `make run-api` | FastAPI ingest API (0.0.0.0:8000) |
| `make test` | Run pytest |
| `make lint` / `make lint-fix` / `make format` | Code quality |
| `make ingest-precedents YEAR=N` | Ingest KKO precedents |
| `make ingest-history START=N END=N` | Batch ingest year range |
| `make ingest-kko` | All KKO subtypes |
| `make ingest-kho` | KHO ingestion |
| `make ingest-finlex` | Finlex statutes |
| `make export-pdf-drive YEAR=N` | PDF backup to Google Drive |
| `make check-ingestion-status` | Check ingestion health |
