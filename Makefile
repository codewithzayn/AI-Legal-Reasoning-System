# AI Legal Reasoning System – All commands (run from project root)
# Usage: make <target>   or   make help

.PHONY: help install run run-cli run-api test \
	ingest-precedents ingest-precedents-force ingest-rulings ingest-leaves ingest-kko ingest-kho ingest-history \
	ingest-finlex

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
	@echo "--- Case law: Supreme Court (KKO) ---"
	@echo "  make ingest-precedents    Ingest KKO precedents (Ennakkopäätökset). Optional: YEAR=2026"
	@echo "  make ingest-precedents-force  Same, force re-scrape (ignore JSON cache)"
	@echo "  make ingest-rulings       Ingest KKO other rulings (Muut päätökset). Optional: YEAR=2026"
	@echo "  make ingest-leaves        Ingest KKO leaves to appeal (Valitusluvat). Optional: YEAR=2026"
	@echo "  make ingest-kko           Ingest KKO all subtypes (precedent + ruling + leave) for one year. Optional: YEAR=2026"
	@echo "  make ingest-history       Ingest case law for a year range. Optional: START=1926 END=2026 COURT=supreme_court"
	@echo ""
	@echo "--- Case law: Supreme Administrative Court (KHO) ---"
	@echo "  make ingest-kho           Ingest KHO case law for one year. Optional: YEAR=2026"
	@echo ""
	@echo "--- Finlex (statutes) ---"
	@echo "  make ingest-finlex       Bulk ingest Finlex statutes"
	@echo ""
	@echo "Examples:"
	@echo "  make run"
	@echo "  make ingest-precedents YEAR=2025"
	@echo "  make ingest-history COURT=supreme_court START=2020 END=2026"

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
# Case law: Supreme Court (KKO)
# ------------------------------------------------------------------------------
YEAR ?= 2026
ingest-precedents:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR)

ingest-precedents-force:
	python3 scripts/case_law/supreme_court/ingest_precedents.py --year $(YEAR) --force

ingest-rulings:
	python3 scripts/case_law/supreme_court/ingest_rulings.py --year $(YEAR)

ingest-leaves:
	python3 scripts/case_law/supreme_court/ingest_leaves.py --year $(YEAR)

ingest-kko:
	python3 scripts/case_law/supreme_court/ingest_all_subtypes.py --year $(YEAR)

START ?= 1926
END ?= 2026
COURT ?= supreme_court
ingest-history:
	python3 scripts/case_law/ingest_history.py --start $(START) --end $(END) --court $(COURT)

# ------------------------------------------------------------------------------
# Case law: Supreme Administrative Court (KHO)
# ------------------------------------------------------------------------------
ingest-kho:
	python3 scripts/case_law/supreme_administrative_court/ingest.py --year $(YEAR)

# ------------------------------------------------------------------------------
# Finlex (statutes)
# ------------------------------------------------------------------------------
ingest-finlex:
	python3 scripts/finlex_ingest/bulk_ingest.py
