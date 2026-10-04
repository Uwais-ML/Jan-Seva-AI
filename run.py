"""
Entry point to run the Jan Seva AI Voice Assistant.
"""

import sys
import logging
from pathlib import Path
from aiohttp import web

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Backend.config import HOST, PORT
from Backend.server import create_app
from RAG.Indegstion import run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def main():
    logger.info("Verifying knowledge base index...")
    run_ingestion()

    logger.info(f"Starting server on http://{HOST}:{PORT}")
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
