# Deployment: Streamlit Cloud (*.streamlit.app)

**Note:** Streamlit does not run on Vercel. Use **Streamlit Community Cloud** for `*.streamlit.app` URLs.

## Streamlit Community Cloud (Recommended)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in → New app → Select repo, branch, main file: `app.py`
4. Add env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, `COHERE_API_KEY`
5. Deploy

## Railway / Render (Procfile)

Uses `Procfile`: `web: sh -c 'streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0'`

- `PORT` is set by the platform (Railway, Render, Heroku); defaults to 8501 if unset.

## Concurrency

- Session state is per-user (Streamlit isolates)
- Supabase client uses async lock for concurrent requests
- CORS and XSRF enabled in `.streamlit/config.toml`

## Case Law Ingestion (Supabase)

Set `USE_AI_EXTRACTION=false` in `.env` for regex-only extraction (no LLM cost).

**Ingest precedents 2025→1926 (newest first):**
```bash
make ingest-history START=1926 END=2025 COURT=supreme_court SUBTYPE=precedent
```

**Ingest single year:**
```bash
make ingest-precedents YEAR=2010
```

**Check status (processed vs remaining):**
```bash
make check-ingestion-status
# or for one year: make check-ingestion-status YEAR=2025
```

Query `case_law_ingestion_tracking` in Supabase for per-year expected/processed/failed.
