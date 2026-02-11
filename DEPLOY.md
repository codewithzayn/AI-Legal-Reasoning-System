# Deployment: Streamlit Cloud (*.streamlit.app)

**Note:** Streamlit does not run on Vercel. Use **Streamlit Community Cloud** for `*.streamlit.app` URLs.

## Streamlit Community Cloud (Recommended)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in → New app → Select repo, branch, main file: `app.py`
4. Add env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, `COHERE_API_KEY`
5. Deploy

## Railway / Render (Procfile)

Uses `Procfile`: `web: streamlit run app.py --server.port=8501 --server.address=0.0.0.0`

Set `PORT` env var if the platform requires it; otherwise 8501 is used.

## Concurrency

- Session state is per-user (Streamlit isolates)
- Supabase client uses async lock for concurrent requests
- CORS and XSRF enabled in `.streamlit/config.toml`
