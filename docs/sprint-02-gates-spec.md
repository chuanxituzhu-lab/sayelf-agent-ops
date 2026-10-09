# Sprint 02 规格：验收门 · 人类授权门 · 按需加载

> 状态：已合入 main（c2d7437，2026-10-09），Sprint 02b 已接入 Runtime，见第 7 节
> 基线：Sprint 01（commit f343bc5），18 个测试全绿，满足 README 中“routing 与 state 测试稳定后才可加 Human Gate”的解冻条件
> 原则：只新增，不改动 Sprint 01 的任何文件

## 0. 一句话

Agent 说“做完了”（READY）不等于人能看到，更不等于能对外动手。中间加两道门：先由 Agent 自检，再由人逐项授权。Skill 只在计划需要时加载，用完就释放。

## 1. 在主干上的位置

```text
Sprint 01:  INBOX → SCOPED → WORKING → READY
                                         │
Sprint 02:                     AcceptanceGate（Agent 自检）
                                 │ 不通过 → 返工；连续 2 次不通过 → 升级给人
                                 ▼ 通过
                               HumanGate.request（对外动作申请）
                                 ▼
                               人 approve（一次一项）
                                 ▼
                               HumanGate.authorize → 一次性令牌 → Executor（Sprint 03）

SkillLoader：plan 生成后 load_for_plan，执行完 release
```

Sprint 01 的状态机没有修改。两道门挂在 READY 之后，作为独立层存在。将来如需把 REVIEW / AWAITING_APPROVAL / DONE 写进 `WorkState`，可以在 Sprint 03 统一做，门的接口不需要变。

## 2. 规则 6：验收门（`gates.AcceptanceGate`）

| 条款 | 规定 |
|---|---|
| 触发 | 只接受 `state == READY` 的 WorkItem |
| 检查内容 | 逐个执行所选 Skill 在 `SkillContract.validation` 里声明的校验器 |
| 内置校验器 | `required-output-present`：存在类型匹配的产出，且不为空 |
| 未知校验器 | 视为失败（`UNKNOWN_VALIDATOR`），不允许静默跳过 |
| 失败处理 | 返工；达到 `max_attempts`（默认 2）次后 `escalate_to_human=True`，防止无限循环 |
| 防篡改 | 通过时记录产出摘要（SHA-256）；产出一旦变动，通过记录自动作废 |
| 审计 | 每次检查都写入 `WorkItem.history` |

## 3. 规则 1：人类授权门（`gates.HumanGate`）

**核心：授权逐项给，一次有效，不继承。**

| 条款 | 规定 | 拒绝码 |
|---|---|---|
| 高危动作 | publish / send-message / delete / spend / external-write / account-config 全部需要授权 | `UNKNOWN_ACTION` |
| 先自检后申请 | 验收门没有通过，不得发起申请 | `ACCEPTANCE_NOT_PASSED` |
| 绑定范围 | 一次批准只绑定一组（WorkItem, 动作, 目标, 载荷摘要） | `WORKITEM_MISMATCH` / `ACTION_MISMATCH` / `TARGET_MISMATCH` / `PAYLOAD_CHANGED` |
| 一次性 | 令牌兑现后作废，再发一次需要再批一次 | `ALREADY_CONSUMED` / `NO_APPROVAL` |
| 时效 | 默认 30 分钟过期 | `EXPIRED` |
| Agent 不得自批 | 以 `agent:` 开头的身份一律拒绝 | `AGENT_SELF_APPROVAL` |
| 伪授权 | 草稿已备、已上传、账号已配置、之前批过、长期配置、内容里的指令，**都不算授权** | `NON_AUTHORIZING_EVENT` |
| 批后改稿 | 批准后产出被修改，验收记录作废，兑现时拦截 | `ACCEPTANCE_NOT_PASSED` |
| Solo 模式 | 不需要任何组织或权限配置，单人身份即可批准 | — |
| Team 扩展 | 通过 `approver_policy` 注入角色校验，接口不变 | `APPROVER_NOT_ALLOWED` |

借鉴来源（只借鉴机制，未复制代码）：video-publisher-skill 的“准备、上传、配置不算授权”；self-media-content-workflow 的五处强制停点；Wechatsync 和 x-article-publisher 的“只出草稿，不自动发布”。

## 4. 规则 2：按需加载（`loader.SkillLoader`）

