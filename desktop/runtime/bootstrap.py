from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from sayelf_agent_ops.demo import run_first_vertical_slice
from sayelf_agent_ops.registry import build_default_registry

APP_ID = "sayelf.agent-ops"
SCHEMA = 1
VERSION = "0.1.0"
DIRECTORIES = ("workitems", "outputs", "evidence", "logs", "backups")
MESSAGES = {
    "SETUP_REQUIRED": "请选择行业包，完成首次初始化。",
    "DATA_UNAVAILABLE": "数据目录不可用，请检查目录权限或恢复备份后重试。",
    "SCHEMA_UNSUPPORTED": "数据版本与此应用不兼容，请使用匹配版本；原数据已保留。",
    "FOREIGN_DATA": "此目录包含其他应用的数据，请选择独立目录。",
    "PACK_MISMATCH": "此目录已配置另一行业包，请继续使用原配置或选择新目录。",
    "CORE_UNHEALTHY": "核心检查未通过，请重新安装应用；原数据已保留。",
    "INVALID_INPUT": "请选择个人模式以及有效行业包。",
    "INSTALL_DIRECTORY": "请将业务数据保存在程序安装目录之外。",
}


class BootstrapError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def default_data_dir(platform: str | None = None, environ=None, home=None) -> Path:
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == "win32":
        base = environ.get("LOCALAPPDATA")
        if not base:
            raise BootstrapError("DATA_UNAVAILABLE")
        return Path(base) / "Sayelf"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Sayelf"
    raise BootstrapError("INVALID_INPUT")


def data_root(path: str | Path | None) -> Path:
    root = Path(path) if path is not None else default_data_dir()
    if not root.is_absolute():
        raise BootstrapError("DATA_UNAVAILABLE")
    root = root.resolve()
    if getattr(sys, "frozen", False):
        program = Path(sys.executable).resolve().parent
        if root == program or program in root.parents:
            raise BootstrapError("INSTALL_DIRECTORY")
    return root


def _connection(root: Path, create=False):
    database = root / "runtime.sqlite3"
    # URI rw must not create a missing database during a health check.
    return sqlite3.connect(database.as_uri() + ("?mode=rwc" if create else "?mode=rw"),
                           uri=True, timeout=5)


@contextmanager
def _opened(root: Path, create=False):
    connection = _connection(root, create)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _metadata(connection):
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "metadata" not in tables:
        raise BootstrapError("FOREIGN_DATA")
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    if metadata.get("app_id") != APP_ID:
        raise BootstrapError("FOREIGN_DATA")
    if metadata.get("schema") != str(SCHEMA):
        raise BootstrapError("SCHEMA_UNSUPPORTED")
    if metadata.get("pack") not in ("media", "engineering") or metadata.get("mode") != "personal":
        raise BootstrapError("DATA_UNAVAILABLE")
    return metadata


def initialize(path=None, pack="media", mode="personal"):
    if pack not in ("media", "engineering") or mode != "personal":
        raise BootstrapError("INVALID_INPUT")
    root = data_root(path)
    root.mkdir(parents=True, exist_ok=True)
    db = root / "runtime.sqlite3"
    expected = {"runtime.sqlite3", *DIRECTORIES}
    unexpected = [entry for entry in root.iterdir() if entry.name not in expected]
    if unexpected:
        raise BootstrapError("FOREIGN_DATA")
    for name in DIRECTORIES:
        folder = root / name
        if folder.is_symlink():
            raise BootstrapError("DATA_UNAVAILABLE")
        folder.mkdir(exist_ok=True)
    if db.exists():
        with _opened(root) as connection:
            tables = list(connection.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            if tables:
                metadata = _metadata(connection)
                if metadata["pack"] != pack:
                    raise BootstrapError("PACK_MISMATCH")
    with _opened(root, create=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        tables = list(connection.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        if tables:
            metadata = _metadata(connection)
            if metadata["pack"] != pack:
                raise BootstrapError("PACK_MISMATCH")
        else:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("app_id", APP_ID), ("schema", str(SCHEMA)), ("version", VERSION),
                ("pack", pack), ("mode", mode),
            ])
    return health(root)


def health(path=None):
    root = data_root(path)
    if not (root / "runtime.sqlite3").exists():
        raise BootstrapError("SETUP_REQUIRED")
    with _opened(root) as connection:
        metadata = _metadata(connection)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BootstrapError("DATA_UNAVAILABLE")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('health_probe', 'temporary')")
        connection.rollback()
    for name in DIRECTORIES:
        folder = root / name
        if not folder.is_dir() or folder.is_symlink():
            raise BootstrapError("DATA_UNAVAILABLE")
        # Actually test write/remove, rather than relying on permission bits.
        with tempfile.TemporaryFile(dir=folder) as probe:
            probe.write(b"sayelf-health")
            probe.flush()
    registry = build_default_registry()
    wi = run_first_vertical_slice()
    if wi.state != "READY" or registry.active_roles or registry.loaded_skills:
        raise BootstrapError("CORE_UNHEALTHY")
    roles = [role.id for role in registry.roles.values() if role.industry == metadata["pack"]]
    if not roles:
        raise BootstrapError("CORE_UNHEALTHY")
    return {
        "app_id": APP_ID, "version": VERSION, "schema": SCHEMA,
        "data_dir": str(root), "mode": metadata["mode"], "pack": metadata["pack"],
        "checks": {"database": "ok", "directories": "ok", "core": "ok", "registry": "ok"},
        "roles": roles, "active_roles": 0, "loaded_skills": 0,
        "capabilities": {"executor": False, "team": False, "network_service": False},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sayelf desktop bootstrap sidecar")
    parser.add_argument("action", choices=("initialize", "health"))
    parser.add_argument("--data-dir")
    parser.add_argument("--pack", choices=("media", "engineering"), default="media")
    parser.add_argument("--mode", choices=("personal",), default="personal")
    args = parser.parse_args(argv)
    try:
        data = initialize(args.data_dir, args.pack, args.mode) if args.action == "initialize" else health(args.data_dir)
        result = {"code": 0, "msg": "本地环境已就绪。", "data": data}
    except BootstrapError as error:
        result = {"code": 10, "msg": MESSAGES[error.reason], "data": {"reason": error.reason}}
    except (OSError, sqlite3.Error, ValueError):
        result = {"code": 20, "msg": MESSAGES["DATA_UNAVAILABLE"], "data": {"reason": "DATA_UNAVAILABLE"}}
    except Exception:
        # Never expose tracebacks, user inputs, paths or environment in errors.
        result = {"code": 30, "msg": MESSAGES["CORE_UNHEALTHY"], "data": {"reason": "CORE_UNHEALTHY"}}
    print(json.dumps(result, ensure_ascii=True))
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
