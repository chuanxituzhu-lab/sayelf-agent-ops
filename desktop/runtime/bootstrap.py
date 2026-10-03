from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

from sayelf_agent_ops.demo import run_first_vertical_slice
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.planner import MinimumPlanner, apply_routing
from sayelf_agent_ops.registry import build_default_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.state import StateEngine, WorkState

APP_ID = "sayelf.agent-ops"
SCHEMA = 2
VERSION = "0.2.0"
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
    "ROLE_NOT_ACTIVE": "请先激活建议角色，再生成工作方案。",
    "INVALID_WORKITEM": "工作单或附件无效，请重新录入后再试。",
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


def _raw_metadata(connection):
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "metadata" not in tables:
        raise BootstrapError("FOREIGN_DATA")
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    if metadata.get("app_id") != APP_ID:
        raise BootstrapError("FOREIGN_DATA")
    try:
        schema = int(metadata.get("schema", "0"))
    except ValueError:
        raise BootstrapError("SCHEMA_UNSUPPORTED") from None
    if schema < 1 or schema > SCHEMA:
        raise BootstrapError("SCHEMA_UNSUPPORTED")
    if metadata.get("pack") not in ("media", "engineering") or metadata.get("mode") != "personal":
        raise BootstrapError("DATA_UNAVAILABLE")
    return metadata


