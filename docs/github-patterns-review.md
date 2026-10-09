# GitHub pattern review — 2026-10-05

Scope: official repository READMEs, documentation and selected source surfaces; no upstream application was installed or benchmarked. This is a mechanism comparison, not an endorsement or production validation. Classification: Public, generic engineering research only.

| Project | Verified mechanism | Value for Sayelf | Decision |
| --- | --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Persisted state, durable execution and human interrupts | Validate accepted checkpoints before reuse; expose recovery after restart | Improve current runner; retain existing SQLite and Core |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Explicit agents, tasks and flow orchestration | Keep each role's responsibility and required output explicit | Reuse existing Role/Skill/Pack contracts; no framework migration |
| [Dify](https://github.com/langgenius/dify) | Workflow inputs, structured human input and resumed sessions | Review/edit/approve should be part of persisted execution state | Existing version-bound approval covers the first media slice; evaluate additional review routes only with a business case |
| [n8n](https://github.com/n8n-io/n8n) | Human review before selected tool calls, showing actual parameters | Future publishing/connectors need action-specific approval and exact arguments | Retain manual publishing; apply this contract when a real connector is added |
| [AgentOps](https://github.com/agentops-ai/agentops) | Session/agent/operation spans, usage and execution visibility | Local run timeline and usage summaries | Existing call IDs, usage and append-only events are reusable; expose summaries locally before considering an SDK |
| [Flowise](https://github.com/FlowiseAI/Flowise) | Explicit control paths, shared state and checkpointed human input | Show real stage state and clear input/output boundaries | Borrow state presentation; a node canvas is not justified for the current ordinary-user workflow |

## Workspace comparison

Observation: `desktop/runtime/media_workflow.py` already persists accepted stages, run events, versions and exact-content approvals. Resume checks the original input fingerprint, provider endpoint and model. Remote retries need fresh confirmation. Existing Core provides roles, skills and separately registered industry Packs.

Observation: cached stage reuse reads `output_json` but does not verify its stored `output_sha256` or reapply the stage output contract. A damaged checkpoint can therefore become downstream model input. This is the immediate, measurable reliability gap.

Observation: frontend identifiers are transient, while SQLite run IDs, stages and results survive restart. The desktop now lists local run metadata, reopens an exact run result, and safely recovers an abandoned `RUNNING` record after acquiring a per-workitem OS lock. Approval carries the selected result version through to the local package.

## Adoption order and acceptance

1. Implemented: verify checkpoint digest and output structure before reuse. Corrupt or structurally invalid checkpoints fail before any new provider call; valid checkpoints avoid rerunning accepted stages.
2. Implemented: local task history and restart recovery use the current SQLite records. The lock proves ownership; resume still checks the original input fingerprint and provider configuration, requests fresh consent for remote transfer, and reuses only accepted checkpoints.
3. Next scoped slice: a local evidence view showing stage status, call count and provider-reported tokens. Missing usage stays unknown; no fabricated cost estimate or remote telemetry.
4. When a real publishing connector exists: preview its exact account, destination, content version and parameters, bind approval to that call, and handle rejection without silently retrying.

No upstream source was copied, no dependency was added, and no license compatibility claim is made. Before copying code or distributing a dependency, inspect the exact revision's license and notices. Dify's repository identifies additional license conditions; n8n describes itself as fair-code, so availability on GitHub alone is not permission for unrestricted redistribution.

Primary evidence:
- [LangGraph durable execution and oversight](https://github.com/langchain-ai/langgraph#why-use-langgraph)
- [LangChain human-in-the-loop contract](https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/human-in-the-loop.mdx)
- [CrewAI crews](https://github.com/crewAIInc/crewAI/blob/main/docs/v1.12.2/en/concepts/crews.mdx)
- [Dify human-result resume and client responsibilities](https://github.com/langgenius/dify/blob/main/dify-agent/docs/dify-agent/user-manual/ask-human-layer/index.md)
- [n8n human review and actual tool parameters](https://github.com/n8n-io/n8n-docs/blob/main/docs/build/integrate-ai/ai-examples/human-in-the-loop-for-tools.md)
- [AgentOps session and operation tracking](https://github.com/agentops-ai/agentops)
- [Flowise AgentFlow V2 state and checkpoints](https://github.com/FlowiseAI/FlowiseDocs/blob/main/en/using-flowise/agentflowv2.md)

## Build Decision Record: checkpoint acceptance

1. Task: safely reuse accepted local stage results when resuming media generation.
2. Closest capability: existing SQLite stage cache and validator; LangGraph's persisted execution pattern.
3. Step 0: **Improve**.
3a. Execution Verdict: **GO**, limited to digest and output-contract checks.
4. Difference: corrupted or invalid cached results produce zero new provider calls.
5. Evidence: regression cases for digest mismatch, invalid structure with a matching digest, and valid accepted-stage reuse.
6. Minimum Core: unchanged; the desktop runner owns checkpoint acceptance.
7. Plugin boundary: provider-neutral adapter and industry Packs unchanged.
8. Local-first: validation uses local stored JSON and SHA-256; no network request.
9. Data: checkpoints are Sensitive; generic source, research and synthetic tests are Public after review.
10. Public release: reviewed source/docs/tests only, on the existing branch/PR; no installer release.
11. Transfer: only that reviewed Public diff to the already-authorized repository; no local task or runtime data.
12. State/check: invalid cache fails the run before reuse; next action is local diagnosis, not automatic regeneration.
13. Labels: Observation is the unchecked cache path; Hypothesis is downstream corruption risk; regression tests establish the implemented boundary.
14. Rollback: revert the focused source commit; no schema migration or user-data deletion.
15. WebUI: no new interface needed for this validation; existing error surface applies.
16. Implementation: existing hash and validator, standard library only.
17. Excluded: framework migration, autonomous publishing, cloud tracing, new agents and broad workflow builders.

Validation: 38 Python evaluations pass, including digest mismatch and invalid-schema checkpoints with zero new provider calls, plus valid-checkpoint reuse. Vite production build passes. No real model request was made. The previously generated Windows installer has not been rebuilt for this source change.

## Build Decision Record: local workflow history and restart recovery

1. Task: after reopening the desktop app, find recent media runs, reopen saved results, and safely resume failed or interrupted runs.
2. Closest capability: SQLite workflow/run/result tables and stage checkpoints already exist; LangGraph and Dify demonstrate persisted pause/resume; current desktop loses selected run IDs when the WebView restarts.
3. Step 0: **Integrate**.
3a. Execution Verdict: **GO**, using existing records and stdlib OS file locks; no workflow framework or schema expansion.
4. Difference: recoverable run IDs survive UI restart; an interrupted `RUNNING` run is recoverable only after an exclusive per-workitem lock proves its worker is gone; active runs remain untouched and two app instances cannot run the same work item concurrently. Reopening or approving a historical result is bound to its exact run/version.
5. Evidence: focused tests cover live-lock protection, stale-run recovery, resuming only unfinished stages, result reload, version-bound approval, and fresh remote consent at the existing UI gate.
6. Minimum Core: existing workflow record/checkpoint contract; UI history stays in desktop adapter.
7. Plugin boundary: provider, Core, industry Packs and role registry unchanged.
8. Local-first: run history and content are read from local SQLite and work item files; no network query.
9. Data: task names/requests/results are Sensitive and stay local; generic source, docs and synthetic tests are Public after review.
10. Public release: source/docs/tests only to the existing PR; no task data, databases, icons, installers or screenshots.
11. Transfer: only reviewed generic code and docs to the already-authorized GitHub repository; leak scan before push.
12. State/check: live lock means RUNNING/read-only; unlocked RUNNING becomes FAILED/INTERRUPTED; FAILED/BLOCKED may resume after normal input fingerprint and provider checks; result records reopen by exact run/version.
13. Labels: Fact — run IDs are only in WebView memory; Fact — SQLite keeps runs and results; Hypothesis — process lock release reliably signals worker exit, tested on supported Windows/macOS runtime APIs.
14. Rollback: additive hidden lock files under work item directories; no migration. Revert app code to roll back; existing DB rows and files stay intact.
15. WebUI: Required; history/reopen/resume needs an ordinary user action. Keep one card and the path open → select saved work → resume or view result.
16. Simplest implementation: existing runtime history query, exact-result read, per-workitem stdlib advisory lock, and current Tauri commands; no new dependency.
17. Explicitly not building: workflow canvas, cloud history sync, team inbox, completed-run analytics, automatic retry, or background job service.

Validation: all 41 Python evaluations pass, including multi-process live-lock protection, stale `RUNNING` recovery, local result reload, and exact-version approval. All 3 Rust tests pass, including bounded workflow ID validation. Vite production build and all 5 role recommender tests pass. The Windows x64 NSIS Setup builds locally (248.88 MiB, unsigned). No real model request or external content transfer was made. The macOS DMG still requires a native Mac build and remains unverified.
