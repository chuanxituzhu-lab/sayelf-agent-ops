# Sayelf Agent Ops 架构 v0.2

> 面向个人与专业团队的 Human + Multi-Agent 协同执行与可信交付系统。
> 最少岗位，专业闭环。

## 1. 模式（产品叙事）

| 模式 | 组织形式 | 适用场景 |
|---|---|---|
| Solo Mode | 1 Human + N Agents | 一人公司、独立开发者、个人创作者 |
| Team Mode | N Humans + N Agents | 小型团队、施工项目部、专业服务组织 |
| Hybrid Mode | 人员动态加入或退出 | 项目协作、临时专家参与 |

单人多 Agent 是基础模式，必须完整可用；多人是扩展模式。

## 2. 内核原则：只有一条路径

代码层**不存在 `mode` 字段，也不存在 `if solo` 分支**。

- Solo = 成员数为 1 的项目。
- Team = 成员数大于 1 的项目。
- Hybrid = 成员列表可增减，这是所有项目的天然属性，不是第三种实现。

理由：两条路径必然分叉，Solo 路径会在 Team 迭代中被遗忘并退化。只有一条路径时，Team 的任何改进 Solo 自动受益，Solo 永远是这条路径上最先跑通、最先测试的情况。

内核统一提供：任务状态机 · 交付物路由 · Skill · 记忆 · 证据链 · 人工裁决。

## 3. 核心对象

### Actor
`id`、`kind`（`human` | `agent`）、`roles`。

### Project
`id`、`members: list[Actor]`、`policy: Policy`。
`Project.solo(owner_id)` 一步创建单人项目：唯一人类 + 默认 Agent 角色 + 默认策略，零配置。

### Policy
定义"哪些动作需要哪类角色批准"。
Solo 默认策略只有一条：高风险动作（发布、对外提交、发送）由项目内唯一人类批准。
Team 在此基础上扩展，不改变结构。

### WorkItem（在 Sprint 01 基础上增加）
`owner`、`assignee`、`reviewer`、`approver`，全部存 actor id，不存"用户"。

### Event（只追加）
每一次状态变化、产出、审核、裁决都记录 `actor`、`event`、`from`、`to`、`evidence`。
证据链和 Team 审计共用这一份日志。

## 4. 状态机（Sprint 02 目标）

```text
INBOX → SCOPED → WORKING → READY → REVIEW ─┬→ APPROVED → DELIVERED
                    ↑                      │
                    └──── REWORK ←─────────┘
```

- 进入执行前，`SkillLoader` 只加载计划里的 Skill；缺能力、非商用许可或超出上下文预算时停在 WORKING 并上报，不带病执行；执行结束即释放。
- `READY → REVIEW`：产出者先过 `AcceptanceGate` 自检（规则来自 SkillContract.validation，通过记录绑定产出摘要），再提交审核。
- `REVIEW → REWORK`：自检或独立审核任一不过，必须附带返工理由。
- `REVIEW → APPROVED`：自检与独立审核都通过。
- `APPROVED → DELIVERED`：若交付物命中 Policy 中的高风险项，必须由有权人类裁决（Human Gate）；否则自动交付。

人类裁决由两部分组成，各管一件事：

| 组件 | 回答 | 规则 |
|---|---|---|
| `Policy` + `Project.can_decide` | **谁**能批 | 必须是 human 类型成员，且持有该动作的批准角色 |
| `HumanGate` | 批的是**什么** | 动作、目标、产出摘要三者绑定；一次有效；批准后改稿即失效；草稿已备、已上传、之前批过都不算授权 |

## 5. 四条 Solo 不变式（冻结，测试强制）

对应测试：`evals/test_solo_invariants.py`（Sprint 02 起强制生效）。任何改动使其中一条失败，不得合入。

1. **零配置闭环**：一个人新建项目、提交任务，不填写任何成员、角色、权限，即可从 INBOX 跑到 DELIVERED。
2. **多 Agent 分工完整**：路由、产出、审核、返工由不同 Agent 角色完成；产出者不能审核自己，人数为 1 也不例外。
3. **人类只在必要处出现**：Agent 之间自动接力，只有命中 Human Gate 的动作才停下等唯一人类裁决。
4. **升级无迁移**：单人项目加入第二个成员后，已有任务、证据链、历史原样可用，不转换数据。

## 6. 开发顺序

| Sprint | 范围 | 状态 |
|---|---|---|
| 01 | WorkItem、State Engine、Role/Skill Registry、交付物路由、最小计划器 | 完成（18 测试通过） |
| 02 | 规则层：AcceptanceGate、按动作授权的 HumanGate、按需加载 SkillLoader（c2d7437） | 完成 |
| 02b | 内核层：Actor / Project / Policy、扩展状态机、Executor 接口（1 条真实技能：标题生成）、独立 Review、事件日志；两道门与加载器接入 Runtime；桌面工作台与 SQLite 运行时（PR #1）并入；四条不变式全绿 | 完成 |
| 03 | HumanGate 审批持久化到桌面 SQLite（统一 `approve_and_export`）、标题生成接入 LLM、第二条真实技能、Pack 级按需加载 | 下一步 |
| 03+ | sayelf.app 公网入口（复用桌面前端，含登录鉴权） | 待定 |
| 04+ | 记忆、Risk 分级、Connector Runtime、多人权限细化 | 待定 |

Team Mode 的真实验证场是 BuildCostIQ：施工项目部本身就是 N 人 + N Agent 的组织。Agent Ops 是内核，BuildCostIQ 是第一个运行在内核上的专业 FDE。

## 7. 不做的事

- 不建两套系统，不为 Solo 和 Team 分别实现。
- 不要求单人用户配置组织架构或权限。
- 不造跨行业超级 Agent，跨行业任务拆成专业子任务。
- Agent 不得绕过 Human Gate 执行发布、对外提交、发送。
