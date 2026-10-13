"""Serve the local Agent Ops workbench without a frontend dependency."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

WEB_ROOT = Path(__file__).resolve().parent / "web"
DEFAULT_API = "http://127.0.0.1:8765/v1"
LOOPBACK = "127.0.0.1"


def _valid_api(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise argparse.ArgumentTypeError(f"接口地址无效：{url}")
    return url.rstrip("/")


class ConsoleHandler(SimpleHTTPRequestHandler):
    api = DEFAULT_API

    def end_headers(self) -> None:
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(self.api))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            f"connect-src 'self' {origin}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/config.json":
            body = json.dumps({"api": self.api}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def log_message(self, fmt, *args) -> None:
        pass


def make_server(port: int, api: str) -> ThreadingHTTPServer:
    handler = type("Handler", (ConsoleHandler,), {"api": api})
    return ThreadingHTTPServer((LOOPBACK, port), partial(handler, directory=str(WEB_ROOT)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sayelf-console", description="Agent Ops 工作台")
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--api", type=_valid_api, default=DEFAULT_API, help="工作区接口地址")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        server = make_server(args.port, args.api)
    except OSError:
        print(f"端口 {args.port} 用不了，请换一个端口（例如 --port 18866）。", file=sys.stderr)
        return 2
    url = f"http://{LOOPBACK}:{args.port}/"
    print(f"Agent Ops 工作台：{url}（接口 {args.api}）")
    print(f"工作区接口需允许来源：{url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
