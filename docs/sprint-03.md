# Sprint 03：一条授权规则、第一条模型技能、按行业包加载

> 状态：已完成（2026-10-09）。基线：452ec78。

## 0. 一句话

桌面应用里“确认并生成发布包”改走内核那道授权门，审批记录落盘；标题生成接入大模型，经产出者自检与独立审核后交付；工作空间只加载自己的行业包。

## 1. 决策记录（按 sayelf-base 构建门禁）

1. 任务：消除“内核规则”与“桌面实际按钮”两条审批路径；让内核第一次产出真实成果；未使用的行业不进入内存与上下文。
2. 最接近的已有能力：内核 `HumanGate`（内存）、桌面 `workflow_approvals`（版本 + 摘要绑定）、桌面 `OpenAICompatibleProvider` 与逐次同意规则、`Registry.register_pack`。
3. Step 0：**Integrate**。不新增框架、依赖或数据库；在现有 SQLite 中加一张表。
4. 可度量差异：桌面导出的每个发布包都带一次性授权号，且授权号可在库中查到“谁、何时、批了哪个版本、已用掉”；重启后仍可校验；媒体工作空间不再导入工程包。
5. 证据：`evals/test_approval_persistence.py`（P01–P06、D01–D02）、`evals/test_sprint03.py`（T01–T04、K01–K06、D01–D05），合计 116 个测试全绿。
6. 最小内核：`ApprovalStore` 协议 + 内存实现；持久化实现放在桌面层（`desktop/runtime/approvals.py`）。
7. 插件边界：模型适配器保持中立，技能只依赖 `complete_json`；行业包按名称加载。
8. 本地优先：远程模型在任何调用前检查逐次同意；日志只记录事件码、摘要与成员 id，不记录需求原文和密钥。
9. 数据：审批表与任务日志属本机敏感数据，不进入仓库；仓库只含通用代码、文档和合成测试。
10. 回滚：`git revert` 本次提交；数据库迁移 3→4 前自动备份到 `backups/runtime-schema-3-*.sqlite3`，新表为纯新增，旧版本数据不受影响。

## 2. 改了什么

| 位置 | 变化 |
|---|---|
| `sayelf_agent_ops/gates.py` | `HumanGate` 改用可替换的 `ApprovalStore`；请求号全局唯一（重启不重号）；`consume` 原子化，一次批准只能兑现一次；已兑现的请求不能再次批准 |
| `desktop/runtime/approvals.py` | `SQLiteApprovalStore`（表 `gate_approvals`）；`ResultVersionAcceptance`：载荷必须指向已存版本且内容摘要一致；桌面只接受本机唯一人类 `human.local-user` 批准 |
| `desktop/runtime/media_workflow.py` | `approve_and_export` 生成发布包前经 `HumanGate` 请求→批准→兑现；授权号写入 `manifest.json` 与 `human-approved` 事件。已导出的包再次确认只做校验，不产生新授权 |
| `desktop/runtime/bootstrap.py` | 数据版本 3→4（自动备份）；只加载工作空间自己的行业包；不属于本行业包或交付物不明确的需求给出明确提示；新增 sidecar 动作 `kernel-titles` |
| `sayelf_agent_ops/skills/title_llm.py` | 模型版 `media.title-writing`：远程端点必须先同意；返回结构校验；返工意见传给下一轮；证据记录模型、用量、轮次 |
| `sayelf_agent_ops/runtime.py` | 技能执行失败（未同意、模型不可用、返回不合规）停在 WORKING 并上报，记录安全错误码；可接入持久化审批 |
| `sayelf_agent_ops/registry.py` | `build_registry(industries)` 按名称导入行业包；跨行业规则只在两端行业都加载时启用 |
| `sayelf_agent_ops/loader.py` | 行业包级许可证清单；`loaded_packs` 显示当前进入上下文的行业 |
| `desktop/runtime/build_sidecar.py` | 打包时收集全部内核子模块（行业包按名称加载，静态分析看不到） |

## 3. 本次不做

- 桌面界面上的“生成标题”按钮（需改 Tauri 前端与 Rust 命令）；目前通过 sidecar 动作 `kernel-titles` 调用。
- 平台自动发布、sayelf.app 公网入口、多人权限细化。
- 媒体三阶段工作流整体迁入内核 Runtime（规则已统一，执行路径迁移放到后续）。

## 4. 未验证

- 冻结后的 Windows 安装包未重新构建；`--collect-submodules` 的效果需在下次构建安装包时由 `smoke_sidecar.py` 验证。
- 真实模型服务未调用；模型标题技能只用模拟模型测试。
