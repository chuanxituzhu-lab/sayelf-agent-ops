# Sayelf Agent Ops

Sayelf（山野精灵）一人公司 Agent Ops。

> **最少岗位，专业闭环。**

## Sprint 01 Baseline

Sprint 01 intentionally implements only the minimum execution spine:

```text
User Input
→ WorkItem
→ Deliverable-first Router
→ Minimum Planner
→ Role + Skill
→ State Engine
→ READY
```

Implemented:

- WorkItem
- State Engine
- Role Registry
- Skill Registry
- Deliverable-first Router
- Minimum Planner
- 10 normal routing evals
- 5 confusion routing evals
- idle-registry and state-transition guards

Not implemented yet:

- Evidence
- Review
- Local Rework
- Risk
- Human Gate
- Executor
- Connector Runtime

## Core rules

1. Deliverable first, not keyword first.
2. Single-role first.
3. Minimum skill set.
4. Existing work is reused; it is not regenerated without need.
5. Installed roles are not automatically active.
6. Registered skills are not automatically loaded.
7. Media and Engineering responsibilities are isolated.
8. Cross-industry work is split into professional subtasks; no super-agent.

## Run demo

```powershell
python -m sayelf_agent_ops.demo
```

Expected first vertical slice:

```text
WorkItem: WI-0001
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
Excluded: media.creative-producer, media.growth-operator
State: READY
```

## Run tests

```powershell
python -m unittest discover -s evals -v
```

## Frozen Sprint 01 boundary

Do not add Review / Risk / Human Gate / Executor until Sprint 01 routing and state tests remain stable.
