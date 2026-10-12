# Build Decision Record: v1.5 workflow fusion

1. **Real task** — Combine the supplied `sayelf-agent-ops-workflow-v1.5.zip` with the current local Agent Ops so a routed job has a minimal, inspectable division sheet and a truthful Codex host-evidence boundary.
2. **Closest solutions** — The archive supplies a five-pattern workflow vocabulary, session/memory separation, stop rules and a static division-sheet checklist. The local Core already has Router, MinimumPlanner, role/skill contracts, state/evidence events, independent review and Human Gate.
3. **Step 0 classification** — **Improve / GO**. This is a bounded improvement to the existing routing handoff, not a second workflow skill or runtime.
4. **Measurable difference** — Every successful `route_task` now returns a machine-readable `workflow_contract`, a deterministic validation result, and a host evidence template. A single-step request stays one `agent-as-tool`; explicit dependent work is `sequential`; neither plan nor template can claim execution.
5. **Success evidence** — Focused contract tests cover single-step minimality, compound ordering, loop/reviewer rejection, review-pending evidence and verified evidence. The full local eval suite must remain green.
6. **Minimum Core** — Reuse `RoutingDecision`, `ExecutionPlan`, `RoleContract`, `SkillContract`, current state transitions and Human Gate. Add only `workflow_contract.py` and additive service/MCP fields.
7. **Plugin boundaries** — Industry packs continue to own roles, skills and route rules. The contract layer cannot create skills, tools, permissions or roles.
8. **Local-first boundary** — Task text, outputs, role overlays and host evidence stay in the local workspace. Contract generation and validation make no network or model call.
9. **Data classification** — Source code, synthetic tests and this BDR are Public after staged review. User requests, attachments, outputs, logs, evidence and settings are Internal/Sensitive; credentials are Restricted.
10. **Transfer/public release** — Only reviewed source, tests and generic documentation may enter GitHub. Before publication inspect staged names, contents and secret/personal-path patterns; never include local databases or run evidence.
11. **State/check rule** — `route_task` is `planned`; host evidence starts `not_run`; missing independent review is `review_pending`; only a complete evidence envelope can be `verified`. No plan state is treated as delivery.
12. **Epistemic labels** — User task is a source fact; route and minimum-role choice are deterministic inferences; host execution, changed files, verification and independent review remain unverified until recorded.
13. **Evolution/rollback** — The contract is additive and versioned (`workflow-contract-v1`, `host-execution-evidence-v1`). Reverting the change leaves existing role, work-item and approval data readable; no migration or deletion is introduced.
14. **WebUI decision** — No new WebUI is needed for this fusion. The existing path remains `Open → Input → Execute → Result`; the contract is available to the current WebUI/host as progressive detail.
15. **Simplest implementation** — Pure standard-library dictionaries and deterministic checks, exposed through the service and read-only MCP validation tools. No LangGraph, Microsoft Agent Framework, model provider or background scheduler.
16. **Explicitly not built** — No parallel executor, unbounded loop, long-term memory bank, automatic publishing/deployment, external telemetry, or automatic role invention.
17. **Rollback trigger** — If routing regressions, reviewer-separation failures, public-diff leaks or a test failure appear, stop publication and revert this additive slice; retain local evidence for inspection.

## Resulting host path

```text
route_task
  → workflow_contract + workflow_validation
  → Codex executes listed local steps
  → validate_host_execution_evidence
  → independent review / human gate when required
  → local delivery evidence
```
