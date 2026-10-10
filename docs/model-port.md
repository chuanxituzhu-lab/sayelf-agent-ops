# 模型接口：没有 AI 平台也能跑

> Sprint 08。Agent Ops 直接调用大模型，不依赖 Claude Code、Codex 这类 AI 平台。有平台时，平台通过 MCP 调用 Agent Ops（见 [mcp.md](mcp.md)）；没有平台时，Agent Ops 自己用这里配置的模型干活。

```text
   有 AI 平台                         没有 AI 平台
Claude Code / Codex …              BuildCostIQ 工作台 / 桌面端
        │ MCP                               │ 工作区接口
        ▼                                   ▼
   ┌──────────── Sayelf Agent Ops 内核 ────────────┐
   │ 路由 · 最少岗位 · 自检 · 独立复核 · 人工审批   │
   └───────────────────────┬────────────────────────┘
                           │ 模型接口（OpenAI 兼容）
            DeepSeek · 通义千问 · 豆包 · Kimi · 智谱 · Ollama · LM Studio
```

## 三种状态

| 状态 | 表现 |
|---|---|
| 没配模型 | 照常运行：标题用内置模板，其余技能返回如实标记的占位产出 |
| 配了本机模型（Ollama / LM Studio） | 全部技能由模型起草；数据不出本机，无需密钥、无需额外允许 |
| 配了远程模型 | 必须显式 `--allow-remote` 才会调用；没允许时一次都不调，执行记录里写明 `MODEL_CONSENT_REQUIRED` |

## 配置（Windows PowerShell）

```powershell
$py = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
cd D:\Codex\skills\sayelf-agent-ops
& $py -m sayelf_agent_ops.model_cli presets
& $py -m sayelf_agent_ops.model_cli configure --preset deepseek --allow-remote
setx DEEPSEEK_API_KEY "你的密钥"
# 重开一个 PowerShell 窗口后：
& $py -m sayelf_agent_ops.model_cli test
```

本机模型：`configure --preset ollama --model qwen2.5:7b`（模型名以 `ollama list` 为准），不需要密钥。

豆包、Kimi 没有默认模型名，用 `--model` 写控制台里的模型或接入点名称。各家模型名会更新，以官方控制台为准。

## 规则

- 密钥只放环境变量，`model.json` 只记变量名。`show`、`capabilities` 接口、日志都不显示密钥。
- 远程地址必须是 https；只有本机地址允许 http。
- 环境变量 `SAYELF_MODEL_*`（Sprint 05 的写法）优先于 `model.json`。
- 有专门实现的技能（标题、大纲、短视频脚本）用专门实现；其余技能走通用执行器：按技能契约（用途、岗位职责、上一步产出、返工意见）让模型起草。每份产出都标注“模型起草，未经计算或现场核实，需由人复核后使用”，并列出模型的假设和缺少的材料。
- 模型只负责起草。自检、独立复核、人工审批一步不少。
- 个别服务不支持 JSON 模式时，自动改为普通回复再解析，不需要手动处理。
- 模型配置坏了：工作区接口拒绝启动并说明原因；MCP 入口照常启动，在 `capabilities` 里报告 `model_error`。

## 查询

- 命令行：`model_cli show`
- 工作区接口：`GET /v1/capabilities`

测试：`evals/test_model_port.py`，用本机假模型服务验证，不需要真实密钥。
