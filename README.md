# Sayelf Agent Ops

![Sayelf 山野精灵 Logo](desktop/tauri/public/sayelf-logo.png)

**通用 Agent Ops 底座，自媒体公司优先落地。**

WebUI、favicon、桌面窗口和安装包使用同一套“山野精灵”品牌图标资源。

Sayelf 把一项业务请求整理成 WorkItem，再按交付物、行业、岗位和技能规划工作。Core 负责通用流程，Industry Pack 承载行业规则；第一条业务落地路线是自媒体公司的选题、内容策划与运营协作。

> **最少岗位，专业闭环。**

[下载最新版本](#下载最新版本) · [English](#sayelf-agent-ops-1) · [Windows 构建说明](installer/windows/README.md) · [桌面构建决策](docs/desktop-build-decision.md) · [最少岗位决策](docs/bdr-adaptive-minimum-workflow.md) · [v1.5 工作流融合决策](docs/bdr-workflow-v15-fusion.md) · [工作台 UI 融合决策](docs/bdr-workbench-ui-reference.md) · [通用工作区模式决策](docs/bdr-workspace-mode-unification.md) · [Harness 分派预览决策](docs/bdr-harness-route-edit-loop.md)

## 下载最新版本

| 平台 | 最新安装包 |
| --- | --- |
| Windows x64 | [Sayelf-Agent-Ops-Setup-x64.exe](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-Setup-x64.exe) |
| macOS Apple Silicon | [Sayelf-Agent-Ops-macOS-arm64.dmg](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-macOS-arm64.dmg) |
| macOS Intel | [Sayelf-Agent-Ops-macOS-x64.dmg](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-macOS-x64.dmg) |

目前尚未发布公开安装包。以上链接会在首个 GitHub Release 发布后指向最新正式版本；[查看所有版本](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases)。

## 产品与架构

Sayelf Agent Ops 面向一人公司和小团队，目标是让专业工作可以被拆分、路由、追踪，并逐步由可替换的行业包承载。通用 Core 与具体行业分开：增加行业覆盖时扩展 Pack，不为每个行业复制一套引擎。

目标工作流：
```text
业务请求
  → WorkItem
  → 交付物优先路由
  → 最小工作计划
  → Role + Skill
  → 状态流转与交付
```

- **通用 Core：** WorkItem、确定性 Router、最小 Planner、Role / Skill Registry 和 State Engine。
- **首个行业落地：** 自媒体公司工作流，Sprint 01 已纳入选题和内容策划岗位、技能及路由示例。
- **行业边界：** 媒体、工程与软件岗位、技能和路由规则拆分为可注册的 Pack 模块；默认 MCP 能力包括这三个包。通用 Router 读取 Registry 中的规则。软件岗位由 Codex 宿主按路由计划执行，需提供验证和独立审核证据；完整说明见 [软件宿主执行契约](docs/software-host-execution.md)。
- **最少岗位闭环：** 用户输入工作内容后，系统从当前行业包已注册技能中匹配岗位；单一交付按依赖组合，明确的复合交付覆盖每项结果并去掉重复技能/岗位。
- **本地优先：** 请求、附件、OCR、工作流状态和成果默认留在本机；应用不启动网络服务或发送遥测。只有用户配置模型并逐次同意后，文字才会发送至所选模型服务。
- **宿主执行合同：** `route_task` 同时返回机器可读的 `workflow_contract`、分工合规校验和宿主证据模板。单一步骤保持一个 `agent-as-tool`，明确依赖的多步骤才使用 `sequential`；计划状态不会伪装成已执行成果。Codex 可在本地执行后调用 `validate_host_execution_evidence`，缺少独立复核会保持 `review_pending`。详见 [v1.5 工作流融合决策](docs/bdr-workflow-v15-fusion.md)。

## 当前实现范围

Sprint 01 已打通最小路由与规划路径：请求 → WorkItem → 路由 → 计划 → READY。媒体路由示例可将请求分配到 `media.content-planner`，并选择 `media.title-writing` 技能。

桌面工作台提供通用专业工作需求入口：用户输入行业/专业和工作内容，系统先按交付物自动识别行业、最少岗位与技能，再生成可核对的分派方案；确认后执行并在详情页展示可读成果、占位状态和证据日志。媒体标题技能已可在本机直接生成真实标题；尚未接入执行器的技能会明确显示结构占位，不冒充成品。工作正文与行业提示分开保存，行业提示不会污染生成内容。工作台可添加 TXT、Markdown、PDF 和常见照片；PDF 文字提取与中英文 OCR 在本机离线完成；图片只识别文字，不分析画面场景或物体。每项工作最多添加 5 个附件、单个不超过 15 MiB。

复合需求会合并已注册路由规则，并按技能输入/输出依赖排序。例如“为小红书写笔记并生成配图方案”会覆盖内容和视觉成果；“对比 BOQ 和施工图”会覆盖商务与技术成果。无法匹配的能力会提示补充或说明缺口，不会临时编造岗位。

配置兼容的 AI 服务地址、模型和密钥后，支持的工作单可生成岗位成果并独立审核。密钥保存在系统凭据库。使用远程模型时，每次运行前都会显示目标地址与将发送的需求文字、附件识别文字，并要求单次确认；原始文件不会上传。工作流按阶段保存状态和版本，失败后可以从已完成阶段继续。媒体生成稿可编辑；点击确认后，系统在本机生成含 Markdown、清单和来源索引的 ZIP 发布包。应用不登录平台、不自动发布。发布后可手工录入浏览、点赞、收藏、评论和分享数量，生成只保存在本机的比例复盘；缺少历史基线时不会替用户判断好坏。

这是可运行的本地创作与人工发布交接闭环，不是无人值守的自媒体公司。当前没有内置模型账号或默认密钥；首次真实连接和内容质量需由使用者配置并验证。平台直发、自动排期、数据接口、视频生成和自动化经营决策尚未实现。

## 执行内核（Sprint 02 / 02b）

Solo 与 Team 共用一条执行路径，代码里没有 `mode` 字段：单人项目就是只有一个人类成员的项目。

```text
提交 → 交付物路由 → 按需加载 Skill → 产出 → 产出者自检 → 独立审核 → 返工
     → 自动交付，或停在人工裁决 → 人类批准（一次性授权）→ 交付
```

- **两道门：** 产出者先自检（AcceptanceGate），再由另一个 Agent 独立审核；产出者不能审核自己，人数为 1 也不例外。
- **人工裁决：** `Policy` 决定谁能批，`HumanGate` 决定批的是什么——动作、目标、产出摘要绑定，一次有效，批准后改稿即失效；草稿已备、已上传、之前批过都不算授权。
- **按需加载：** 只加载计划需要的 Skill；缺能力、非商用许可或超出上下文预算时停下并说明原因。
- **审批落盘：** 桌面“确认成果并生成发布包”经同一道授权门，授权号写入发布包清单，记录保存在本机 SQLite，重启后仍可校验。
- **按行业包加载：** 工作空间只加载自己的行业包；其他行业的需求会提示补充，不会被硬套岗位。
- **桌面里用内核：** 交付物是标题或短视频脚本的工作单，执行面板会出现“生成标题”或“生成短视频脚本”，由产出岗位生成并自检、独立审核岗位检查，不合格自动返工。
- **团队（N 人 + N Agent）：** 专业岗位由人担任时那一步交给人；多人裁决须各批一次才交付；成员可加入、退出，历史不改写。通用团队规格见 `templates/agent-ops-team-workspace.json`；内核评估场见 `evals/fixtures/team-project.json`。
- **模型接口：** 没有 Claude Code、Codex 等 AI 平台也能运行：直连 DeepSeek、通义千问、豆包、Kimi、智谱或本机 Ollama，每个技能都可由模型起草，自检、复核、人工审批照旧。见 [docs/model-port.md](docs/model-port.md)。
- **产品工作台接入：** 行业产品用自己的界面，通过本机工作区接口连内核：成员凭各自令牌登录，提交人工任务、联签审批；Agent 没有令牌。BuildCostIQ 是一个显式的造价产品模板，不是 Agent Ops 共享底座的默认 UI。见 [docs/sprint-07-workspace-api.md](docs/sprint-07-workspace-api.md)。
- **通用本地工作台：** Sprint 09 融合了一个不依赖 Node 的标准库 WebUI：打开后输入行业/专业与工作内容、预览最少岗位、附加文件、提交工作项并查看成果与证据。行业包只是示范与已连接能力目录；未选择行业也能先做路由建议。预览方案后可返回修改，输入变化会使旧方案失效并要求重新生成；确认后才开始执行。结果页把结构化 `content` / `items` 渲染成可读成果，并把 `placeholder=true` 明确显示为结构占位；路由卡同时显示识别依据。文本、CSV、JSON、Markdown 与安全的 XLSX 在工作区内提取；PDF、照片、DWG 等先保留原件和哈希，界面明确标注未解析。它只调用当前 Workspace API，不创建第二套执行内核。默认初始化使用 `templates/agent-ops-workspace.json`；多人工作区可显式选择 `templates/agent-ops-team-workspace.json`。见 [Sprint 09 深度融合决策](docs/bdr-sprint09-deep-fusion.md) 与 [Harness 分派预览决策](docs/bdr-harness-route-edit-loop.md)。
- **四条 Solo 不变式**由 `evals/test_solo_invariants.py` 强制。详见 [ARCHITECTURE.md](ARCHITECTURE.md) 与 [规则层规格](docs/sprint-02-gates-spec.md)。

作为 Claude Code / Codex 共享 Skill 使用时，见 [SKILL.md](SKILL.md)；命令行路由：`python scripts/route.py "写 5 个公众号标题"`。任何支持 MCP 的 Agent 可通过本机 MCP 入口调用内核，Agent 不能批准，需人在终端批准，见 [docs/mcp.md](docs/mcp.md)。

**宿主 Agent 接入建议：** 若由 Codex 等宿主完成实际工作，调用 `route_task` 获取岗位、技能、执行合同和步骤，再由宿主执行并保留验证证据；无需调用 `run_task`。行业岗位建议可通过 MCP 本地核验、查询和撤销，不会改写共享行业包，也不要求新模型或编排框架。详见 [MCP 接入说明](docs/mcp.md)。

## 一键安装基线

普通用户安装和启动桌面应用不需要另外安装 Python、Node.js、Git、Docker、数据库或命令行工具。安装包包含 Tauri 桌面壳和冻结的 Python Core Runtime；首次启动会初始化本地目录、SQLite 元数据并运行健康检查。

| 平台 | 安装包构建路线 | 默认数据目录 |
| --- | --- | --- |
| Windows x64 | Windows 上运行 `installer/windows/build.ps1`，生成 NSIS Setup.exe（内含离线 WebView2 安装程序） | `%LOCALAPPDATA%\Sayelf` |
| macOS Apple Silicon | 在 Apple Silicon Mac 上运行 `installer/macos/build.sh arm64`，生成 DMG | `~/Library/Application Support/Sayelf` |
| macOS Intel | 在 Intel Mac 上运行 `installer/macos/build.sh x64`，生成 DMG | `~/Library/Application Support/Sayelf` |

卸载应用会保留用户数据。健康检查失败、数据目录来源不明、已有数据库版本过新或行业包不匹配时，应用会停止初始化，不覆盖现有数据。签名与 macOS 公证属于正式发布流程；本地构建产物不等于已签名的公开版本。详见 [Windows 构建说明](installer/windows/README.md) 和 [macOS 构建说明](installer/macos/README.md)。

## 开发与验证

本节面向开发者；普通用户使用上面的安装包，无需运行这些命令。

```powershell
python -m sayelf_agent_ops.demo
python -m unittest discover -s evals -v
# 工作区 API 与本地 WebUI（两个终端）
python -m sayelf_agent_ops.workspace_api serve --allow-origin http://127.0.0.1:18766
python -m sayelf_agent_ops.console
```

Python 自动评估集覆盖核心路由与状态、团队协作（人工步骤、多人裁决、成员进出）、工作区接口（令牌身份、来源限制）、规则层（两道门与加载器）、执行内核与四条 Solo 不变式、审批持久化、模型标题与短视频脚本技能、行业包按需加载、MCP 入口与终端人工批准、桌面基线，以及媒体执行流程的离线模拟。预期媒体路由示例：

```text
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
State: READY
```

---

# Sayelf Agent Ops

**A general Agent Ops foundation, with a media company as its first vertical.**

The WebUI, favicon, desktop window, and installers use the same Sayelf brand asset.

Sayelf turns a business request into a WorkItem, then plans it by deliverable, industry, role, and skill. The Core owns the shared workflow; replaceable Industry Packs provide domain rules. The first business workflow targets a self-media company, starting with ideation, content planning, and operations collaboration.

> **Fewer roles. A professional workflow.**

[Download the latest version](#latest-downloads) · [中文](#sayelf-agent-ops) · [Windows build guide](installer/windows/README.md) · [Build decision](docs/desktop-build-decision.md)

## Latest downloads

| Platform | Latest installer |
| --- | --- |
| Windows x64 | [Sayelf-Agent-Ops-Setup-x64.exe](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-Setup-x64.exe) |
| macOS Apple Silicon | [Sayelf-Agent-Ops-macOS-arm64.dmg](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-macOS-arm64.dmg) |
| macOS Intel | [Sayelf-Agent-Ops-macOS-x64.dmg](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases/latest/download/Sayelf-Agent-Ops-macOS-x64.dmg) |

There is no public installer release yet. These links will resolve to the latest stable assets after the first GitHub Release is published. [Browse all releases](https://github.com/chuanxituzhu-lab/sayelf-agent-ops/releases).

## Product and architecture

Sayelf Agent Ops is designed for one-person companies and small teams. It makes professional work easier to decompose, route, and track, while letting replaceable industry packs carry domain-specific behavior. New industries extend a Pack instead of duplicating the shared engine.

Target workflow:
```text
Business request
  → WorkItem
  → Deliverable-first routing
  → Minimum plan
  → Role + Skill
  → State transitions and deliverables
```

- **General Core:** WorkItem, deterministic Router, minimum Planner, Role / Skill Registry, and State Engine.
- **First vertical:** self-media company workflows. Sprint 01 already includes sample roles, skills, and routing for topic selection and content planning.
- **Adaptive minimum staffing:** single deliverables use their registered skill chain; explicit compound requests are combined by pack rules, ordered by declared input/output dependencies, and deduplicated.
- **Industry boundary:** media, engineering, and software roles, skills, and routing rules live in separately registerable Pack modules; the default MCP capability exposes all three. The general Router reads rules from the local Registry. External pack discovery is not implemented. Engineering currently produces a local professional workplan; engineering execution handlers are not yet connected.
- **Local-first:** requests, attachments, OCR, workflow state, and outputs stay on-device by default. The app starts no network service and sends no telemetry. Text leaves the device only after the user configures a model and consents to each run.

## Current implementation

Sprint 01 implements a verifiable routing and planning path: request → WorkItem → route → plan → READY. The media routing example assigns a request to `media.content-planner` with the `media.title-writing` skill.

The desktop workbench is industry-neutral: a user enters an industry or specialty and the work description, then the system identifies the deliverable, minimum roles, and skills before showing an editable route preview. After confirmation, the detail page renders structured `content` / `items` as readable results, marks `placeholder=true` outputs as structural placeholders, and keeps the evidence log visible. The media title skill can generate real titles locally; unsupported handlers remain explicit placeholders. The original work text is kept separate from the industry hint so routing context never leaks into generated content. Users can attach TXT, Markdown, PDF, or common image files. PDF text extraction and Chinese/English OCR run locally and offline. Images are OCRed for text; the app does not interpret image scenes or objects. Each work item accepts up to five attachments, 15 MiB each.

The workbench also accepts an industry label such as “self-media company,” “MCN,” or “WeChat content operations” and recommends roles from the local registered pack. Recommendations reuse existing roles and do not activate or create them. Unsupported or ambiguous input asks the user to clarify; no model call is made.


After configuring an AI-compatible endpoint, model, and key, the workbench can run three role stages: content plan, creative brief, and channel-ready draft. The key stays in the operating system credential store. Before each remote run, the UI identifies the endpoint and the request/OCR text being sent and asks for one-time consent; original files stay local. Stage state and versions are saved locally, and a failed run can resume from accepted stages. Users can edit the draft, then explicitly approve it to create a local ZIP containing Markdown, a checklist, and a source index. The app does not sign into social platforms or publish for the user. After manual publication, users can enter views, likes, saves, comments, and shares to create a local metrics review; without a history baseline, the app reports ratios but makes no performance judgment.

This is a working local creation and human publishing handoff, not an unattended media company. There is no bundled model account or default API key; users must configure and verify a real provider. Direct platform posting, scheduling, analytics connectors, video generation, and automated business decisions are not implemented.

## Execution kernel (Sprint 02 / 02b)

Solo and Team share one execution path; there is no `mode` field. A solo project is simply a project with one human member.

```text
submit → deliverable-first routing → load only planned skills → produce → producer self-check
       → independent review → rework → auto-deliver, or stop at the human gate
       → human approval (single-use authorization) → deliver
```

- **Two gates:** the producer self-checks (AcceptanceGate), then a different agent reviews. A producer never reviews its own work, even with one human.
- **Human gate:** `Policy` decides who may approve; `HumanGate` decides what was approved — action, target, and output digest are bound, single-use, and void if the output changes. Prepared drafts, uploads, or earlier approvals never count as authorization.
- **Lazy loading:** only planned skills load; missing capabilities, non-commercial licenses, or context-budget overruns stop the run with a reason.
- **Durable approvals:** the desktop “approve and create package” action goes through the same gate; the authorization id is written into the package manifest and kept in local SQLite across restarts.
- **Per-workspace packs:** a workspace loads only its own industry pack; requests for other industries ask for clarification instead of being misrouted.
- **Kernel tasks on the desktop:** work items whose deliverable is titles or a short-video script get a “Generate titles” / “Generate video script” button; the producer self-checks, an independent reviewer checks, and failures are reworked automatically.
- **Teams (N humans + N agents):** a step whose role a human holds goes to that person; quorum gates need one approval from each distinct person; members can join and leave without rewriting history. See `templates/agent-ops-team-workspace.json` and [docs/sprint-06-team.md](docs/sprint-06-team.md).
- **Model port:** runs without any AI host platform by calling an OpenAI-compatible model directly (DeepSeek, Qwen, Doubao, Kimi, GLM, local Ollama); every skill can be drafted by the model, with self-check, independent review and human approval unchanged. See [docs/model-port.md](docs/model-port.md).
- **Product workbenches:** an industry product keeps its own UI and connects through the local Workspace API: each member signs in with their own token to submit human steps and decide quorum gates; agents get no token. See [docs/sprint-07-workspace-api.md](docs/sprint-07-workspace-api.md).
- **Harness route loop:** the generic local workbench previews the minimum role plan through the shared routing contract, shows the recognition reason, lets the user return and edit the input, invalidates stale previews, and starts execution only after the current plan is confirmed. The result view distinguishes generated content from structural placeholders. See [docs/bdr-harness-route-edit-loop.md](docs/bdr-harness-route-edit-loop.md).
- **Four Solo invariants** are enforced by `evals/test_solo_invariants.py`. See [ARCHITECTURE.md](ARCHITECTURE.md) and the [rules spec](docs/sprint-02-gates-spec.md).

For use as a shared Claude Code / Codex skill, see [SKILL.md](SKILL.md); CLI routing: `python scripts/route.py "写 5 个公众号标题"`. Any MCP-capable agent can call the kernel through the local MCP entry; agents cannot approve — a human approves in a terminal. See [docs/mcp.md](docs/mcp.md).

**Host-agent integration:** When Codex or another host performs the actual work, call `route_task` for roles, skills, the workflow contract, and execution steps, then execute and retain validation evidence in the host. This path does not call `run_task`; missing independent review stays `review_pending`. Role suggestions can be locally verified, inspected, and revoked through MCP without rewriting shared packs or requiring a model/framework. See the [MCP integration guide](docs/mcp.md).

## One-click installer baseline

End users do not need to install Python, Node.js, Git, Docker, a database, or command-line tools to install and launch the desktop app. The installer bundles the Tauri shell and frozen Python Core Runtime. First launch initializes local folders and SQLite metadata, then runs a health check.

| Platform | Installer build route | Default data directory |
| --- | --- | --- |
| Windows x64 | Run `installer/windows/build.ps1` on Windows to create an NSIS Setup.exe with the offline WebView2 installer | `%LOCALAPPDATA%\Sayelf` |
| macOS Apple Silicon | Run `installer/macos/build.sh arm64` on Apple Silicon Mac to create a DMG | `~/Library/Application Support/Sayelf` |
| macOS Intel | Run `installer/macos/build.sh x64` on Intel Mac to create a DMG | `~/Library/Application Support/Sayelf` |

Uninstalling the app preserves user data. Initialization stops without overwriting data when the data directory is unfamiliar, the database schema is newer, the selected industry pack does not match, or a health check fails. Signing and macOS notarization belong to the production release process; local build artifacts are not signed public releases. See the [Windows build guide](installer/windows/README.md) and [macOS build guide](installer/macos/README.md).

## Develop and verify

This section is for developers. End users install the desktop app and do not need these commands.

```powershell
python -m sayelf_agent_ops.demo
python -m unittest discover -s evals -v
```

The Python evaluation suite covers core routing and state, team collaboration, the Workspace API (token identity, origin limits), the rules layer (two gates and loader), the execution kernel and four Solo invariants, durable approvals, model-backed title and short-video script skills, lazy industry packs, the MCP entry and terminal-only approval, the desktop baseline, and offline simulated media workflows. Expected media routing example:

```text
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
State: READY
```
