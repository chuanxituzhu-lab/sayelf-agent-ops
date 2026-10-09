# Sayelf Agent Ops

![Sayelf 山野精灵 Logo](desktop/tauri/public/sayelf-logo.png)

**通用 Agent Ops 底座，自媒体公司优先落地。**

WebUI、favicon、桌面窗口和安装包使用同一套“山野精灵”品牌图标资源。

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
- **本地优先：** 请求、附件、OCR、工作流状态和成果默认留在本机；应用不启动网络服务或发送遥测。只有用户配置模型并逐次同意后，文字才会发送至所选模型服务。

## 当前实现范围

Sprint 01 已打通最小路由与规划路径：请求 → WorkItem → 路由 → 计划 → READY。媒体路由示例可将请求分配到 `media.content-planner`，并选择 `media.title-writing` 技能。

桌面工作台提供自媒体需求入口：选择小红书、公众号、视频号、抖音或通用媒体内容，输入文字，并可添加 TXT、Markdown、PDF 和常见照片。PDF 文字提取与中英文 OCR 在本机离线完成；图片只识别文字，不分析画面场景或物体。每项工作最多添加 5 个附件、单个不超过 15 MiB。提交后先生成工作单和方案；首次使用可一键激活内容策划、内容制作、运营增长三个媒体角色。

工作台还可输入“自媒体公司”“MCN”“公众号运营”等行业词，从本机已注册的行业包推荐岗位。推荐只读取现有角色，不会自动激活或新建岗位；暂不支持的行业或含义不明确的输入会提示用户补充，不调用模型。

配置兼容的 AI 服务地址、模型和密钥后，工作单可按三个岗位阶段生成内容方案、视觉创意简报和平台发布稿。密钥保存在系统凭据库。使用远程模型时，每次运行前都会显示目标地址与将发送的需求文字、附件识别文字，并要求单次确认；原始文件不会上传。工作流按阶段保存状态和版本，失败后可以从已完成阶段继续。生成稿可编辑；点击确认后，系统在本机生成含 Markdown、清单和来源索引的 ZIP 发布包。应用不登录平台、不自动发布。发布后可手工录入浏览、点赞、收藏、评论和分享数量，生成只保存在本机的比例复盘；缺少历史基线时不会替用户判断好坏。

这是可运行的本地创作与人工发布交接闭环，不是无人值守的自媒体公司。当前没有内置模型账号或默认密钥；首次真实连接和内容质量需由使用者配置并验证。平台直发、自动排期、数据接口、视频生成和自动化经营决策尚未实现。

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

当前自动评估集包含 26 个核心路由与桌面基线用例，另含媒体执行流程的离线模拟用例。预期媒体路由示例：

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
- **Industry boundary:** media and engineering roles, skills, and routing rules now live in separately registerable Pack modules; the general Router reads rules from the Registry. Sprint 01 does not yet discover or load Packs from external directories. Engineering routing remains a foundation example.
- **Local-first:** requests, attachments, OCR, workflow state, and outputs stay on-device by default. The app starts no network service and sends no telemetry. Text leaves the device only after the user configures a model and consents to each run.

## Current implementation

Sprint 01 implements a verifiable routing and planning path: request → WorkItem → route → plan → READY. The media routing example assigns a request to `media.content-planner` with the `media.title-writing` skill.

The desktop workbench accepts self-media requests for Xiaohongshu, WeChat Official Accounts, Channels, Douyin, or general media content. Users can enter text and attach TXT, Markdown, PDF, or common image files. PDF text extraction and Chinese/English OCR run locally and offline. Images are OCRed for text; the app does not interpret image scenes or objects. Each work item accepts up to five attachments, 15 MiB each. The app creates a WorkItem and plan; first-time users can activate the three media roles together.

The workbench also accepts an industry label such as “self-media company,” “MCN,” or “WeChat content operations” and recommends roles from the local registered pack. Recommendations reuse existing roles and do not activate or create them. Unsupported or ambiguous input asks the user to clarify; no model call is made.

After configuring an AI-compatible endpoint, model, and key, the workbench can run three role stages: content plan, creative brief, and channel-ready draft. The key stays in the operating system credential store. Before each remote run, the UI identifies the endpoint and the request/OCR text being sent and asks for one-time consent; original files stay local. Stage state and versions are saved locally, and a failed run can resume from accepted stages. Users can edit the draft, then explicitly approve it to create a local ZIP containing Markdown, a checklist, and a source index. The app does not sign into social platforms or publish for the user. After manual publication, users can enter views, likes, saves, comments, and shares to create a local metrics review; without a history baseline, the app reports ratios but makes no performance judgment.

This is a working local creation and human publishing handoff, not an unattended media company. There is no bundled model account or default API key; users must configure and verify a real provider. Direct platform posting, scheduling, analytics connectors, video generation, and automated business decisions are not implemented.

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

The automated evaluation suite includes 26 core routing and desktop-baseline cases, plus offline simulated media-workflow cases. Expected media routing example:

```text
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
State: READY
```
