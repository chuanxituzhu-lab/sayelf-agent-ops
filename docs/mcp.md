# MCP 入口：让任何支持 MCP 的 Agent 调用 Sayelf Agent Ops

> 状态：已完成（2026-10-09）。基线：e0c13be。

## 0. 一句话

一个内核，多个薄入口。Codex、Claude Code、太一/OpenClaw、Cursor 等支持 MCP 的 Agent 通过本机 stdio 调用内核：按交付物分派、产出、自检、独立审核、返工、交付。**Agent 不能批准**——需要人工裁决的交付，只有你在终端里批准后，Agent 才能完成交付。

## 1. 安装（一次）

```powershell
powershell -ExecutionPolicy Bypass -File D:\Codex\skills\sayelf-agent-ops\scripts\install-mcp.ps1
```

脚本会：检查 Python 3.11+ → 安装官方 MCP Python SDK（`mcp>=1.2`）→ 试加载服务 → 在 Codex 的 `config.toml` 追加 `[mcp_servers.sayelf-agent-ops]`（先备份）→ 在 Claude Code 用户级注册。已注册的会跳过，可重复运行。完成后重启 Codex / Claude Code。

其他 Agent（太一/OpenClaw、Cursor 等）按各自的 MCP 配置填写同一条命令：

| 字段 | 值 |
|---|---|
| 传输 | stdio |
| 命令 | `python` 的完整路径 |
| 参数 | `-m sayelf_agent_ops.mcp_server` |
| 工作目录 | `D:\Codex\skills\sayelf-agent-ops`（或设置环境变量 `PYTHONPATH` 为该目录） |

## 2. 提供的工具

| 工具 | 作用 |
|---|---|
| `capabilities` | 已加载的行业包、配置的模型、人工批准方式 |
| `route_task` | 只判断该由哪个岗位、哪些技能负责，不执行 |
| `run_task` | 完整执行：路由 → 产出 → 产出者自检 → 独立审核 → 返工；结果为已交付，或停在人工裁决 |
| `get_task` | 任务状态、产出和只追加的事件日志（证据链） |
| `list_pending_approvals` | 本会话中等待人工决定的交付 |
| `deliver_task` | 你批准后完成交付；未决定返回 `AWAITING_HUMAN_APPROVAL`；被驳回则退回返工 |

默认注册媒体和土木工程行业包；`route_task` 只返回岗位建议。

**没有** approve / deny / decide 工具。

## 3. 人工批准（只在终端）

```powershell
cd D:\Codex\skills\sayelf-agent-ops
python -m sayelf_agent_ops.approve_cli list
python -m sayelf_agent_ops.approve_cli approve <请求号>
python -m sayelf_agent_ops.approve_cli deny <请求号> --reason "原因"
```

- 批准/驳回必须在交互式终端里输入确认词（`yes` / `deny`），非交互调用直接拒绝。
- 一次批准只对“这个动作 + 这个目标 + 这份产出”有效，30 分钟内用一次即失效；批准后产出被改动，交付会被拦下。
- 运行 MCP 的进程在交付时再核对一次：批准人必须是项目的人类负责人（`SAYELF_OWNER`，默认 `human.owner`）。

## 4. 可选配置（环境变量，写在 MCP 配置里）

| 变量 | 作用 | 默认 |
|---|---|---|
| `SAYELF_AGENT_OPS_HOME` | 审批记录所在目录 | `~/.sayelf/agent-ops` |
| `SAYELF_OWNER` | 唯一有权批准的人类成员 id | `human.owner` |
| `SAYELF_PACKS` | 加载的行业包，逗号分隔 | 全部 |
| `SAYELF_MODEL_ENDPOINT` / `SAYELF_MODEL_NAME` / `SAYELF_MODEL_API_KEY` | OpenAI 兼容模型；不配置则标题用本地模板、其余技能返回如实标记的占位 | 未配置 |
| `SAYELF_MODEL_ALLOW_REMOTE` | 设为 `1` 才允许调用非本机模型 | 不允许 |

也可以用 `python -m sayelf_agent_ops.model_cli configure` 写一次配置，环境变量优先。详见 [model-port.md](model-port.md)。

模型同意的差异：桌面应用是**每次运行前**确认；MCP 入口由调用方 Agent 发起，Agent 不能代你同意，所以改为由你在配置里**一次性**开启 `SAYELF_MODEL_ALLOW_REMOTE=1`。不开启时，远程模型一次都不会被调用。

## 5. 决策记录（按 sayelf-base 构建门禁）

1. 任务：让多个 Agent 共用一个内核，不复制代码、不逐个适配。
2. 最接近的已有能力：内核 Runtime、两道门、SQLite 审批存储、`scripts/route.py`、Skill 入口；官方 MCP Python SDK。
3. Step 0：**Integrate**。服务层 + 官方 SDK 薄封装；不自写协议。
4. 可度量差异：一次注册，任何 MCP 客户端可用；Agent 无法批准高风险交付。
5. 证据：`evals/test_mcp_entry.py`（S01–S10 服务与批准规则、M01–M02 真实 stdio MCP 握手），在 mcp 1.30 / 2.2 / 2.3 下均通过；未安装 mcp 时 M 系列自动跳过。全部 138 个测试通过。
6. 依赖：`mcp` 为可选依赖，只有 MCP 入口需要；内核仍为纯标准库。
7. 本地优先：只用 stdio，不开端口；审批记录在本机。
8. 回滚：删除 Codex `config.toml` 中的 `[mcp_servers.sayelf-agent-ops]`（或用安装时的备份还原），`claude mcp remove sayelf-agent-ops --scope user`。

## 6. 同时调整

- 模型适配器从 `desktop/runtime/model_provider.py` 移到 `sayelf_agent_ops/providers/openai_compatible.py`，桌面原路径保留为转出，三处入口共用一份。
- SQLite 审批存储移入内核（`sayelf_agent_ops/approvals_sqlite.py`），桌面复用同一份表结构和实现。
- `Runtime.finalize`：完成由人在别处做出的裁决；`Runtime` 可设置工作单编号前缀，避免多次会话编号重复。

## 7. 未做 / 未验证

- HTTP API：服务层已就绪，HTTP 只需一层薄封装；等 sayelf.app 需要时再加（届时必须有登录鉴权）。
- MCP 会话中的任务保存在服务进程内存里；重启 MCP 服务后，未交付的任务需要重新运行（审批记录仍在本机）。
- 未在你的 Windows 上实际运行安装脚本；Codex / Claude Code 里的实际调用未验证。
