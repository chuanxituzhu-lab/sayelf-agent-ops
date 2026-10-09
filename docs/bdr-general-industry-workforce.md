# Build Decision Record: General Industry Workforce Blueprint

1. **Real task:** Let a user describe any industry/business and its typical work during first setup, then produce a small role-owned workflow with responsibilities, inputs, outputs, and acceptance checks. Existing industry packs are examples and executable catalogs, not the product boundary.
2. **Closest capabilities:** The local Router, Registry, MinimumPlanner, and media/engineering/software packs already assemble registered roles; current WebUI only filters registered roles and rejects unknown industries. LangGraph documents orchestrator-worker decomposition; CrewAI documents role/task contracts; AgentWork and LinkWork provide reusable role templates and workflow management. Reuse the local contracts and status/evidence conventions; do not add another orchestration framework. Sources: [LangGraph workflows and agents](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/workflows-agents.mdx), [CrewAI collaboration](https://github.com/crewAIInc/crewAI/blob/main/docs/v1.13.0/en/concepts/collaboration.mdx), [AgentWork](https://github.com/agentwork-ai/agentwork), [LinkWork](https://github.com/momotech/LinkWork).
3. **Step 0:** Differentiate.
3a. **Execution Verdict:** GO for a local, deterministic, reviewable role blueprint and setup intake. Existing executor capabilities remain pack-bound; this change does not claim unregistered skills can execute work.
4. **Measurable difference:** Any non-empty user-entered industry/business can produce a minimum two-role plan (professional producer + independent reviewer), with structured responsibility/input/output/acceptance fields; named deliverables refine the plan. No industry-package selection is required to create the plan.
5. **Success evidence:** Focused tests cover arbitrary industries, simple vs compound requests, output-specific refinement, missing/oversized input, local-only profile handling, and clear distinction between proposed roles and activated/executable registered roles.
6. **Minimum Core:** Local text intake; deterministic blueprint composer from reusable role templates; minimum 2-role producer/reviewer closure; output and acceptance contracts; visible status that distinguishes proposal from activated/executed work.
7. **Plugin boundary:** Existing industry packs remain optional demonstration/execution plugins. Provider/model adapters remain replaceable and are not needed for local baseline planning.
8. **Local-first:** Industry and workflow text, blueprint, and evidence stay in the local app/workspace. No model request or network call is made by blueprint generation.
9. **Data classification:** Industry/business description and work request are `Unknown` at intake and treated as `Sensitive`; keep local. Credentials are `Restricted` and excluded. No external transfer.
10. **Public release:** Yes; the user explicitly requested a GitHub update. Publish only the reviewed source, tests, and documentation classified `Public`; exclude user inputs, local outputs, and credentials.
11. **External transfer:** Push the reviewed `Public` repository diff to the configured GitHub origin. No task data or credentials are included.
12. **State/check:** `draft → generated → reviewed`; the blueprint is only a proposal. Activation/execution requires an existing registered capability and any applicable consent. Recompute when either input or selected demo pack changes.
13. **Epistemic labels:** User text is the source fact; template matching is a deterministic inference; a proposed role/output is a plan, not evidence of execution or delivered work.
14. **Evolution / rollback:** Additive UI/model changes; profile text stays in local browser storage and does not alter the workspace schema; rollback by hiding the generic blueprint section and using the existing pack selector and role registry.
15. **WebUI:** Required because the actual task is first-run, user-entered workflow setup; keep the path `Open → Input → Execute → Result` and expose capability/activation state plainly.
16. **Simplest implementation:** Reuse current Tauri setup flow and JavaScript modules; add a small pure local blueprint composer and focused Node tests; no new dependency, model, or orchestration framework.
17. **Explicitly not built:** Runtime-created executable skills, arbitrary tool permissions, automatic external actions/publication, model calls, automatic project/file mutation, or claims that unknown-industry work has been executed.

## Principle profile

- **mandatory:** local data sovereignty, truthful proposal/execution state, independent review, smallest role count, registered-capability checks, rollback.
- **conditional:** existing-pack role activation and model execution only when the user selects a supported pack and explicitly configures/approves the corresponding capability.
- **conditional:** public publication is allowed only for explicitly `Public` source/docs/tests after staged-diff and leak review; cloud generation, telemetry, deployment, and multi-tenant execution remain outside scope.
- **blocked:** any claim to activate or execute a proposed role where no matching registered role/skill/executor exists.