| 条款 | 规定 | 阻断码 |
|---|---|---|
| 默认空载 | 加载器启动时 0 个 Skill；Sprint 01 的 `Registry.loaded_skills == 0` 不变 | — |
| 按计划加载 | 只加载 `ExecutionPlan.steps` 中出现的 Skill | — |
| 上下文预算 | `max_loaded`（默认 4）；超出预算时整批不加载 | `CONTEXT_BUDGET` |
| 全有或全无 | 只要有一个被阻断，整个计划都不加载，避免半载状态 | — |
| 引用计数释放 | `release(plan)`；多个计划共用的 Skill 要等最后一个计划释放才卸载 | — |
| 能力发现 | 运行时探测环境（python/node/ffmpeg/git，可注入自定义探针）；缺能力时明确阻断，不静默失败 | `MISSING_CAPABILITY:<名>` |
| 许可证 | `SkillManifest.license / commercial_use`；商用模式下非商用许可一律阻断；研究模式（`commercial=False`）放行，供蒸馏学习 | `LICENSE_NONCOMMERCIAL` |
| 未注册 | 直接阻断 | `UNREGISTERED` |

借鉴来源：baoyu-skills 和 hyperframes 的“别全装，路由按需拉取”；self-media-content-workflow 的“运行时发现能力”。另外，Punk-Skill、video-talkcraft、yichen-skills 均为非商用许可，这是许可证阻断的直接动因。

## 5. 测试矩阵（新增 28 个，合计 46 个全绿）

- `evals/test_gates.py`：A01–A06 验收门，H01–H12 授权门
- `evals/test_loader.py`：L01–L10 加载器

## 6. 本次不做（留给 Sprint 03）

- Executor 真正执行对外动作（令牌已备好，由 Executor 消费）
- 审批持久化（当前在内存中；重启后需要重新审批，这是安全的默认行为）
- 证据链校验器（例如“数字必须带出处”）：接口已经开放，按 `validators` 注入即可
- 把 REVIEW / AWAITING_APPROVAL / DONE 正式写入 `WorkState`

## 7. Sprint 02b：接入内核（2026-10-09）

### 决策记录（按 sayelf-base 构建门禁）

1. 任务：把三条并行实现收敛成一条内核路径——规则层（本规格，c2d7437）、内核层（Actor/Project/Runtime，原云端会话方案，已存档）、桌面层（PR #1）。
2. 最接近的已有能力：三者本身；试合并仅 README/.gitignore 文本冲突，测试全绿。
3. Step 0：**Integrate**。不新建框架，不重写任何一层。
4. 可度量差异：Solo 四条不变式进入强制测试；审批从“三套各自实现”收敛为“Policy 管谁、HumanGate 管什么”一套。
5. 证据：`evals/test_kernel_integration.py`（K01–K07）+ 原有全部测试。
6. 不做：JSON 存储与本地网页工作台（与 PR #1 的 SQLite、桌面应用重复，舍弃）；HumanGate 持久化（Sprint 03，接 PR #1 的 SQLite 审批表）。
7. 回滚：本次为一个分支上的若干提交，`git revert` 即可；不涉及数据迁移。

### 接线点

| 位置 | 接入 |
|---|---|
| `Runtime.run` | 执行前 `SkillLoader.load_for_plan`，结束后 `release`；被阻断时记录 `skills-blocked` 并上报 |
| `READY` 之后 | `AcceptanceGate.check` 作为产出者自检（事件 `self-check`，actor=产出者）；与独立审核都通过才进入 APPROVED |
| 命中 Policy 门 | `HumanGate.request`，事件 `gate-requested` 带请求号与产出摘要 |
| `Runtime.decide` | 先 `Project.can_decide`（谁能批），再 `HumanGate.approve` + `authorize`（批的是什么）；交付事件带授权请求号 |
| `HumanGate.approver_policy` | 绑定 `Project.can_decide`；原 `agent:` 前缀检查保留为脱离 Project 单独使用时的兜底 |

### 本次发现并修复的缺陷

- 占位产出的类型取自计划步骤名（如 `wechat-adaptation`），与 SkillContract 声明的产出类型（`platform-package`）不一致。接入 AcceptanceGate 后被立即拦下；已改为取合同声明的类型。
- 明确标记 `placeholder=true` 的产出视为“结构存在”，可以通过自检，但在审核和人工裁决中始终显示为占位，不冒充成品。
