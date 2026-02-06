# Case Law: Separate PDF Backup Pipeline and Google Drive

## Approach: Separate backup only (no PDF during ingestion)

- **Ingestion pipeline** stays unchanged: scrape → extract → embed → store in Supabase. No PDF generation and no Google Drive upload during ingestion. When you scrape, you do not convert to PDF.
- **Backup pipeline** is a separate, standalone process: you run a command for a specific year (or year range) that loads documents from existing JSON cache, converts each to PDF, and uploads to Google Drive. You run it when you want to refresh the Drive backup (e.g. after ingesting 2025, run backup for 2025; later run for 2026).
- **Typical workflow:** Ingest a year (e.g. `make ingest-precedents YEAR=2025`) → when ready, run backup for that year (e.g. `make export-pdf-drive YEAR=2025`) → PDFs appear locally and on Drive. Next year: ingest 2026, then run `make export-pdf-drive YEAR=2026`. No re-conversion of already-backed-up years unless you re-run the backup command.

## Commands you will run

| Goal | Command |
|------|---------|
| Backup one year (all types: precedents, rulings, leaves) | `make export-pdf-drive YEAR=2025` |
| Backup a range of years | `make export-pdf-drive START=2020 END=2026` |
| Backup one type and one year (e.g. testing) | `make export-pdf-drive TYPE=precedent YEAR=2025` |

- Each command loads only from **existing** JSON under `data/case_law/supreme_court/{precedents|rulings|leaves_to_appeal}/{year}.json`. If a file is missing for a year/type, that year/type is skipped (no scrape).
- Ingestion is unchanged: e.g. `make ingest-precedents YEAR=2025` (no PDF/Drive). Run export when you want backup.

## Target folder structure (local and Google Drive)

```
Case Law Backup/
├── Supreme Court Precedents/
│   ├── 2025/
│   │   ├── KKO:2025:1.pdf
│   │   └── ...
│   ├── 2026/
│   └── ...
├── Supreme Court Rulings/
│   └── ...
└── Supreme Court Leaves to Appeal/
    └── ...
```

## What the implementation needs

1. **Config/env:** `CASE_LAW_EXPORT_ROOT`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `GOOGLE_APPLICATION_CREDENTIALS` (or path to service account JSON).
2. **PDF module:** Turn `CaseLawDocument.full_text` into a PDF (Finnish-safe, one file per doc).
3. **Local export:** Write PDFs to `{export_root}/{TypeLabel}/{year}/{case_id}.pdf`.
4. **Google Drive module:** Service account auth; create folders by name (type → year); upload file; update if exists.
5. **Standalone script:** `scripts/case_law/export_pdf_to_drive.py` with `--year`, `--start`/`--end`, optional `--type`. Load from JSON only; no scrape. This is the **only** place that does PDF + Drive.
6. **Makefile:** Targets `export-pdf-drive YEAR=...`, `START=... END=...`, optional `TYPE=...`.
7. **No changes** to `scripts/case_law/core/ingestion_manager.py` (ingestion never runs PDF or Drive).

## What you need to provide for Google Drive (Option A – service account)

- **Root folder ID:** Create a folder in Drive (e.g. "Case Law Backup"), share it with the service account email (Editor), and provide the folder ID from the URL.
- **Service account JSON key:** Path via `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON_PATH`; never commit the key.
