"""
Pytest configuration and shared fixtures.
Run from project root: python -m pytest tests/ -v
"""

import sys
from pathlib import Path

# Ensure project root is on path when running tests
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
