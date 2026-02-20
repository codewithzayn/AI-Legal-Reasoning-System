# AI Legal Reasoning System – All commands (run from project root)
# Usage: make <target>   or   make help

.PHONY: help install run run-cli run-api test \
	lint format lint-fix fix \
	ingest-precedents ingest-precedents-force ingest-precedents-case-ids fix-json-precedents update-case-full-text verify-json-full-text check-ingestion-status sync-ingestion-status \
	ingest-rulings ingest-leaves ingest-kko ingest-kho ingest-history \
	scrape-json-pdf-drive scrape-json-pdf-drive-range \
	export-pdf-drive export-pdf-drive-range export-pdf-drive-type \
	kho-scrape-json-pdf-drive kho-scrape-json-pdf-drive-range \
	kho-export-pdf-drive kho-export-pdf-drive-range kho-export-pdf-drive-type \
	ingest-finlex \
	verify-ingestion reingest-cases \
	ingest-eu ingest-eu-seed ingest-eu-fi-refs ingest-echr-finland fetch-latest-curia

# Default: list all commands with short descriptions
help:
	@echo "=============================================="
	@echo "  AI Legal Reasoning System – Commands"
	@echo "=============================================="
	@echo ""
	@echo "--- Install ---"
	@echo "  make install              Install Python dependencies (pip install -r requirements.txt)"
	@echo ""
	@echo "--- Start the app (frontend / backend) ---"
	@echo "  make run                  Start Streamlit UI (main app, default entrypoint)"
	@echo "  make run-cli              Start CLI mode (interactive chat in terminal)"
	@echo "  make run-api              Start FastAPI ingest API on http://0.0.0.0:8000"
	@echo ""
	@echo "--- Tests ---"
	@echo "  make test                 Run all tests (pytest)"
	@echo ""
	@echo "--- Linting & Formatting (Ruff) ---"
	@echo "  make lint                 Check code for lint errors"
	@echo "  make lint-fix             Auto-fix lint errors"
	@echo "  make format               Format all Python files"
	@echo "  make fix                  Lint-fix + format (run before commit to avoid pre-commit stash conflicts)"
	@echo ""
	@echo "--- Case law: Supreme Court (KKO) ---"
	@echo "  make ingest-precedents    Ingest KKO precedents (Ennakkopäätökset). Optional: YEAR=2026"
	@echo "  make ingest-precedents-force  Same, force re-scrape (ignore JSON cache)"
	@echo "  make ingest-precedents-case-ids  Ingest only given case IDs (JSON + Supabase). YEAR=... CASE_IDS=\"...\""
	@echo "  make fix-json-precedents  Re-scrape case IDs, update JSON only (no Supabase). Fix empty full_text."
	@echo "  make update-case-full-text  Manually set full_text for one case. YEAR=... CASE_ID=... FILE=..."
	@echo "  make verify-json-full-text  Scan precedent JSON for empty full_text; print fix commands."
	@echo "  make check-ingestion-status  Show Supabase ingestion status (per year). Optional: YEAR=..."
	@echo "  make sync-ingestion-status   Update tracking.processed_cases from case_law (sync DB). Optional: YEAR=..."
	@echo "  make verify-ingestion     Find cases with 0 sections or 0 references. Optional: YEAR=... START=... END=..."
	@echo "  make verify-ingestion YEAR=1983 FIX=1   Re-ingest all 0-section cases for that year"
	@echo "  make reingest-cases YEAR=1983 CASE_IDS='KKO:1983-II-124 KKO:1983-II-125'   Re-ingest specific case IDs"
	@echo "  make ingest-rulings       Ingest KKO other rulings (Muut päätökset). Optional: YEAR=2026"
	@echo "  make ingest-leaves        Ingest KKO leaves to appeal (Valitusluvat). Optional: YEAR=2026"
	@echo "  make ingest-kko           Ingest KKO all subtypes (precedent + ruling + leave) for one year. Optional: YEAR=2026"
	@echo "  make ingest-history       Ingest case law for a year range. Optional: START=1926 END=2000 COURT=... SUBTYPE=... MAX_YEARS=10 YEAR_DELAY=5"
	@echo ""
	@echo "--- Case law: Scrape → JSON + PDF (ditto) → Drive (one command) ---"
	@echo "  make scrape-json-pdf-drive  Scrape year → save JSON → PDF (same as website) → Drive. YEAR=2025"
	@echo "  make scrape-json-pdf-drive-range  Same, range. START=2020 END=2023"
	@echo "--- Case law: PDF backup from existing JSON (no scrape) ---"
	@echo "  make export-pdf-drive     Export one year to PDF + Drive. Optional: YEAR=2025"
	@echo "  make export-pdf-drive-range  Export year range. Optional: START=2020 END=2026"
	@echo "  make export-pdf-drive-type   Export one type for one year. Optional: TYPE=precedent YEAR=2025"
	@echo ""
	@echo "--- Case law: Supreme Administrative Court (KHO) ---"
	@echo "  make ingest-kho                             Ingest KHO case law for one year. Optional: YEAR=2026"
	@echo "  make kho-scrape-json-pdf-drive              KHO: Scrape → JSON → PDF → Drive. YEAR=2025"
	@echo "  make kho-scrape-json-pdf-drive-range        KHO: Same, year range. START=2020 END=2024"
	@echo "  make kho-export-pdf-drive                   KHO: Export existing JSON to PDF + Drive. YEAR=2025"
	@echo "  make kho-export-pdf-drive-range             KHO: Same, year range. START=2020 END=2026"
	@echo "  make kho-export-pdf-drive-type              KHO: Export one subtype. TYPE=precedent YEAR=2025"
	@echo ""
	@echo "--- Finlex (statutes) ---"
	@echo "  make ingest-finlex       Bulk ingest Finlex statutes"
	@echo ""
	@echo "--- EU Case Law (CJEU, ECHR, General Court) ---"
	@echo "  make ingest-eu           Ingest EU cases by court + year. COURT=cjeu YEAR=2024 LANG=EN"
	@echo "  make ingest-eu-seed      Seed from existing cited_eu_cases in Finnish decisions"
	@echo "  make ingest-eu-fi-refs   Finnish preliminary references (all CJEU cases referred by Finnish courts)"
	@echo "  make ingest-echr-finland ECHR cases involving Finland"
	@echo "  make fetch-latest-curia  Latest 14 days from CURIA (DAYS=14 LANG=en)"
	@echo ""
	@echo "Examples:"
	@echo "  make run"
	@echo "  make ingest-precedents YEAR=2025"
	@echo "  make ingest-history COURT=supreme_court START=1926 END=2000 SUBTYPE=precedent"
	@echo "  make ingest-history START=1926 END=2000 COURT=supreme_court SUBTYPE=precedent MAX_YEARS=10 YEAR_DELAY=8"