def _create_role_activation_table(connection, pack):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS role_activation (
            role_id TEXT PRIMARY KEY,
            pack TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
            updated_at TEXT NOT NULL
        )
    """)
    now = datetime.now(timezone.utc).isoformat()
    registry = build_default_registry()
    connection.executemany(
        "INSERT OR IGNORE INTO role_activation (role_id, pack, active, updated_at) VALUES (?, ?, 0, ?)",
        [(role.id, pack, now) for role in registry.roles.values() if role.industry == pack],
    )


def _backup_before_migration(connection, root):
    folder = root / "backups"
    if not folder.is_dir() or folder.is_symlink():
        raise BootstrapError("DATA_UNAVAILABLE")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = folder / f"runtime-schema-1-{stamp}.sqlite3"
    suffix = 1
    while destination.exists():
        destination = folder / f"runtime-schema-1-{stamp}-{suffix}.sqlite3"
        suffix += 1
    backup = None
    try:
        backup = sqlite3.connect(destination)
        connection.backup(backup)
        backup.close()
        backup = None
    except sqlite3.Error:
        if backup is not None:
            backup.close()
        destination.unlink(missing_ok=True)
        raise BootstrapError("DATA_UNAVAILABLE") from None
    return destination


def _ensure_current_schema(connection, root):
    metadata = _raw_metadata(connection)
    schema = int(metadata["schema"])
    if schema == 1:
        _backup_before_migration(connection, root)
        connection.execute("BEGIN IMMEDIATE")
        try:
            _create_role_activation_table(connection, metadata["pack"])
            connection.execute("UPDATE metadata SET value=? WHERE key='schema'", (str(SCHEMA),))
            connection.execute("UPDATE metadata SET value=? WHERE key='version'", (VERSION,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        metadata = _raw_metadata(connection)
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if metadata.get("schema") != str(SCHEMA) or "role_activation" not in tables:
        raise BootstrapError("SCHEMA_UNSUPPORTED")
    return metadata


def _activate_registered_roles(connection, registry, pack):
    rows = connection.execute(
        "SELECT role_id, active FROM role_activation WHERE pack=?", (pack,)
    ).fetchall()
    known = {role_id for role_id, _ in rows}
    expected = {role.id for role in registry.roles.values() if role.industry == pack}
    if known != expected:
        raise BootstrapError("CORE_UNHEALTHY")
    for role_id, active in rows:
        if active:
            registry.activate_role(role_id)
    return registry


def _role_details(registry, pack):
    return [
        {
            "id": role.id,
            "name": role.name,
            "responsibility": role.responsibility,
            "active": role.id in registry.active_role_ids,
        }
        for role in registry.roles.values()
        if role.industry == pack
    ]


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
                metadata = _raw_metadata(connection)
                if metadata["pack"] != pack:
                    raise BootstrapError("PACK_MISMATCH")
    with _opened(root, create=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        tables = list(connection.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        if tables:
            metadata = _raw_metadata(connection)
            if metadata["pack"] != pack:
                raise BootstrapError("PACK_MISMATCH")
            connection.commit()
            _ensure_current_schema(connection, root)
        else:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("app_id", APP_ID), ("schema", str(SCHEMA)), ("version", VERSION),
                ("pack", pack), ("mode", mode),
            ])
            _create_role_activation_table(connection, pack)
    return health(root)


def health(path=None):
    root = data_root(path)
    if not (root / "runtime.sqlite3").exists():
        raise BootstrapError("SETUP_REQUIRED")
    with _opened(root) as connection:
        metadata = _ensure_current_schema(connection, root)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BootstrapError("DATA_UNAVAILABLE")
        registry = _activate_registered_roles(connection, build_default_registry(), metadata["pack"])
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
    wi = run_first_vertical_slice()
    if wi.state != "READY" or registry.loaded_skills:
        raise BootstrapError("CORE_UNHEALTHY")
    roles = _role_details(registry, metadata["pack"])
    if not roles:
        raise BootstrapError("CORE_UNHEALTHY")
    return {
        "app_id": APP_ID, "version": VERSION, "schema": SCHEMA,
        "data_dir": str(root), "mode": metadata["mode"], "pack": metadata["pack"],
        "checks": {"database": "ok", "directories": "ok", "core": "ok", "registry": "ok"},
        "roles": roles, "active_roles": registry.active_roles, "loaded_skills": 0,
        "capabilities": {
            "executor": False, "team": False, "network_service": False,
            "local_file_intake": True, "pdf_text_extraction": True,
            "image_ocr": True, "workplan_export": True,
        },
    }


def set_role_active(path, role_id, active):
    if not isinstance(active, bool) or not isinstance(role_id, str):
        raise BootstrapError("INVALID_INPUT")
    status = health(path)
    root = data_root(status["data_dir"])
    registry = build_default_registry()
    role = registry.roles.get(role_id)
    if role is None or role.industry != status["pack"]:
        raise BootstrapError("INVALID_INPUT")
    if active:
        registry.activate_role(role_id)
    else:
        registry.deactivate_role(role_id)
    with _opened(root) as connection:
        connection.execute(
            "UPDATE role_activation SET active=?, updated_at=? WHERE role_id=? AND pack=?",
            (int(active), datetime.now(timezone.utc).isoformat(), role_id, status["pack"]),
        )
        if connection.total_changes < 1:
            raise BootstrapError("CORE_UNHEALTHY")
    return health(root)


def _validate_workitem_id(workitem_id):
    if not isinstance(workitem_id, str) or not re.fullmatch(r"WI-[A-Za-z0-9_-]{1,64}", workitem_id):
        raise BootstrapError("INVALID_WORKITEM")
    return workitem_id


def _load_workitem_request(root, request_file):
    source_path = Path(request_file)
    if source_path.is_symlink():
        raise BootstrapError("INVALID_WORKITEM")
    path = source_path.resolve(strict=True)
    workitems_root = (root / "workitems").resolve(strict=True)
    if path.name != "request.json" or path.parent.parent != workitems_root or path.is_symlink():
        raise BootstrapError("INVALID_WORKITEM")
    with path.open("r", encoding="utf-8") as source:
        request = json.load(source)
    workitem_id = _validate_workitem_id(request.get("id"))
    if path.parent.name != workitem_id:
        raise BootstrapError("INVALID_WORKITEM")
    if not isinstance(request.get("request"), str) or not request["request"].strip():
        raise BootstrapError("INVALID_WORKITEM")
    if len(request["request"]) > 20000:
        raise BootstrapError("INVALID_WORKITEM")
    attachments = request.get("attachments", [])
    if not isinstance(attachments, list) or len(attachments) > 5:
        raise BootstrapError("INVALID_WORKITEM")
    extracted_chars = 0
    for attachment in attachments:
        relative = Path(attachment.get("relative_path", ""))
        expected_parent = Path("evidence") / workitem_id
        if relative.is_absolute() or relative.parent != expected_parent or not relative.name:
            raise BootstrapError("INVALID_WORKITEM")
        evidence_root = (root / expected_parent).resolve(strict=True)
        evidence_path = (root / relative).resolve(strict=True)
        if evidence_path.parent != evidence_root or not evidence_path.is_file():
            raise BootstrapError("INVALID_WORKITEM")
        extracted_text = attachment.get("extracted_text", "")
        if not isinstance(extracted_text, str):
            raise BootstrapError("INVALID_WORKITEM")
        extracted_chars += len(extracted_text)
        if extracted_chars > 60000:
            raise BootstrapError("INVALID_WORKITEM")
    return request


def _routing_data(decision, registry):
    role = registry.roles[decision.selected_role]
    return {
        "industry": decision.industry,
        "deliverable_type": decision.deliverable_type,
        "deliverable_level": decision.deliverable_level,
        "selected_role": decision.selected_role,
        "role_name": role.name,
        "responsibility": role.responsibility,
        "selected_skills": list(decision.selected_skills),
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def _render_workplan(workitem_id, request, routing, steps):
    channel = request.get("channel") or "未指定"
    lines = [
        "# Sayelf Agent Ops 工作方案",
        "",
        f"- 工作单：`{workitem_id}`",
        "- 当前状态：已规划（尚未执行）",
        f"- 目标平台：{channel}",
        f"- 交付类型：{routing['deliverable_type']}",
        "",
        "## 需求",
        "",
        request["request"].strip(),
        "",
        "## 输入材料",
        "",
    ]
    attachments = request.get("attachments", [])
    if not attachments:
        lines.append("本次没有附加文件。")
    for attachment in attachments:
        lines.extend([f"### {attachment['name']}", "", f"识别状态：{attachment.get('extraction_status', '未识别')}", ""])
        extracted_text = attachment.get("extracted_text", "").strip()
        if extracted_text:
            lines.extend([extracted_text[:12000], ""])
        else:
            lines.extend(["未提取到可用文字；原始文件仍保存在本机证据目录。", ""])
    lines.extend([
        "## 路由结果",
        "",
        f"- 建议角色：{routing['role_name']} (`{routing['selected_role']}`)",
        f"- 角色职责：{routing['responsibility']}",
        f"- 路由依据：{routing['reason']}",
        f"- 技能：{', '.join(routing['selected_skills'])}",
        "",
        "## 工作步骤",
        "",
    ])
    for step in steps:
        lines.append(f"{step['step']}. **{step['skill']}**：产出 `{step['output']}`；完成条件：`{step['done_when']}`。")
    lines.extend([
        "",
        "## 完成说明",
        "",
        "这份文件是本机生成的路由与执行方案。当前版本没有连接 AI 内容执行器，也没有自动发布到平台；请人工审核后再使用。",
        "",
    ])
    return "\n".join(lines)


def create_workplan(path, request_file):
    status = health(path)
    root = data_root(status["data_dir"])
    request = _load_workitem_request(root, request_file)
    workitem_id = request["id"]
    platform = request.get("channel", "")
    extracted = "\n".join(
        f"\n材料《{entry['name']}》识别文字：\n{entry.get('extracted_text', '')}"
        for entry in request.get("attachments", [])
        if entry.get("extracted_text")
    )
    routing_input = "\n".join((platform, request["request"], extracted))
    wi = WorkItem(
        id=workitem_id,
        input=routing_input,
        goal=request["request"],
        deliverable=f"{platform}内容方案",
        industry=status["pack"],
    )
    engine = StateEngine()
    engine.transition(wi, WorkState.SCOPED)
    with _opened(root) as connection:
        metadata = _ensure_current_schema(connection, root)
        registry = _activate_registered_roles(connection, build_default_registry(), metadata["pack"])
    decision = Router(registry).route(wi)
    routing = _routing_data(decision, registry)
    if decision.selected_role not in registry.active_role_ids:
        return {
            "code": 11,
            "msg": MESSAGES["ROLE_NOT_ACTIVE"],
            "data": {
                "reason": "ROLE_NOT_ACTIVE",
                "workitem_id": workitem_id,
                "required_role_id": decision.selected_role,
                "routing": routing,
                "roles": _role_details(registry, metadata["pack"]),
            },
        }
    execution_plan = MinimumPlanner().build(wi, decision)
    apply_routing(wi, decision, execution_plan)
    steps = [
        {
            "step": item.step,
            "role": item.role,
            "skill": item.skill,
            "output": item.output,
            "done_when": item.done_when,
        }
        for item in execution_plan.steps
    ]
    content = _render_workplan(workitem_id, request, routing, steps)
    workitem_folder = root / "workitems" / workitem_id
    output_path = root / "outputs" / f"{workitem_id}.md"
    (workitem_folder / "plan.json").write_text(json.dumps({
        "workitem_id": workitem_id,
        "state": "planned",
        "routing": routing,
        "steps": steps,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.write_text(content, encoding="utf-8")
    return {
        "code": 0,
        "msg": "工作方案已保存到本机成果目录。",
        "data": {
            "workitem_id": workitem_id,
            "state": "planned",
            "routing": routing,
            "steps": steps,
            "result_content": content,
            "output_name": output_path.name,
            "roles": _role_details(registry, metadata["pack"]),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sayelf desktop bootstrap sidecar")
    parser.add_argument("action", choices=("initialize", "health", "set-role", "plan"))
    parser.add_argument("--data-dir")
    parser.add_argument("--pack", choices=("media", "engineering"), default="media")
    parser.add_argument("--mode", choices=("personal",), default="personal")
    parser.add_argument("--role-id")
    parser.add_argument("--active", choices=("true", "false"))
    parser.add_argument("--request-file")
    args = parser.parse_args(argv)
    try:
        if args.action == "initialize":
            data = initialize(args.data_dir, args.pack, args.mode)
            result = {"code": 0, "msg": "本地环境已就绪。", "data": data}
        elif args.action == "health":
            data = health(args.data_dir)
            result = {"code": 0, "msg": "本地环境已就绪。", "data": data}
        elif args.action == "set-role":
            if args.role_id is None or args.active is None:
                raise BootstrapError("INVALID_INPUT")
            data = set_role_active(args.data_dir, args.role_id, args.active == "true")
            result = {"code": 0, "msg": "角色状态已更新。", "data": data}
        else:
            if args.request_file is None:
                raise BootstrapError("INVALID_WORKITEM")
            result = create_workplan(args.data_dir, args.request_file)
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
