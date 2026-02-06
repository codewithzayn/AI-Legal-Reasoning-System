# Data sources – Finlex API vs Case law (web)

The system ingests two kinds of Finnish legal content. They are handled differently because only one has an official API.

---

## 1. Finlex documents (statutes, etc.) – **API, documented**

- **Source:** Finlex Open Data API (documented).
- **How we get data:** HTTP API calls. Structured responses (e.g. XML/Akoma Ntoso).
- **Where in the project:**
  - **Service:** `src/services/finlex/` – client, ingestion, XML parser, storage.
  - **Scripts:** `scripts/finlex_ingest/` – e.g. `bulk_ingest.py`.
  - **API:** `src/api/ingest.py` can trigger Finlex ingestion.
- **Why this structure:** One documented API → one client, clear pipeline (fetch → parse → chunk → store).

---

## 2. Case law (Supreme Court, etc.) – **No API, website scraping**

- **Source:** Court websites (e.g. Finlex web pages for KKO precedents). No official API or machine-readable feed.
- **How we get data:** Browser automation (Playwright) to load pages and extract text, then regex + optional LLM to structure it.
- **Where in the project:**
  - **Service:** `src/services/case_law/` – scraper, extractors (regex, hybrid), storage.
  - **Scripts:** `scripts/case_law/` – per court and subtype (e.g. `supreme_court/ingest_precedents.py`).
- **Why this structure:** No API → we scrape and extract; pipeline is scrape → extract (regex/LLM) → store. Separate from Finlex so API vs scraping are not mixed.

---

## Summary

| Type        | Has API/docs? | How we ingest      | Main code location        |
|------------|----------------|--------------------|---------------------------|
| **Finlex** | Yes (API)      | API client + parse | `src/services/finlex/`, `scripts/finlex_ingest/` |
| **Case law** | No           | Web scraping + extract | `src/services/case_law/`, `scripts/case_law/`   |

The product structure separates these two on purpose: **Finlex = API path**, **Case law = scraping path**. Shared pieces (e.g. storage, embeddings, retrieval) live in `common/` and `retrieval/` and are used by both.
