"""Start the web interface.

Run:  python -m src.serve
"""

from __future__ import annotations

import argparse
import logging
import webbrowser

import uvicorn

from . import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Pawprint interface.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    url = f"http://{args.host}:{args.port}"
    print(f"\nPawprint-Local — {url}")
    print(f"Models: {config.CHAT_MODEL_ALIAS} + {config.EMBEDDING_MODEL_ALIAS}")
    print("Everything runs on this machine. Ctrl+C to stop.\n")

    if not args.no_browser:
        webbrowser.open(url)

    uvicorn.run(
        "src.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
