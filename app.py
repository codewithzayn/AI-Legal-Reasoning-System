"""
Streamlit entry point for deployment (Streamlit Cloud, Railway, Render).
Deploy: streamlit run app.py

This file re-exports the main app for platforms that expect app.py at project root.
"""

import sys
from pathlib import Path

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Delegate to real app
from src.ui.app import main

if __name__ == "__main__":
    main()
