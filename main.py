#!/usr/bin/env python3
"""
AI Legal Reasoning System - Main Entry Point

Usage:
    python main.py          # Run Streamlit UI (default)
    python main.py --cli    # Run CLI mode (interactive)
"""

import asyncio
import contextlib
import subprocess
import sys
from pathlib import Path

from src.config.logging_config import logger

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.stream import stream_query_response


def run_streamlit():
    """Launch the Streamlit web interface"""
    app_path = PROJECT_ROOT / "src" / "ui" / "app.py"
    subprocess.run(["streamlit", "run", str(app_path)], check=True)


async def run_cli_async():
    """Run interactive CLI mode (Async)"""
    logger.info("=" * 60)
    logger.info("🇫🇮 AI Legal Reasoning System - CLI Mode")
    logger.info("=" * 60)
    logger.info("Type your legal questions. Type 'exit' to quit.\n")

    while True:
        try:
            # Use asyncio.to_thread for blocking input if needed, but input() is blocking main thread anyway.
            # Simple input() is fine for CLI demo.
            print("You: ", end="", flush=True)
            query = await asyncio.to_thread(sys.stdin.readline)
            query = query.strip()

            if query.lower() in ("exit", "quit", "q"):
                logger.info("Goodbye!")
                break
            if not query:
                continue
            logger.info("\nAssistant: ")
            async for chunk in stream_query_response(query):
                print(chunk, end="", flush=True)
            logger.info("\n")
        except KeyboardInterrupt:
            logger.info("\nGoodbye!")
            break


def run_cli():
    """Wrapper for async CLI"""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_cli_async())


def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        run_cli()
    else:
        run_streamlit()


if __name__ == "__main__":
    main()
