# AI Legal Reasoning System – Conventions & Structure

Where to put what, and how the project is organized.

---

## Conventions at a glance

| Purpose | Where to keep it | Example |
|--------|-------------------|---------|
| **App / library code** | `src/` | `src/services/case_law/`, `src/agent/` |
| **Config & env** | `src/config/` + `.env` | `settings.py`, `LOG_FORMAT`, `CASE_LAW_NO_JSON_CACHE` |
| **Entrypoints (app)** | `main.py`, `src/ui/`, `src/api/` | Streamlit, FastAPI, CLI |
| **Batch / ingestion** | `scripts/` | `scripts/case_law/supreme_court/ingest_precedents.py` |
| **SQL migrations** | `scripts/migrations/` | `case_law_tables.sql`, `legal_chunks.sql` |
| **Architecture / design** | `docs/` | This file, [DATA_SOURCES.md](DATA_SOURCES.md), [RETRIEVAL_AND_RERANK.md](RETRIEVAL_AND_RERANK.md) |
| **Tests** | `tests/` | `tests/unit/services/case_law/`, `tests/integration/` |
| **Runtime data / cache** | `data/` (gitignored) | `data/case_law/supreme_court/precedents/2026.json` |

---

## Directory roles

### Data sources (why two paths)

- **Finlex documents** – Have a documented API. Ingested via **API client** (`src/services/finlex/`, `scripts/finlex_ingest/`).
- **Case law** – No API; we use **website scraping** (Playwright) and extraction (`src/services/case_law/`, `scripts/case_law/`). See **[docs/DATA_SOURCES.md](DATA_SOURCES.md)**.

---

### `src/` – Application code only

- All importable application and library code lives here.
- **Do not** put runnable scripts or one-off tools under `src/`; use `scripts/` instead.
- Subpackages:
  - `config/` – Logging, settings, env-driven config.
  - `agent/` – LangGraph (graph, nodes, state, stream).
  - `api/` – FastAPI routes (e.g. ingest).
  - `ui/` – Streamlit app.
  - `utils/` – Shared helpers (e.g. chat).
  - `services/` – Domain logic: **`finlex/`** (API), **`case_law/`** (scraping), `common/`, `retrieval/`.

### `scripts/` – Runnable jobs and migrations

- **Finlex ingestion:** `finlex_ingest/` – uses the Finlex API (documented).
- **Case law:** `case_law/` – per court/subtype; uses scraping (no API). See [DATA_SOURCES.md](DATA_SOURCES.md).
  - **Core** (`case_law/core/`): shared pipeline – `ingestion_manager.py`, `ingest_history.py`, `export_pdf_to_drive.py`, `scrape_json_pdf_drive.py`, `check_ingestion_status.py` (Supabase ingestion status).
  - **Supreme Court** (`case_law/supreme_court/`): `ingest_precedents.py`, `ingest_rulings.py` (rulings + leave_to_appeal via --subtype), `ingest_all_subtypes.py`, `verify_json_full_text.py` (scan JSON for empty full_text), `update_case_full_text.py` (manual full_text fix).
- **Migrations:** `migrations/*.sql` – all schema/DB changes.
- Scripts import from `src/` only. Run from **project root** (optionally with `PYTHONPATH` set to project root).

### `docs/` – Design and conventions

- **CONVENTIONS.md** (this file) – structure, commands, git/venv.
- **DATA_SOURCES.md** – Finlex API vs case law scraping.
- **RETRIEVAL_AND_RERANK.md** – chunks to LLM, Cohere rerank, inotify.
- No code; markdown only.

### `tests/` – Automated tests

- Mirror `src/` where useful: e.g. `tests/unit/services/case_law/`, `tests/integration/`.
- Use **pytest**. Run from project root: `pytest` or `python -m pytest`.

### `data/` – Runtime data and cache

- Gitignored. Local JSON cache, downloaded files, etc.
- Paths like `data/case_law/<court>/<subtype>/<year>.json` follow the conventions above.

---

## Config and environment

- **Code config:** `src/config/settings.py` and `src/config/logging_config.py`.
- **Secrets and env-specific values:** `.env` (never committed). Copy from `.env.example`. For every variable see `.env.example`; do not commit `.env`.
- No hardcoded secrets, API keys, or DB URLs in code.

