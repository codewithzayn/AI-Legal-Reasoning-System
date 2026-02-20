# KHO (Supreme Administrative Court) Ingestion: 1944–2026

---

## What the scraper keeps (nothing important skipped)

The pipeline is designed so that **no important content is dropped**:

| What | How it’s kept |
|------|-------------------------------|
| **Full page text** | The whole visible main content (article/main) is stored as `full_text` in each document. That includes **all headings, summaries, body text, and structure** as shown on the Finlex page. |
| **Keywords (Asiasanat)** | Parsed from the header and stored in `legal_domains` (and in the JSON). Multi-line keyword blocks are kept. |
| **Case ID** | Detected from the page (KHO:YYYY:N, old formats, date-based) and stored in `case_id`. |
| **Decision date, diary number, ECLI, volume** | Taken from the header and stored in structured fields. |
| **Judges line** | Last paragraph matching “Asian ovat ratkaisseet…” is stored in `judges`. |

Only **UI-only lines** are skipped (e.g. “Kieliversiot”, “Language versions”, “Suomi”, “Ruotsi”) so they don’t appear as document content. All real headings, summaries, and body text stay in `full_text` and in the JSON/PDF.

---

## Test run 2025–2026: scrape → JSON → Drive only (no Supabase)

Use this to check that you get the relevant data before doing a full run or any ingestion.

**Command (scrape + JSON + Google Drive only; does NOT run ingestion / does NOT add anything to Supabase):**

```bash
make kho-scrape-json-pdf-drive-range START=2025 END=2026
```

Or without Make:

```bash
python3 scripts/case_law/core/scrape_json_pdf_drive.py \
  --court supreme_administrative_court \
  --start 2025 \
  --end 2026
```

This will:

1. Scrape KHO for 2025 and 2026 (all three subtypes: precedent, other, brief).
2. Write JSON under `data/case_law/supreme_administrative_court/...`.
3. Generate PDFs and upload them to Google Drive (if configured).

**Do not run** any of these for this test (they add data to Supabase):

- `make ingest-kho`
- `python scripts/case_law/core/ingest_history.py ...`

After the run, check the JSON files and (if enabled) the PDFs on Drive to confirm keywords, case IDs, headings, and summaries are present. When you’re satisfied, you can run the full range and/or the ingestion pipeline.

---

## Checklist: nothing missed

| Step | What to run | What gets covered |
|------|-------------|-------------------|
| 1. Scrape | `make kho-scrape-json-pdf-drive-range START=1944 END=2026` | All three subtypes (precedent, other, brief) for every year 1944–2026. JSON + PDF + Drive. |
| 2. Ingest to Supabase | Per year: `make ingest-kho YEAR=YYYY` or range: `python scripts/case_law/core/ingest_history.py --court supreme_administrative_court --start 1944 --end 2026` | All three subtypes per year are loaded from JSON and written to Supabase (single-year script now ingests precedent + other + brief). |

- **Pagination:** Scraper follows “Seuraava sivu” on index pages; if Finlex changes that label, later pages could be skipped (rare).
- **Empty years:** Many older years (e.g. 1944–1980s) may have no KHO data on Finlex; the script logs “No documents” and continues.
- **Failed cases:** Any failed fetch or store is logged and recorded in `case_law_ingestion_errors`; check logs and that table after a run.

---

## Format check: OK

The existing pipeline matches Finlex’s KHO structure:

| Finlex (EN)        | Finlex (FI)     | Our scraper | JSON dir            |
|--------------------|-----------------|------------|---------------------|
| Precedents         | ennakkopaatokset| precedent  | precedents/         |
| Other decisions    | muut            | other      | other_decisions/    |
| Brief explanations| lyhyet          | brief      | brief_explanations/ |

- **Index URLs:** `https://www.finlex.fi/fi/oikeuskaytanto/korkein-hallinto-oikeus/ennakkopaatokset/{year}` (and `muut/{year}`, `lyhyet/{year}`).
- **Case pages:** Same pattern as KKO; scraper collects links with `/{year}/` and fetches each case.
- **Output:** One JSON per (court, year, subtype), then PDF per case, then upload to Google Drive.

No change needed to the format before running the pipeline.

---

## 1. Two-step flow (recommended): JSON only, then PDF + Drive

**Step 1 – Scrape and save JSON only** (no PDF, no Drive):
```bash
make kho-scrape-json-only-range START=1946 END=2024 KHO_TYPE=precedent
```

**Step 2 – Convert JSON to PDF and upload to Google Drive** (same layout/format as Supreme Court):
```bash
make kho-export-pdf-drive-range START=1946 END=2024 KHO_TYPE=precedent
```

Supreme Administrative Court PDFs use the **same formatting** as Supreme Court (same `doc_to_pdf` in `src/services/case_law/pdf_export.py`).

---

## 2. Scrape → JSON → PDF → Google Drive in one run (1944–2026)

**Only Supreme Administrative Court precedents** (no Other, no Brief)—e.g. for 1946–2024:
```bash
make kho-scrape-json-pdf-drive-range START=1946 END=2024 KHO_TYPE=precedent
```

Single run for **all three subtypes** (precedent, other, brief) for years 1944–2026:

```bash
# From project root
make kho-scrape-json-pdf-drive-range START=1944 END=2026
```

Or without Make:

```bash
python3 scripts/case_law/core/scrape_json_pdf_drive.py \
  --court supreme_administrative_court \
  --start 1944 \
  --end 2026
```

- **JSON:** `data/case_law/supreme_administrative_court/{precedents|other_decisions|brief_explanations}/YYYY.json`
- **PDFs (if CASE_LAW_EXPORT_LOCAL=1):** `data/case_law_export/Supreme Administrative Court .../YYYY/`
- **Google Drive:** Same structure under `GOOGLE_DRIVE_ROOT_FOLDER_ID`.

Many older years (e.g. 1944–1980s) may have no or few documents; the script will log “No documents for …” and continue.

---

## 3. Faster: precedents only first

To get precedents (main material) first and run faster:

```bash
make kho-scrape-json-pdf-drive-range START=1944 END=2026 KHO_TYPE=precedent
```

Then, if you want the rest:

```bash
make kho-scrape-json-pdf-drive-range START=1944 END=2026 KHO_TYPE=other
make kho-scrape-json-pdf-drive-range START=1944 END=2026 KHO_TYPE=brief
```

---

## 4. Run in background (long run)

```bash
nohup make kho-scrape-json-pdf-drive-range START=1944 END=2026 > kho_scrape_1944_2026.log 2>&1 &
```

---

## 5. After JSON + Drive: ingestion into Supabase

When JSON (and optionally Drive) are done, run ingestion (chunking, embedding, Supabase). **Ingest all three subtypes** so nothing is missed:

**Single year (precedent + other + brief):**
```bash
make ingest-kho YEAR=2026
```

**Year range (all subtypes, all years):**
```bash
python scripts/case_law/core/ingest_history.py --court supreme_administrative_court --start 1944 --end 2026
```

Optional: ingest only one subtype, e.g. `make ingest-kho YEAR=2026` with `TYPE=precedent` (see Makefile) or `--type precedent` for the Python script.

---

## Prerequisites

- `.env`: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY` (for later ingestion).
- Google Drive (optional): `GOOGLE_DRIVE_ROOT_FOLDER_ID`, credentials under project root.
- `CASE_LAW_EXPORT_LOCAL=1` if you want PDFs written locally.
- Playwright: `playwright install chromium` (for scraping).
