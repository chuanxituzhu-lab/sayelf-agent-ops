# Sayelf Agent Ops

**通用 Agent Ops 底座，自媒体公司优先落地。**

Sayelf 把一项业务请求整理成 WorkItem，再按交付物、行业、岗位和技能规划工作。Core 负责通用流程，Industry Pack 承载行业规则；第一条业务落地路线是自媒体公司的选题、内容策划与运营协作。

> **最少岗位，专业闭环。**

[下载最新版本](#下载最新版本) · [English](#sayelf-agent-ops-1) · [Windows 构建说明](installer/windows/README.md) · [构建决策记录](docs/desktop-build-decision.md)

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
- **行业边界：** 媒体与工程岗位、技能和路由规则已拆到可注册的 Pack 模块；通用 Router 读取 Registry 中的规则。Sprint 01 尚未实现从外部目录动态发现或加载 Pack；工程路由保留为基础样例。
- **本地优先：** 当前桌面基线在本机初始化数据和 SQLite 元数据，不启动网络服务，也不发送遥测。

## 当前实现范围

Sprint 01 已打通最小路由与规划路径：请求 → WorkItem → 路由 → 计划 → READY。媒体路由示例可将请求分配到 `media.content-planner`，并选择 `media.title-writing` 技能。

这仍是 Agent Ops 的可验证底座，不代表完整的自媒体公司自动运营系统。Executor、内容生成、外部平台连接、Review、Evidence、Risk 和 Human Gate 尚未实现；已安装岗位也不会自动执行任务。

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
```

当前 Core 评估集包含 19 个用例。预期媒体路由示例：

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
- **Industry boundary:** media and engineering roles, skills, and routing rules now live in separately registerable Pack modules; the general Router reads rules from the Registry. Sprint 01 does not yet discover or load Packs from external directories. Engineering routing remains a foundation example.
- **Local-first:** the current desktop baseline initializes local data and SQLite metadata. It starts no network service and sends no telemetry.

## Current implementation

Sprint 01 implements a verifiable routing and planning path: request → WorkItem → route → plan → READY. The media routing example assigns a request to `media.content-planner` with the `media.title-writing` skill.

This is the validated Agent Ops foundation, not a complete autonomous media company. The Executor, content generation, external platform connectors, Review, Evidence, Risk, and Human Gate are not implemented. Registered roles do not execute tasks automatically.

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

The current Core evaluation suite contains 19 cases. Expected media routing example:

```text
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
State: READY
```