# ------------------------------------------------------------------------------
# Install
# ------------------------------------------------------------------------------
install:
	pip install -r requirements.txt

# ------------------------------------------------------------------------------
# Start the app (frontend and backend entrypoints)
# ------------------------------------------------------------------------------
run:
	streamlit run src/ui/app.py --server.fileWatcherType none

run-cli:
	python main.py --cli

run-api:
	uvicorn src.api.ingest:app --host 0.0.0.0 --port 8000

# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------
test:
	python -m pytest tests/ -v

# ------------------------------------------------------------------------------
# Linting & Formatting (Ruff – runs automatically on commit via pre-commit)
# ------------------------------------------------------------------------------
lint:
	ruff check src/ scripts/ tests/ main.py

lint-fix:
	ruff check --fix src/ scripts/ tests/ main.py

format:
	ruff format src/ scripts/ tests/ main.py

# Run before 'git add' and 'git commit' so pre-commit hooks pass (no unstaged vs staged conflict).
fix: lint-fix format

# ------------------------------------------------------------------------------
# Case law: Supreme Court (KKO)
# ------------------------------------------------------------------------------
YEAR ?= 2026
ingest-precedents:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR)

ingest-precedents-force:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR) --force

# Ingest only specific precedent case IDs. Updates JSON + Supabase.
# Example: make ingest-precedents-case-ids YEAR=2018 CASE_IDS="KKO:2018:72,KKO:2018:73"
CASE_IDS ?=
ingest-precedents-case-ids:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR) --case-ids "$(CASE_IDS)"

