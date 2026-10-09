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
from urllib.parse import urlsplit

from sayelf_agent_ops.demo import run_first_vertical_slice
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.planner import MinimumPlanner, apply_routing
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.state import StateEngine, WorkState

APP_ID = "sayelf.agent-ops"
SCHEMA = 4
VERSION = "0.4.0"
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
    "MODEL_NOT_CONFIGURED": "尚未配置 AI 服务，请先填写兼容接口地址、模型名称和密钥。",
    "MODEL_CONSENT_REQUIRED": "发送需求文字前，请确认本次数据发送范围和服务地址。",
    "WORKFLOW_ROLES_REQUIRED": "请先启用内容策划、内容制作和运营增长三个角色。",
    "WORKFLOW_INVALID": "内容工作流无法继续，请检查输入和工作空间状态。",
    "WORKFLOW_ALREADY_RUNNING": "这项内容任务正在处理中，请稍后刷新任务记录。",
    "WORKFLOW_INTERRUPTED": "上次运行中断；已保留完成步骤，可以确认后继续。",
    "WORKFLOW_CHECKPOINT_INVALID": "已保存的阶段结果校验失败，已停止生成并保留本机记录；请检查工作空间。",
    "MODEL_UNAVAILABLE": "模型服务暂时不可用；已保留已完成步骤，可以检查网络后继续。",
    "MODEL_RATE_LIMITED": "模型服务请求频率受限；请稍后再试。",
    "MODEL_REJECTED_REQUEST": "模型服务拒绝了请求；请检查接口地址、模型和服务配置。",
    "MODEL_RESPONSE_INVALID": "模型返回内容未通过结构校验；请检查模型兼容性后重试。",
    "MODEL_RESPONSE_TOO_LARGE": "模型返回内容过大，已拒绝保存。",
    "MODEL_INPUT_TOO_LARGE": "本次材料过长，请减少附件或缩短需求后再试。",
    "UNROUTABLE_DELIVERABLE": "这项需求不属于当前行业包，或没有说清要交付什么；请补充要交付的成果（如标题、文章、配图、发布稿）。",
    "MODEL_CALL_FAILED": "模型调用失败；请检查服务配置后重试。",
    "OUTLINE_MISSING": "内容大纲没有生成，脚本步骤已停下；请重试。",
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
    registry = build_registry((pack,))
    connection.executemany(
        "INSERT OR IGNORE INTO role_activation (role_id, pack, active, updated_at) VALUES (?, ?, 0, ?)",
        [(role.id, pack, now) for role in registry.roles.values() if role.industry == pack],
    )


def _create_execution_tables(connection):
    statements = (
        """CREATE TABLE IF NOT EXISTS ai_provider (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            endpoint TEXT NOT NULL,
            model TEXT NOT NULL,
            timeout_seconds INTEGER NOT NULL DEFAULT 90,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS workflow_runs (
            run_id TEXT PRIMARY KEY,
            workitem_id TEXT NOT NULL,
            state TEXT NOT NULL,
            current_step TEXT,
            endpoint TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS workflow_runs_workitem ON workflow_runs(workitem_id, created_at)",
        """CREATE TABLE IF NOT EXISTS workflow_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            step TEXT,
            state TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
        )""",
        """CREATE TABLE IF NOT EXISTS workflow_stages (
            run_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            output_json TEXT NOT NULL,
            output_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(run_id, stage),
            FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
        )""",
        """CREATE TABLE IF NOT EXISTS workflow_results (
            workitem_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            content_json TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            review_state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workitem_id, version),
            FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
        )""",
        """CREATE TABLE IF NOT EXISTS workflow_approvals (
            workitem_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            decision TEXT NOT NULL,
            actor TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(workitem_id, version),
            FOREIGN KEY(workitem_id, version)
                REFERENCES workflow_results(workitem_id, version)
        )""",
        """CREATE TABLE IF NOT EXISTS performance_reviews (
            review_id TEXT PRIMARY KEY,
            workitem_id TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
    )
    for statement in statements:
        connection.execute(statement)


def _create_gate_tables(connection):
    # Single schema definition shared with the kernel store.
    from sayelf_agent_ops.approvals_sqlite import create_gate_tables

    create_gate_tables(connection)