### Logging

- **Single entry point:** All modules use `from src.config.logging_config import setup_logger` and `logger = setup_logger(__name__)`.
- **No `print()` in library or pipeline code:** Use `logger.info()`, `logger.warning()`, `logger.error()` (or `logger.debug()` / `logger.exception()`). CLI scripts that produce human-readable reports (e.g. `verify_json_full_text.py`) also use the logger with `LOG_FORMAT=simple` so output is message-only.
- **Format:** Use `%s` placeholders in log messages (e.g. `logger.info("Count: %s", n)`), not f-strings, so formatting is lazy and consistent.
- **Env:** `LOG_LEVEL` (default INFO), `LOG_FORMAT` – set to `simple` for human-readable progress (e.g. ingestion, verify scripts); unset for JSON logs in production.

---

## Naming conventions

- **Ingestion scripts (case law):** `ingest_<subtype>.py` or unified scripts (e.g. `ingest_precedents.py`, `ingest_rulings.py` with `--subtype ruling` or `--subtype leave_to_appeal`). Use `ingest_all_subtypes.py` when the script runs all subtypes for that court in one go. The folder already names the court (e.g. `supreme_court/`), so the file name describes *what* is ingested.
- **Finlex:** `bulk_ingest.py` under `scripts/finlex_ingest/` for bulk statute ingestion.
- **API module:** `src/api/ingest.py` is the FastAPI app for ingest endpoints (not a script; it’s an importable module).
- **No generic `ingest.py`** in a court folder when that folder has multiple subtypes; use `ingest_all_subtypes.py` or one script per subtype so names are explicit and consistent.

---

## Adding new pieces

- **New court or ingestion type:** New dir under `scripts/case_law/` (or similar), reusing `scripts/case_law/core/ingestion_manager.py`.
- **New service domain:** New package under `src/services/` (e.g. `src/services/new_domain/`).
- **New migration:** New `.sql` file under `scripts/migrations/`.
- **New tests:** Under `tests/unit/` or `tests/integration/`, mirroring the module under test.

---

## What to commit vs ignore, and venv

- **Commit:** Source code (`src/`, `scripts/`, `tests/`), `.env.example`, `requirements.txt`, docs, migrations, Makefile, `main.py`. Do not add these to `.gitignore`.
- **Do not commit:** `.env` (secrets), `.venv/` / `venv/`, `data/`, `__pycache__/`, `.pytest_cache/`. These must be in `.gitignore`.
- **Venv:** Use one per project. Create: `python3 -m venv .venv`. Activate: `source .venv/bin/activate` (Linux/macOS). Then `pip install -r requirements.txt`. Do not commit `.venv/`.

---

## Commands reference

All commands from **project root**. Prefer **Make:** `make <target>` (e.g. `make run`, `make test`). Run `make help` for the full list.

| Command | Description |
|--------|-------------|
| `make install` | Install dependencies (`pip install -r requirements.txt`) |
| `make run` | **Streamlit UI** – http://localhost:8501 |
| `make run-cli` | CLI chat |
| `make run-api` | FastAPI ingest API – http://0.0.0.0:8000 |
| `make test` | Run pytest |

**Case law (KKO):** `make ingest-precedents`, `make ingest-precedents-force`, `make ingest-precedents-case-ids`, `make fix-json-precedents`, `make update-case-full-text`, `make verify-json-full-text`, `make check-ingestion-status`, `make ingest-rulings`, `make ingest-leaves`, `make ingest-kko`, `make ingest-history` (START/END/COURT).  
**PDF/Drive backup:** `make export-pdf-drive`, `make export-pdf-drive-range`, `make export-pdf-drive-type`.  
**KHO:** `make ingest-kho`. **Finlex:** `make ingest-finlex`.  
**Linting:** `make lint`, `make lint-fix`, `make format`.

If imports fail, set `PYTHONPATH` to project root (e.g. `export PYTHONPATH=$(pwd)` or use `setup.sh`). Shell equivalents for each target are in the [Makefile](../Makefile).
