"""Entrypoint so `python -m uni.webui [--host H] [--port P]` starts the dev console."""
from __future__ import annotations

import argparse

from .server import run_webui

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UNI development console (WebUI)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    run_webui(host=args.host, port=args.port)
