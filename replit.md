# AI Legal Reasoning System

## Overview
Finnish Legal AI system that provides legal reasoning using Streamlit UI, LangGraph agent pipeline, and hybrid retrieval (vector + full-text search) with Supabase, OpenAI, and Cohere.

## Recent Changes
- 2026-02-08: Added multilingual support (English + Finnish)
  - Created src/config/translations.py with all UI strings in both languages
  - Language selector in sidebar (English / Suomi)
  - All UI text, status messages, and stream messages are translated
- 2026-02-08: Imported from GitHub, configured for Replit environment
  - Set Streamlit to run on port 5000 with CORS/XSRF disabled for Replit proxy
  - Made OpenAI/LLM client initialization lazy to allow UI to load without API keys
  - Configured deployment as autoscale

## Project Architecture
- **Language**: Python 3.12
- **Frontend**: Streamlit (port 5000)
- **Agent**: LangGraph workflow (analyze → search → reason → respond)
- **Retrieval**: Hybrid search (vector + FTS via Supabase) + Cohere reranking
- **LLM**: OpenAI (gpt-4o-mini for routing, gpt-4o for generation)
- **Database**: Supabase (external, not Replit DB)

## Key Files
- `src/ui/app.py` - Streamlit chat interface
- `src/agent/` - LangGraph agent (graph.py, nodes.py, stream.py, state.py)
- `src/services/retrieval/` - Hybrid search, reranker, generator
- `src/config/settings.py` - Configuration from env vars
- `src/config/translations.py` - Multilingual UI strings (en/fi)
- `.streamlit/config.toml` - Streamlit server config

## Required Environment Variables
- `OPENAI_API_KEY` - OpenAI API key
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon/service key
- `COHERE_API_KEY` - Cohere API key for reranking
- Optional: `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` for observability

## User Preferences
- None recorded yet
