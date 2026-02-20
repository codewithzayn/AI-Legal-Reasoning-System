"""
Pytest configuration and shared fixtures.
Run from project root: python -m pytest tests/ -v
"""

import os
import sys
from pathlib import Path

# Set env vars before any app imports (ensures deterministic test behavior)
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["REFORMULATE_ENABLED"] = "true"

# Ensure project root is on path when running tests
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