# Re-scrape case IDs and update JSON only (no Supabase). Use to fix empty full_text before PDF/Drive export.
# Example: make fix-json-precedents YEAR=1983 CASE_IDS="KKO:1983:II-55,KKO:1983:II-56"
fix-json-precedents:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR) --case-ids "$(CASE_IDS)" --json-only

# Manually update full_text for a case (when scraper fails). FILE=path to text file.
# Example: make update-case-full-text YEAR=1983 CASE_ID=KKO:1983:II-55 FILE=content.txt
CASE_ID ?=
FILE ?=
update-case-full-text:
	python3 scripts/case_law/supreme_court/update_case_full_text.py --year $(YEAR) --case-id "$(CASE_ID)" --file "$(FILE)"

# Verify precedent JSON files for empty full_text; print re-scrape commands.
verify-json-full-text:
	python3 scripts/case_law/supreme_court/verify_json_full_text.py

# Check Supabase ingestion status (total/processed/failed per year). Optional: YEAR=2025
check-ingestion-status:
	python3 scripts/case_law/core/check_ingestion_status.py $(if $(YEAR),--year $(YEAR),)

# Sync case_law_ingestion_tracking.processed_cases from actual case_law count (fixes out-of-sync tracking)
sync-ingestion-status:
	python3 scripts/case_law/core/check_ingestion_status.py --sync $(if $(YEAR),--year $(YEAR),)

ingest-rulings:
	python3 scripts/case_law/supreme_court/ingest_rulings.py --year $(YEAR)

ingest-leaves:
	python3 scripts/case_law/supreme_court/ingest_rulings.py --subtype leave_to_appeal --year $(YEAR)

ingest-kko:
	python3 scripts/case_law/supreme_court/ingest_all_subtypes.py --year $(YEAR)

START ?= 1926
END ?= 2026
COURT ?= supreme_court
SUBTYPE ?=
MAX_YEARS ?=
YEAR_DELAY ?= 5
ingest-history:
	python3 scripts/case_law/core/ingest_history.py --start $(START) --end $(END) --court $(COURT) $(if $(SUBTYPE),--subtype $(SUBTYPE),) $(if $(MAX_YEARS),--max-years $(MAX_YEARS),) --year-delay $(YEAR_DELAY)

# ------------------------------------------------------------------------------
# Case law: Supreme Administrative Court (KHO)
# ------------------------------------------------------------------------------
ingest-kho:
	python3 scripts/case_law/supreme_administrative_court/ingest.py --year $(YEAR) $(if $(KHO_TYPE),--type $(KHO_TYPE),)

# KHO: Scrape website → save JSON → PDF (ditto copy) → Google Drive (one command, no Supabase)
KHO_TYPE ?=
kho-scrape-json-pdf-drive:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --year $(YEAR) $(if $(KHO_TYPE),--type $(KHO_TYPE),)

kho-scrape-json-pdf-drive-range:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --start $(START) --end $(END) $(if $(KHO_TYPE),--type $(KHO_TYPE),)

# KHO: Scrape only → save JSON (no PDF, no Drive). Then run kho-export-pdf-drive-range to upload.
kho-scrape-json-only-range:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --start $(START) --end $(END) $(if $(KHO_TYPE),--type $(KHO_TYPE),) --json-only

