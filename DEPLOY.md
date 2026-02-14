# Deployment: Streamlit Cloud (*.streamlit.app)

**Note:** Streamlit does not run on Vercel. Use **Streamlit Community Cloud** for `*.streamlit.app` URLs.

## Streamlit Community Cloud (Recommended)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in → New app → Select repo, branch, main file: `app.py`
4. Add env vars (see **Environment variables for deployment** below)
5. Deploy

## Railway / Render (Procfile)

Uses `Procfile`: `web: sh -c 'streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0'`

- `PORT` is set by the platform (Railway, Render, Heroku); defaults to 8501 if unset.

## Replit

- Entrypoint: `streamlit run src/ui/app.py` (see `.replit`).
- Set **Secrets** (Replit → Tools → Secrets) from the list below. Same keys as Streamlit Cloud.

## Concurrency

- Session state is per-user (Streamlit isolates)
- Supabase client uses async lock for concurrent requests
- CORS and XSRF enabled in `.streamlit/config.toml`

---

## Environment variables for deployment

Paste these into **Streamlit Cloud** (App → Settings → Secrets), **Replit** (Secrets), or your platform’s env/config. Replace placeholder values with your real keys.

**Required for the app (search + answer):**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-key
OPENAI_API_KEY=your-openai-api-key
```

**Required if rerank is enabled (default):**

```
COHERE_API_KEY=your-cohere-api-key
```

**Optional (recommended):**

```
MAX_QUERY_LENGTH=2000
RERANK_ENABLED=false
MULTI_QUERY_ENABLED=false
RELEVANCY_CHECK_ENABLED=false
```

**Optional (tracing, embeddings, tuning):**

```
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ai-legal-reasoning
EMBEDDING_MODEL=text-embedding-3-small
CHUNKS_TO_LLM=10
```

Copy-paste block (one key=value per line; fill in the right-hand sides):

```
SUPABASE_URL=
SUPABASE_KEY=
OPENAI_API_KEY=
COHERE_API_KEY=
MAX_QUERY_LENGTH=2000
RERANK_ENABLED=false
MULTI_QUERY_ENABLED=false
RELEVANCY_CHECK_ENABLED=false
```

---

## Case law: night run 2015 → 1926 (Supabase + PDF/Drive)

Two pipelines:

1. **Supabase ingestion** – JSON → `case_law` + `case_law_sections` in Supabase (for search in the app).  
   Command: `make ingest-history ...`
2. **PDF + Google Drive** – existing JSON → PDF → upload to Drive (backup).  
   Commands: `make export-pdf-drive-range ...` (from JSON) or `make scrape-json-pdf-drive-range ...` (scrape then PDF then Drive).

### Pre-flight (before starting the night run)

- [ ] `.env` has `SUPABASE_URL`, `SUPABASE_KEY` (and `OPENAI_API_KEY` if using AI extraction).
- [ ] `USE_AI_EXTRACTION=false` in `.env` for fast, no-LLM ingestion (recommended for 2015→1926).
- [ ] Precedent JSON files exist for 1926–2015 under `data/case_law/supreme_court/precedents/` (e.g. `2015.json` … `1926.json`). If a year is missing, run `make ingest-precedents YEAR=YYYY` or scrape for that year first.
- [ ] For PDF/Drive: `GOOGLE_DRIVE_ROOT_FOLDER_ID` and Drive credentials set in `.env` if you will run `export-pdf-drive-range` or `scrape-json-pdf-drive-range`.

### Step 0: See where you left off (Supabase)

Check which years are already in Supabase so you don’t re-run them:

```bash
make check-ingestion-status
```

Shows documents per year and tracking (processed / total / remaining). If you only care about one year:

```bash
make check-ingestion-status YEAR=2015
```

Optional: sync tracking with actual DB counts:

```bash
make sync-ingestion-status
```

### Step 1: Ingest 2015 down to 1926 into Supabase (precedents only)

Runs newest first (2015, 2014, …, 1926). Uses existing JSON under `data/case_law/supreme_court/precedents/`; if a year’s JSON is missing, that year is scraped first. Expect ~7 hours for 90 years with `USE_AI_EXTRACTION=false`.

```bash
make ingest-history START=1926 END=2015 COURT=supreme_court SUBTYPE=precedent
```

- Ensure `.env` has `SUPABASE_URL`, `SUPABASE_KEY`.
- Set `USE_AI_EXTRACTION=false` in `.env` for regex-only extraction (no LLM cost, faster).
- Precedent JSON files must exist for 1926–2015 (e.g. `data/case_law/supreme_court/precedents/2015.json`, …, `1926.json`). If some are missing, run a scrape or single-year ingest for those years first.

**If Supabase reports Disk IO budget / too many read-write operations:** run ingestion in **batches** and add throttling:

- **Batch by years:** process at most 10 years per run, with 8 seconds pause between years:
  ```bash
  make ingest-history START=1926 END=2000 COURT=supreme_court SUBTYPE=precedent MAX_YEARS=10 YEAR_DELAY=8
  ```
  Each run processes the **newest** `MAX_YEARS` years in [START, END]. Example: first run processes 2000 down to 1991; next run use `END=1990` to process 1990 down to 1981, and so on until you reach 1926.
- **Optional:** in `.env` set `INGESTION_DOC_DELAY_EVERY=25` and `INGESTION_DOC_DELAY_SECONDS=0.5` to pause every 25 documents and spread Disk IO.
- Keep `INGESTION_SKIP_UNCHANGED=true` so already-ingested documents are skipped (fewer writes).

### Step 2 (optional): PDF + Drive for same range

If PDFs are not yet uploaded for 2015→1926 and you use existing JSON only (no scrape):

```bash
make export-pdf-drive-range START=1926 END=2015
```

Requires `GOOGLE_DRIVE_ROOT_FOLDER_ID` and Drive credentials in `.env`. If you need to scrape and then export:

```bash
make scrape-json-pdf-drive-range START=1926 END=2015
```

### Quick reference

| Goal                         | Command                                                                 |
|-----------------------------|-------------------------------------------------------------------------|
| Check Supabase status       | `make check-ingestion-status` or `make check-ingestion-status YEAR=2025` |
| Sync tracking with DB       | `make sync-ingestion-status` or `make sync-ingestion-status YEAR=2025`  |
| Ingest 2015→1926 to Supabase| `make ingest-history START=1926 END=2015 COURT=supreme_court SUBTYPE=precedent` |
| PDF + Drive from JSON (range)| `make export-pdf-drive-range START=1926 END=2015`                      |
| Scrape + JSON + PDF + Drive (range) | `make scrape-json-pdf-drive-range START=1926 END=2015`            |

---

## Case law: single-year and other commands

Set `USE_AI_EXTRACTION=false` in `.env` for regex-only extraction (no LLM cost).

**Ingest single year:**
```bash
make ingest-precedents YEAR=2010
```

**Check status (processed vs remaining):**
```bash
make check-ingestion-status
make check-ingestion-status YEAR=2025
```

Query `case_law_ingestion_tracking` in Supabase for per-year expected/processed/failed.
