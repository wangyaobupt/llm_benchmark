"""Minimal static HTTP server for the real-time progress monitor.

Serves ``data/phenotype/`` (the progress JSON files) and the monitor HTML so the
browser can ``fetch`` progress snapshots (``file://`` fetch is blocked).

Usage:
    .\\.venv\\Scripts\\python.exe data_pipeline\\archived\\phenotype\\serve_progress.py [--port 8766]
"""
from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT / "docs" / "reports" / "progress_monitor.html"
SERVE_DIR = ROOT / "data" / "phenotype"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SERVE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args(argv)

    if not HTML.exists():
        print(f"WARN: monitor HTML not found: {HTML}", file=sys.stderr)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"serving {SERVE_DIR} at http://127.0.0.1:{args.port}/progress/")
    print(f"monitor HTML: {HTML} (open it directly, or copy into Preview)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
