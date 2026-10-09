"""Sprint 07 — Workspace API: a local HTTP entry for product workbenches.

  python -m sayelf_agent_ops.workspace_api init --spec templates/buildcostiq-project-department.json
  python -m sayelf_agent_ops.workspace_api issue-token human.pm
  python -m sayelf_agent_ops.workspace_api serve [--port 8765] [--allow-origin http://127.0.0.1:5173]
  python -m sayelf_agent_ops.workspace_api revoke-token human.pm

Safety, by construction:

* Binds to 127.0.0.1 only. No remote access in this sprint.
* Identity comes from ``Authorization: Bearer <token>``; the body never names
  the actor. Tokens are issued per human member from an interactive terminal,
  shown once, stored only as SHA-256 hashes. Agents get no token.
* A removed member's token stops working at once (the kernel sees them inactive).
* Browser requests are accepted only from origins listed with ``--allow-origin``.
* JSON bodies only, at most 64 KiB.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .service import default_home
from .workspace import WorkspaceError, WorkspaceService, _write_json_atomic, workspace_dir

API_VERSION = "v1"
MAX_BODY = 64 * 1024
DEFAULT_PORT = 8765
LOOPBACK = "127.0.0.1"


# ---------------------------------------------------------------------------- tokens
class TokenStore:
    def __init__(self, home: Path | None = None):
        self.path = workspace_dir(home) / "tokens.json"

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue(self, member_id: str) -> str:
        token = "sao_" + secrets.token_urlsafe(32)
        data = {h: m for h, m in self._load().items() if m != member_id}  # one live token per member
        data[self._hash(token)] = member_id
        _write_json_atomic(self.path, data)
        return token

    def revoke(self, member_id: str) -> int:
        data = self._load()
        kept = {h: m for h, m in data.items() if m != member_id}
        _write_json_atomic(self.path, kept)
        return len(data) - len(kept)

    def resolve(self, token: str) -> str | None:
        digest = self._hash(token)
        for stored, member in self._load().items():
            if hmac.compare_digest(stored, digest):
                return member
        return None


# ---------------------------------------------------------------------------- routes
Route = tuple[str, "re.Pattern[str]", Callable[..., Any], int]


def _routes(service: WorkspaceService) -> list[Route]:
    def r(method: str, pattern: str, fn: Callable[..., Any], status: int = 200) -> Route:
        return method, re.compile(f"^/{API_VERSION}{pattern}$"), fn, status

    seg = r"([A-Za-z0-9._-]{1,64})"
    return [
        r("GET", "/me", lambda a, b: service.me(a)),
        r("GET", "/project", lambda a, b: service.project_view(a)),
        r("GET", "/project/events", lambda a, b: {"events": service.project_events(a)}),
        r("POST", "/members", lambda a, b: service.add_member(a, b), 201),
        r("DELETE", f"/members/{seg}", lambda a, b, m: service.remove_member(a, m)),
        r("GET", "/workitems", lambda a, b: {"workitems": service.list_workitems(a)}),
        r("POST", "/workitems", lambda a, b: service.submit(a, (b or {}).get("text")), 201),
        r("GET", f"/workitems/{seg}", lambda a, b, w: service.get_workitem(a, w)),
        r("POST", f"/workitems/{seg}/human-output",
          lambda a, b, w: service.submit_task(a, w, (b or {}).get("content"))),
        r("POST", f"/workitems/{seg}/decision",
          lambda a, b, w: service.decide(a, w, (b or {}).get("approve"), (b or {}).get("reason", ""))),
        r("GET", "/tasks", lambda a, b: {"tasks": service.my_tasks(a)}),
        r("GET", "/approvals", lambda a, b: {"approvals": service.my_approvals(a)}),
    ]


def make_handler(service: WorkspaceService, tokens: TokenStore, allowed_origins: tuple[str, ...],
                 log: bool = False):
    routes = _routes(service)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SayelfAgentOps"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:  # path only: no bodies or tokens in logs
            if log:
                sys.stderr.write("%s %s\n" % (self.command, urlsplit(self.path).path))

        # -------------------------------------------------------------- helpers
        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in allowed_origins

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin and origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, code: str) -> None:
            self._send(status, {"ok": False, "error": code})

        def _body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise WorkspaceError("BODY_TOO_LARGE", 413)
            if length == 0:
                return None
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise WorkspaceError("JSON_REQUIRED", 415)
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise WorkspaceError("INVALID_JSON") from None

        def _actor(self) -> str:
            header = self.headers.get("Authorization") or ""
            if not header.startswith("Bearer "):
                raise WorkspaceError("AUTH_REQUIRED", 401)
            member = tokens.resolve(header[7:].strip())
            if member is None:
                raise WorkspaceError("INVALID_TOKEN", 401)
            return member

        # -------------------------------------------------------------- dispatch
        def _dispatch(self, method: str) -> None:
            if not self._origin_ok():
                return self._error(403, "ORIGIN_NOT_ALLOWED")
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if method == "GET" and path == f"/{API_VERSION}/health":
                return self._send(200, {"ok": True, "api": API_VERSION})
            for route_method, pattern, fn, status in routes:
                match = pattern.match(path)
                if not match:
                    continue
                if route_method != method:
                    continue
                try:
                    actor = self._actor()
                    body = self._body() if method in ("POST", "DELETE") else None
                    if body is not None and not isinstance(body, dict):
                        raise WorkspaceError("INVALID_JSON")
                    result = fn(actor, body, *match.groups())
                except WorkspaceError as error:
                    return self._error(error.status, error.code)
                except Exception:  # never leak internals to the client
                    return self._error(500, "INTERNAL_ERROR")
                return self._send(status, {"ok": True, **result} if isinstance(result, dict)
                                  else {"ok": True, "data": result})
            if any(p.match(path) for _, p, _, _ in routes):
                return self._error(405, "METHOD_NOT_ALLOWED")
            return self._error(404, "NOT_FOUND")

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def do_OPTIONS(self) -> None:
            origin = self.headers.get("Origin")
            if not origin or origin not in allowed_origins:
                return self._error(403, "ORIGIN_NOT_ALLOWED")
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
            self.end_headers()

    return Handler


def make_server(service: WorkspaceService, tokens: TokenStore, port: int = DEFAULT_PORT,
                allowed_origins: tuple[str, ...] = (), log: bool = False) -> ThreadingHTTPServer:
    for origin in allowed_origins:
        parts = urlsplit(origin)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
            raise ValueError(f"INVALID_ORIGIN:{origin}")
    return ThreadingHTTPServer((LOOPBACK, port), make_handler(service, tokens, tuple(allowed_origins), log))


# ---------------------------------------------------------------------------- CLI
def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sayelf-workspace", description="Sayelf Agent Ops 工作区接口")
    parser.add_argument("--home", type=Path, default=None, help="数据目录（默认 ~/.sayelf/agent-ops）")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="用项目规格初始化工作区（已存在则不覆盖）")
    p_init.add_argument("--spec", type=Path, required=True)
    p_issue = sub.add_parser("issue-token", help="为一位人类成员签发访问令牌（仅限交互终端）")
    p_issue.add_argument("member_id")
    p_revoke = sub.add_parser("revoke-token", help="作废某位成员的令牌")
    p_revoke.add_argument("member_id")
    p_serve = sub.add_parser("serve", help="在 127.0.0.1 启动工作区接口")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_serve.add_argument("--allow-origin", action="append", default=[],
                         help="允许调用的工作台网页来源，例如 http://127.0.0.1:5173，可重复")
    args = parser.parse_args(argv)
    home = args.home or default_home()
    project_file = workspace_dir(home) / "project.json"

    if args.command == "init":
        if project_file.exists():
            print(f"工作区已存在，未覆盖：{project_file}")
            return 0
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        WorkspaceService(spec=spec, home=home)
        print(f"已初始化工作区：{project_file}")
        return 0

    if not project_file.exists():
        print("还没有工作区。先运行：python -m sayelf_agent_ops.workspace_api init --spec <项目规格.json>",
              file=sys.stderr)
        return 2
    service = WorkspaceService(home=home)
    tokens = TokenStore(home)

    if args.command == "issue-token":
        if not _interactive():
            print("签发令牌必须在交互终端里由人操作。", file=sys.stderr)
            return 3
        try:
            actor = service.member(args.member_id)
        except WorkspaceError as error:
            print(f"无法签发：{error.code}", file=sys.stderr)
            return 4
        confirm = input(f"为 {actor.name or actor.id}（{actor.id}）签发新令牌，旧令牌将作废。输入 yes 确认：")
        if confirm.strip() != "yes":
            print("已取消。")
            return 1
        print(tokens.issue(actor.id))
        print("令牌只显示这一次，请填入工作台的登录设置。", file=sys.stderr)
        return 0

    if args.command == "revoke-token":
        print(f"已作废 {tokens.revoke(args.member_id)} 个令牌。")
        return 0

    server = make_server(service, tokens, args.port, tuple(args.allow_origin), log=True)
    print(f"工作区接口已启动：http://{LOOPBACK}:{args.port}/{API_VERSION}/health  （Ctrl+C 停止）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
