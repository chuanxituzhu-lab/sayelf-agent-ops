# Build Decision Record: Software Role and Text-Driven Workflows

> Role-count decisions were refined by [Adaptive Minimum Professional Workflow](bdr-adaptive-minimum-workflow.md): bounded software tasks use developer + independent QA; architect is added only for cross-module/system design scope.

1. **Real task:** Let a user enter a software change request, route it to software roles, and receive a reviewable artifact from each role.
2. **Closest capabilities:** The local Registry/Router/MinimumPlanner/Runtime, per-industry packs, provider-neutral OpenAI-compatible adapter, and the existing media execution and approval evidence. LangGraph documents orchestrator-worker state and worker outputs; CrewAI provides sequential tasks with explicit outputs. Reuse the local kernel and adopt only the explicit state/role-output pattern. Sources: [LangGraph workflows and agents](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/workflows-agents.mdx), [CrewAI](https://github.com/crewAIInc/crewAI).
3. **Step 0:** Integrate.
3a. **Execution Verdict:** GO for a bounded, model-backed local artifact workflow; the repo already contains a partially implemented software pack and routing tests.
4. **Measurable difference:** A software request yields a role-attributed requirements/design artifact, implementation artifact, and QA report in one run; each output is persisted locally, declared non-placeholder, and independently checked before delivery. Missing model configuration or consent must never be reported as success.
5. **Success evidence:** Software feature request routes to the software team; a deterministic fake provider exercises each planned role and verifies output types, role attribution, review, local persistence, and refusal without consent. Existing routing and Solo invariants remain green.
6. **Minimum Core:** Software role contracts, route rules, role-aware sequential plan, structured software output handler, independent QA/reviewer gate, local artifact persistence, and a visible UI action.
7. **Plugin boundary:** Software Pack is isolated and loaded only for a software workspace; model provider remains replaceable. Media and engineering behavior stay in their packs.
8. **Local-first:** Request, source context, artifacts, and evidence stay on-device. A configured remote model receives only the bounded fields required after per-run consent.
9. **Data classification:** User text/source context is Unknown until classified and treated as Sensitive by default; credentials are Restricted and never included in model payloads or artifacts. Public status does not transfer user requests.
10. **Public release:** Yes; the user explicitly requested a GitHub update. Publish only the reviewed source, tests, and documentation classified `Public`; exclude user inputs, local outputs, and credentials.
11. **External transfer:** Push the reviewed `Public` repository diff to the configured GitHub origin. No task data or credentials are included. If a remote model is configured, show destination and exact text scope and require per-run consent; do not transmit local source files unless separately supported and disclosed.
12. **State/check:** `planned → executing → reviewed → delivered`; on missing inputs, provider failure, consent refusal, or review failure, stop and report the failed role. The current software run has no durable stage checkpoint, so the user must rerun from the beginning; completed packages are preserved. Recheck after model configuration, consent, or user edits.
13. **Epistemic labels:** Request requirements are user-provided facts; model-produced code/design are generated proposals; test results are facts only when locally executed and recorded; unexecuted test plans remain proposals.
14. **Evolution/rollback:** Additive Pack and handler; preserve the user's uncommitted software pack work; feature can be disabled by omitting the software pack/handler. Do not migrate or overwrite existing media data.
15. **WebUI:** Required because the user needs to enter text, see role assignment and outputs, configure a model, and review artifacts.
16. **Simplest implementation:** Extend the existing deterministic Router and Runtime with one sequential software plan and structured handlers using the current provider adapter; no new orchestration framework or dependency.
17. **Explicitly not built:** Arbitrary code execution, automatic writes into a source repository, deployment, external publishing, unrestricted agent spawning, parallel agent infrastructure, or automatic approval.

## Principle profile

- **mandatory:** shared-capability reuse, local data boundary, explicit external-model consent, deterministic role routing, state/evidence logging, independent review, rollback, truthful `planned`/`executed` states, and staged-publication gate.
- **conditional:** provider adapter and UI execution controls apply only when a model is configured; source-specific validation applies only when the user supplies project context.
- **conditional:** public publication is allowed only for explicitly `Public` source/docs/tests after staged-diff and leak review; deployment, package publishing, and cross-tenant collaboration are outside this slice.
- **blocked:** generated software must not execute or modify an arbitrary project path in this slice; the user receives a reviewable local artifact package.