# KHO: One year only, precedents only, JSON only (free/light run).
kho-scrape-json-only:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --year $(YEAR) --type precedent --json-only

# KHO: Export existing JSON → PDF → Google Drive (no scraping)
kho-export-pdf-drive:
	python3 scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --year $(YEAR) $(if $(KHO_TYPE),--type $(KHO_TYPE),)

kho-export-pdf-drive-range:
	python3 scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --start $(START) --end $(END) $(if $(KHO_TYPE),--type $(KHO_TYPE),)

kho-export-pdf-drive-type:
	python3 scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --type $(KHO_TYPE) --year $(YEAR)

# ------------------------------------------------------------------------------
# Case law: Scrape → JSON + PDF (ditto copy of website) → Google Drive (one command)
# ------------------------------------------------------------------------------
# No extraction, no Supabase. PDF content = scraped website text (1:1).
# Requires: GOOGLE_DRIVE_ROOT_FOLDER_ID + credentials in .env
scrape-json-pdf-drive:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --year $(YEAR)

scrape-json-pdf-drive-range:
	python3 scripts/case_law/core/scrape_json_pdf_drive.py --start $(START) --end $(END)

# ------------------------------------------------------------------------------
# Case law: PDF export and Google Drive backup (from existing JSON only, no scrape)
# ------------------------------------------------------------------------------
# Export existing JSON cache to PDF and upload to Drive. Run after scrape or ingest.
# Requires: GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_DRIVE_ROOT_FOLDER_ID in .env
export-pdf-drive:
	python3 scripts/case_law/core/export_pdf_to_drive.py --year $(YEAR)

export-pdf-drive-range:
	python3 scripts/case_law/core/export_pdf_to_drive.py --start $(START) --end $(END)

TYPE ?= precedent
export-pdf-drive-type:
	python3 scripts/case_law/core/export_pdf_to_drive.py --type $(TYPE) --year $(YEAR)

# ------------------------------------------------------------------------------
# Case law: Verify ingestion completeness
# ------------------------------------------------------------------------------
# Find cases with 0 sections or 0 references (incomplete ingestion).
# FIX=1 re-ingests all 0-section cases for that year.
FIX ?=
CASE_IDS ?=
verify-ingestion:
	python3 scripts/case_law/core/verify_ingestion.py $(if $(YEAR),--year $(YEAR),--start $(START) --end $(END)) --court $(COURT) $(if $(SUBTYPE),--subtype $(SUBTYPE),--subtype precedent) $(if $(FIX),--fix,)

reingest-cases:
	python3 scripts/case_law/core/verify_ingestion.py --year $(YEAR) --court $(COURT) $(if $(SUBTYPE),--subtype $(SUBTYPE),--subtype precedent) --fix --case-ids $(CASE_IDS)

# ------------------------------------------------------------------------------
# Finlex (statutes)
# ------------------------------------------------------------------------------
ingest-finlex:
	python3 scripts/finlex_ingest/bulk_ingest.py

# ------------------------------------------------------------------------------
# EU Case Law (CJEU, ECHR, General Court)
# ------------------------------------------------------------------------------
EU_COURT ?= cjeu
LANG ?= EN
DAYS ?= 14
ingest-eu:
	python3 scripts/case_law/eu/ingest_eu.py --court $(EU_COURT) --year $(YEAR) --language $(LANG)

ingest-eu-seed:
	python3 scripts/case_law/eu/seed_from_citations.py

ingest-eu-fi-refs:
	python3 scripts/case_law/eu/ingest_fi_preliminary_refs.py

ingest-echr-finland:
	python3 scripts/case_law/eu/ingest_echr_finland.py

fetch-latest-curia:
	python3 scripts/case_law/eu/fetch_latest_curia.py --days $(DAYS) --language $(LANG)