def _backup_before_migration(connection, root, source_schema):
    folder = root / "backups"
    if not folder.is_dir() or folder.is_symlink():
        raise BootstrapError("DATA_UNAVAILABLE")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = folder / f"runtime-schema-{source_schema}-{stamp}.sqlite3"
    suffix = 1
    while destination.exists():
        destination = folder / f"runtime-schema-{source_schema}-{stamp}-{suffix}.sqlite3"
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
    while schema < SCHEMA:
        _backup_before_migration(connection, root, schema)
        connection.execute("BEGIN IMMEDIATE")
        try:
            if schema == 1:
                _create_role_activation_table(connection, metadata["pack"])
            elif schema == 2:
                _create_execution_tables(connection)
            elif schema == 3:
                _create_gate_tables(connection)
            else:
                raise BootstrapError("SCHEMA_UNSUPPORTED")
            schema += 1
            connection.execute("UPDATE metadata SET value=? WHERE key='schema'", (str(schema),))
            connection.execute("UPDATE metadata SET value=? WHERE key='version'", (VERSION,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        metadata = _raw_metadata(connection)
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    required_tables = {
        "role_activation", "ai_provider", "workflow_runs", "workflow_events",
        "workflow_stages", "workflow_results", "workflow_approvals", "performance_reviews",
        "gate_approvals",
    }
    if metadata.get("schema") != str(SCHEMA) or not required_tables.issubset(tables):
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
            _create_execution_tables(connection)
            _create_gate_tables(connection)
    return health(root)


def health(path=None):
    root = data_root(path)
    if not (root / "runtime.sqlite3").exists():
        raise BootstrapError("SETUP_REQUIRED")
    with _opened(root) as connection:
        metadata = _ensure_current_schema(connection, root)
        provider_configured = _provider_configured(connection)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BootstrapError("DATA_UNAVAILABLE")
        registry = _activate_registered_roles(
            connection, build_registry((metadata["pack"],)), metadata["pack"]
        )
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
            "executor": True, "team": False, "network_service": False,
            "local_file_intake": True, "pdf_text_extraction": True,
            "image_ocr": True, "workplan_export": True,
            "workflow_runs": True, "provider_configured": provider_configured,
        },
    }


def _provider_configured(connection):
    row = connection.execute(
        "SELECT endpoint, model FROM ai_provider WHERE id=1"
    ).fetchone()
    return bool(row and row[0] and row[1])


def provider_status(path):
    status = health(path)
    root = data_root(status["data_dir"])
    with _opened(root) as connection:
        row = connection.execute(
            "SELECT endpoint, model, timeout_seconds FROM ai_provider WHERE id=1"
        ).fetchone()
    if not row:
        return {"configured": False, "endpoint": "", "model": "", "timeout_seconds": 90}
    return {
        "configured": True,
        "endpoint": row[0],
        "model": row[1],
        "timeout_seconds": row[2],
    }


def configure_provider(path, endpoint, model):
    if not isinstance(endpoint, str) or not isinstance(model, str):
        raise BootstrapError("INVALID_INPUT")
    endpoint = endpoint.strip().rstrip("/")
    model = model.strip()
    if len(endpoint) > 2048 or len(model) > 200 or not model:
        raise BootstrapError("INVALID_INPUT")
    parsed = urlsplit(endpoint)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts)
    ) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BootstrapError("INVALID_INPUT")
    status = health(path)
    root = data_root(status["data_dir"])
    with _opened(root) as connection:
        connection.execute(
            "INSERT INTO ai_provider (id, endpoint, model, timeout_seconds, updated_at) "
            "VALUES (1, ?, ?, 90, ?) "
            "ON CONFLICT(id) DO UPDATE SET endpoint=excluded.endpoint, model=excluded.model, "
            "timeout_seconds=excluded.timeout_seconds, updated_at=excluded.updated_at",
            (endpoint, model, datetime.now(timezone.utc).isoformat()),
        )
    return provider_status(root)


