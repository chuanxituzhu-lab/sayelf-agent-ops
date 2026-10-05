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

Observation: frontend work item/run identifiers live in memory; the UI has no history/recovery entry point after restart. Backend checkpoint persistence alone does not complete the ordinary-user recovery workflow. This remains a named follow-up, not an implemented feature.

## Adoption order and acceptance

1. Implement now: verify checkpoint digest and output structure before reuse. Corrupt or structurally invalid checkpoints must fail before any new provider call; valid checkpoints must continue to avoid rerunning accepted stages.
2. Next scoped slice: local task history and recovery after restart, using current SQLite records. Acceptance: restart, select a failed run, confirm remote transfer again, and execute only the unfinished stages. Interrupted `RUNNING` runs need an explicit ownership/recovery policy before they can be resumed.
3. Then: a local evidence view showing stage status, call count and provider-reported tokens. Missing usage stays unknown; no fabricated cost estimate or remote telemetry.
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
