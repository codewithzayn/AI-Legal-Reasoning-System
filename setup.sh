#!/bin/bash
# AI Legal Reasoning System – setup (venv + dependencies)
# Run from project root.

set -e
echo "=== AI Legal Reasoning System Setup ==="

echo ""
echo "1. Checking Python..."
python3 --version

echo ""
echo "2. Creating virtual environment (.venv) if missing..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "   Created .venv"
else
    echo "   .venv already exists"
fi

echo ""
echo "3. Activating .venv and installing dependencies..."
# shellcheck source=/dev/null
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "=== Setup complete ==="
echo ""
echo "Activate the virtual environment (if not already):"
echo "  source .venv/bin/activate   # Linux/macOS"
echo ""
echo "Then run the app:"
echo "  make run"
echo "  # or: streamlit run src/ui/app.py"
echo ""
echo "See docs/ for more documentation."