def set_role_active(path, role_id, active):
    if not isinstance(active, bool) or not isinstance(role_id, str):
        raise BootstrapError("INVALID_INPUT")
    status = health(path)
    root = data_root(status["data_dir"])
    registry = build_registry((status["pack"],))
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
    selected_roles = tuple(dict.fromkeys(
        role_id for role_id, _ in decision.workflow_steps
    )) or (decision.selected_role,)
    return {
        "industry": decision.industry,
        "deliverable_type": decision.deliverable_type,
        "requested_deliverables": list(decision.requested_deliverables or (decision.deliverable_type,)),
        "deliverable_level": decision.deliverable_level,
        "selected_role": decision.selected_role,
        "role_name": role.name,
        "selected_roles": list(selected_roles),
        "role_count": len(selected_roles),
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
        f"- 本次最少岗位数：{routing['role_count']}",
        f"- 完整交付要求：{', '.join(routing['requested_deliverables'])}",
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
        lines.append(f"{step['step']}. **{step['role']} · {step['skill']}**：产出 `{step['output']}`；完成条件：`{step['done_when']}`。")
    lines.extend([
        "",
        "## 完成说明",
        "",
        "每个步骤必须生成其声明的成果并通过技能契约校验；整单须覆盖以上全部交付要求，经独立审核后方可闭环。",
        "",
        "这份文件是本机生成的分工方案，状态为已规划，尚未执行。配置 AI 服务后可生成实际岗位成果；外部模型调用需逐次确认。",
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
        registry = _activate_registered_roles(
            connection, build_registry((metadata["pack"],)), metadata["pack"]
        )
    try:
        decision = Router(registry).route(wi)
    except ValueError as error:
        if str(error) != "UNROUTABLE_DELIVERABLE":
            raise
        # 只加载本工作空间的行业包；不属于它、或交付物不明确的需求在此说明，不硬套岗位。
        raise BootstrapError("UNROUTABLE_DELIVERABLE") from None
    routing = _routing_data(decision, registry)
    execution_plan = MinimumPlanner(registry).build(wi, decision)
    required_roles = tuple(dict.fromkeys(step.role for step in execution_plan.steps))
    missing_roles = [role_id for role_id in required_roles if role_id not in registry.active_role_ids]
    if missing_roles:
        return {
            "code": 11,
            "msg": MESSAGES["ROLE_NOT_ACTIVE"],
            "data": {
                "reason": "ROLE_NOT_ACTIVE",
                "workitem_id": workitem_id,
                "required_role_id": missing_roles[0] if len(missing_roles) == 1 else None,
                "missing_role_ids": missing_roles,
                "routing": routing,
                "roles": _role_details(registry, metadata["pack"]),
            },
        }
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
    parser.add_argument("action", choices=(
        "initialize", "health", "set-role", "plan", "provider-config",
        "provider-status", "provider-clear", "provider-test", "execute-media", "approve-export",
        "performance-review", "recent-workflows", "saved-media-result", "kernel-run",
    ))
    parser.add_argument("--data-dir")
    parser.add_argument("--pack", choices=("media", "engineering"), default="media")
    parser.add_argument("--mode", choices=("personal",), default="personal")
    parser.add_argument("--role-id")
    parser.add_argument("--active", choices=("true", "false"))
    parser.add_argument("--request-file")
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--workitem-id")
    parser.add_argument("--content-file")
    parser.add_argument("--metrics-file")
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--run-id")
    parser.add_argument("--version", type=int)
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
        elif args.action == "provider-config":
            data = configure_provider(args.data_dir, args.endpoint, args.model)
            result = {"code": 0, "msg": "AI 服务地址与模型已保存；密钥由桌面端单独保管。", "data": data}
        elif args.action == "provider-status":
            data = provider_status(args.data_dir)
            result = {"code": 0, "msg": "AI 服务配置已读取。", "data": data}
        elif args.action == "provider-clear":
            root = data_root(args.data_dir)
            health(root)
            with _opened(root) as connection:
                connection.execute("DELETE FROM ai_provider WHERE id=1")
            result = {"code": 0, "msg": "AI 服务配置已清除。", "data": {"configured": False}}
        elif args.action in {"provider-test", "execute-media", "kernel-run"}:
            from desktop.runtime.media_workflow import execute_media_workflow, test_provider
            from desktop.runtime.model_provider import OpenAICompatibleProvider

            config = provider_status(args.data_dir)
            api_key = os.environ.get("SAYELF_MODEL_API_KEY", "")
            if not config["configured"] or not api_key:
                raise BootstrapError("MODEL_NOT_CONFIGURED")
            provider = OpenAICompatibleProvider(
                config["endpoint"], config["model"], api_key, config["timeout_seconds"]
            )
            if args.action == "kernel-run":
                from desktop.runtime.kernel_tasks import run_kernel_task

                if not args.workitem_id:
                    raise BootstrapError("WORKFLOW_INVALID")
                result = run_kernel_task(args.data_dir, args.workitem_id, provider,
                                         allow_external=args.allow_external)
            elif args.action == "provider-test":
                try:
                    data = test_provider(provider)
                    result = {"code": 0, "msg": data["message"], "data": data}
                except Exception as error:
                    reason = getattr(error, "code", "MODEL_UNAVAILABLE")
                    result = {
                        "code": 20,
                        "msg": MESSAGES.get(reason, "模型服务测试失败，请检查配置后重试。"),
                        "data": {"reason": reason},
                    }
            else:
                if not args.workitem_id:
                    raise BootstrapError("WORKFLOW_INVALID")
                result = execute_media_workflow(
                    args.data_dir, args.workitem_id, provider,
                    allow_external=args.allow_external, resume_run_id=args.resume_run_id,
                )
        elif args.action == "recent-workflows":
            from desktop.runtime.media_workflow import recent_media_workflows

            items = recent_media_workflows(args.data_dir)
            result = {"code": 0, "msg": "本机任务记录已读取。", "data": {"items": items}}
        elif args.action == "saved-media-result":
            from desktop.runtime.media_workflow import load_saved_media_result

            if not args.workitem_id or not args.run_id:
                raise BootstrapError("WORKFLOW_INVALID")
            data = load_saved_media_result(args.data_dir, args.workitem_id, args.run_id)
            result = {"code": 0, "msg": "本机成果已读取。", "data": data}
        elif args.action == "approve-export":
            from desktop.runtime.media_workflow import approve_and_export

            workitem_id = _validate_workitem_id(args.workitem_id)
            root = data_root(args.data_dir)
            expected = root / "workitems" / workitem_id / "review-current.md"
            supplied = Path(args.content_file or "")
            if supplied.is_symlink() or supplied.resolve(strict=True) != expected.resolve(strict=True):
                raise BootstrapError("WORKFLOW_INVALID")
            if args.version is None or args.version < 1:
                raise BootstrapError("WORKFLOW_INVALID")
            content = supplied.read_text(encoding="utf-8")
            result = approve_and_export(root, workitem_id, content, version=args.version)
        elif args.action == "performance-review":
            from desktop.runtime.media_workflow import record_performance_review

            workitem_id = _validate_workitem_id(args.workitem_id)
            root = data_root(args.data_dir)
            expected = root / "workitems" / workitem_id / "performance-current.json"
            supplied = Path(args.metrics_file or "")
            if supplied.is_symlink() or supplied.resolve(strict=True) != expected.resolve(strict=True):
                raise BootstrapError("WORKFLOW_INVALID")
            metrics = json.loads(supplied.read_text(encoding="utf-8"))
            result = record_performance_review(root, workitem_id, metrics)
        else:
            if args.request_file is None:
                raise BootstrapError("INVALID_WORKITEM")
            result = create_workplan(args.data_dir, args.request_file)
    except BootstrapError as error:
        result = {"code": 10, "msg": MESSAGES[error.reason], "data": {"reason": error.reason}}
    except (OSError, sqlite3.Error, ValueError):
        result = {"code": 20, "msg": MESSAGES["DATA_UNAVAILABLE"], "data": {"reason": "DATA_UNAVAILABLE"}}
    except Exception as error:
        # Never expose tracebacks, user inputs, paths or environment in errors.
        reason = getattr(error, "code", "CORE_UNHEALTHY")
        result = {
            "code": 20 if reason.startswith("MODEL_") else 30,
            "msg": MESSAGES.get(reason, MESSAGES["CORE_UNHEALTHY"]),
            "data": {"reason": reason},
        }
    print(json.dumps(result, ensure_ascii=True))
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
