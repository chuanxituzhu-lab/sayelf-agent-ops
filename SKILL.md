---
name: sayelf-agent-ops
description: "Use when a task should be routed by its deliverable to the right professional role and skill (media / engineering), or run through the Solo/Team Human + Multi-Agent loop with independent review and per-action human approval. Chinese triggers: Agent Ops / 一人公司 / 交付物路由 / 按交付物分派 / 岗位路由 / 谁来干 / 人工裁决 / Human Gate / 独立审核. Not for build discipline (use sayelf-base) or ordinary questions."
metadata:
  short-description: 交付物优先路由 + Human + Multi-Agent 执行内核
  aliases: [Agent Ops, 一人公司, 交付物路由, 岗位路由, 谁来干, 人工裁决, Human Gate, 独立审核]
---

# Sayelf Agent Ops

> 当前内容版本：0.4.0a1。

与 `sayelf-base` 是上下两层：sayelf-base 管“怎么造”（构建门禁，唯一底座）；本 Skill 管“谁来干”（按交付物路由与执行闭环）。两层叠加，不互相替代。

## 何时使用

- 判断一项任务该由哪个岗位、哪些技能完成（先看交付物，不看主题词）。
- 需要“产出者不能审核自己、对外动作必须由人逐项批准”的执行闭环。

## 怎么用

只读路由（不联网、不写文件）：

```powershell
python D:\Codex\skills\sayelf-agent-ops\scripts\route.py "写 5 个公众号标题"
```

单人项目跑完整闭环（路由 → 产出 → 自检 → 独立审核 → 返工 → 交付或停在人工裁决）：

```powershell
python D:\Codex\skills\sayelf-agent-ops\scripts\route.py --run "把已确认的文章整理成公众号草稿发布准备包"
```

输出为 JSON。`ok=false` 且 `error=UNROUTABLE_DELIVERABLE` 表示交付物不明确：向用户澄清，不要硬套岗位。

## 硬规则

1. 交付物优先，不按关键词；跨行业任务拆成专业子任务，不造超级 Agent。
2. 产出者不能审核自己；人数为 1 也不例外。
3. 发布、对外发送、删除、花钱、外部写入、账号配置：必须由人类逐项批准，批准只对一个动作、一个目标、一份产出有效，用一次即失效；草稿已备、已上传、之前批过都不算授权。
4. Skill 只按计划加载；缺能力、非商用许可、超出上下文预算时停下并说明原因，不带病执行。
5. 占位产出必须如实标记 `placeholder=true`，不得冒充成品。

架构与不变式见同目录 `ARCHITECTURE.md`；规则层规格见 `docs/sprint-02-gates-spec.md`。
