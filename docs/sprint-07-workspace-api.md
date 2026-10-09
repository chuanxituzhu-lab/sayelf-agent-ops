# Sprint 07：工作区接口（Workspace API）与生产负责人

> 状态：完成。基线 `1f096da`，Python 测试 178 个全绿（新增 18 个）。

## 0. 先定位置：Agent Ops 是引擎，不是某个行业的界面

| 问题 | 决定 |
|---|---|
| Agent Ops 是否独立 | 独立。它是内核加入口（路由、执行、自检、复核、人工裁决、证据链），不绑定任何行业界面。 |
| 单人和团队是否两套工作台 | 不是。同一个运行时，项目里有几个人、什么规则，决定表现成单人还是团队。Agent Ops 自带的桌面端是单人参考工作台（自媒体 MVP）。 |
| BuildCostIQ 用谁的界面 | 用自己的：**BuildCostIQ 工作台**，背后连 Agent Ops。界面按造价业务设计（清单、图纸、进度、联签），团队能力全部来自 Agent Ops。 |
| 标准是什么 | 标准是**接口契约**，不是某个界面。哪个产品接入，都调同一组接口。 |
| 为什么不用 MCP 接 BuildCostIQ | MCP 是给 AI 工具用的，故意不能审批。产品工作台要让人提交、让人批准，所以另开一个口：工作区接口，人用自己的令牌登录。 |
| 为什么不做“Agent Ops 团队工作台（BuildCostIQ）” | 会把造价界面塞进共享底座，以后图纸动画、自媒体等产品都要往里塞，底座就不再是底座。 |

```text
BuildCostIQ 工作台（造价界面）     其他产品工作台（以后）
          │  工作区接口：人，带令牌，可提交、可裁决
          ▼
   ┌──────────── Sayelf Agent Ops 内核 ────────────┐
   │ 路由 · 最少岗位 · 执行 · 自检 · 独立复核 · 联签 │
   └────────────────────────────────────────────────┘
          ▲  MCP：AI 工具，可路由、可执行，不能裁决
Claude Code / Codex / Cursor / WorkBuddy …
```

## 1. 生产负责人

| 项 | 内容 |
|---|---|
| 成员 | `human.prod-lead`，名称“生产负责人”，角色 `production-lead` |
| 新增路由 | “形象进度”，或“进度”加“跟踪/滞后/偏差/核对/检查/复盘/周报/月报/计划” → `progress-review`，岗位 `engineering.production`（Agent 先出核查结果）。“进度款”不走这条。 |
| 进度放行 `progress-release` | 生产负责人 + 项目经理联签 |
| 工程量放行 `quantity-release` | 生产负责人 + 造价负责人联签 |
| 不变 | 造价放行仍是造价负责人 + 项目经理；对外发布仍由所有者批准 |

生产负责人只持有审批角色，不持有 `engineering.production`，所以进度核查由 Agent 起草、生产负责人把关。如果要他亲自出核查结果，给他加上 `engineering.production` 角色即可，那一步会自动变成他的人工任务。

## 2. 接口

只监听 `127.0.0.1`。除 `/v1/health` 外都要 `Authorization: Bearer <令牌>`，身份只看令牌，请求体里写谁都无效。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/health` | 存活检查 |
| GET | `/v1/me` | 我是谁 |
| GET | `/v1/project` | 成员（人和 Agent，含在岗状态）、审批规则 |
| GET | `/v1/project/events` | 成员变更记录 |
| POST | `/v1/members` | 所有者添加成员 `{id:"human.x", name, roles:[…]}` |
| DELETE | `/v1/members/{id}` | 所有者移出成员（保留历史，未完成任务退回） |
| GET | `/v1/workitems` | 工作项列表，含当前在等谁 |
| POST | `/v1/workitems` | 发起工作 `{text}` |
| GET | `/v1/workitems/{id}` | 详情：步骤、产出、联签进度、证据日志 |
| GET | `/v1/tasks` | 我的人工任务 |
| POST | `/v1/workitems/{id}/human-output` | 提交人工任务 `{content}` |
| GET | `/v1/approvals` | 待我审批 |
| POST | `/v1/workitems/{id}/decision` | 批准 `{approve:true}`；退回 `{approve:false, reason:"…"}`（退回必须写理由） |

错误统一为 `{"ok": false, "error": "代码"}`，例如 `NOT_ALLOWED_TO_DECIDE`、`ALREADY_APPROVED_BY_ACTOR`、`NOT_ASSIGNEE`、`LAST_OWNER`。

## 3. 安全

- 令牌只能在交互终端里由人签发，只显示一次，磁盘上只存哈希；重签即作废旧令牌。Agent 没有令牌。
- 成员被移出后，他的令牌立刻失效。
- 网页调用只接受 `--allow-origin` 列出的来源，其他浏览器来源一律拒绝。
- 只收 JSON，单次不超过 64 KiB；服务端错误不向外泄露细节；日志只记路径，不记内容和令牌。

## 4. 用法（Windows PowerShell）

```powershell
$py = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
cd D:\Codex\skills\sayelf-agent-ops
& $py -m sayelf_agent_ops.workspace_api init --spec templates\buildcostiq-project-department.json
& $py -m sayelf_agent_ops.workspace_api issue-token human.pm
& $py -m sayelf_agent_ops.workspace_api serve --allow-origin http://127.0.0.1:5173
```

## 5. 本次不做（Sprint 08）

- 工作项持久化：成员和规则已落盘，审批记录在 SQLite；工作项本身还在进程内存里，服务重启后清空。
- BuildCostIQ 工作台本体（新仓库，按画布 4 屏 + 生产负责人实现，只调本接口）。
- 局域网或公网访问、正式登录（sayelf.app）。
