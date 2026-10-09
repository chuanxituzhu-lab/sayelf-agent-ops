# Build Decision Record: Adaptive Minimum Professional Workflow

1. **Real task:** Given a user's professional work request, determine which registered skills and roles are necessary, assemble the smallest complete workflow, and show the role-owned work results and closure checks.
2. **Closest capabilities:** Local Registry, Router, MinimumPlanner, pack route rules, skill input/output contracts, independent review and provider consent. LangGraph supplies stateful orchestrator-worker patterns; AutoGen provides dynamic participant selection but can involve a shared conversation among participants. Reuse local route/skill contracts and deterministic dependency ordering; do not add either runtime. Sources: [LangGraph](https://github.com/langchain-ai/langgraph), [AutoGen SelectorGroupChat](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_selector_group_chat.py).
3. **Step 0:** Integrate.
3a. **Execution Verdict:** GO for local-first adaptive assembly over the currently registered industry packs.
4. **Measurable difference:** A single-destination request uses only the registered skill route it needs; explicit compound requests include all matching deliverables, ordered by declared input/output dependencies, and exclude duplicate skills/roles. Software feature plans omit the separate architecture step for clearly bounded changes while retaining implementation and independent QA; architecture remains for cross-cutting/explicit design work.
5. **Success evidence:** Golden cases for simple, compound, ambiguous, and unsupported requests assert minimum distinct role count, complete declared output coverage, dependency order, independent QA, and no off-catalog role invention.
6. **Minimum Core:** Existing registry as capability catalog; pack-declared bounded workflow selection; deterministic dependency ordering and assembly validation; role-attributed workflow and outputs; explicit blocked/clarify responses; local run evidence.
7. **Plugin boundary:** Each industry pack continues to own its roles, skills, outputs, and domain handlers; model/provider remains replaceable; no role is created at runtime.
8. **Local-first:** Input persistence, matching, dependency planning, validation, results, and evidence remain local; no model call is added to workflow planning.
9. **Data classification:** Request and attachments are `Unknown` and handled as `Sensitive`; credentials are `Restricted` and never included in prompts; generated results are local until user export.
10. **Public release:** Yes; the user explicitly requested a GitHub update. Publish only the reviewed source, tests, and documentation classified `Public`; exclude user inputs, local outputs, and credentials.
11. **External transfer:** Push the reviewed `Public` repository diff to the configured GitHub origin. No task data or credentials are included. The existing per-run model consent still governs later content/code generation.
12. **State/check:** `received → classified → assembled → validated → planned → executed → reviewed → closed`; unknown scope or unsupported capability returns `CLARIFY/BLOCKED`; only verified required results can close the run. Re-evaluate on scope, result, provider, consent, or catalog change.
13. **Epistemic labels:** User-specified outputs are facts; model-suggested decomposition is a proposal; workflow validation is a fact about structural coverage only; generated work and tests are complete only when their own acceptance evidence passes.
14. **Evolution / rollback:** Additive assembly layer with versioned plan metadata; preserve prior local edits and data; revert by disabling adaptive assembly and retaining existing deterministic routes.
15. **WebUI:** Required; the existing task entry and result panels are the natural place to show the minimum role chain, missing inputs, status, and artifacts.
16. **Simplest implementation:** Reuse current Python core and provider adapter; add bounded planner/validator and thread the existing per-run consent through intake; no agent framework or new dependency.
17. **Explicitly not built:** Runtime role creation, unrestricted agent spawning, uncontrolled group chat/loops, external publication, automatic source/project mutation, or claims of task closure without result evidence.

## Principle profile

- **mandatory:** minimum registered skill set, data sovereignty, explicit remote consent, schema/ownership validation, independent review where required, local evidence, truthful status and rollback.
- **conditional:** attachment-specific routes apply only when attachments are supplied; model generation remains conditional on configuration and per-run consent.
- **conditional:** public publication is allowed only for explicitly `Public` source/docs/tests after staged-diff and leak review; deployment and cross-tenant execution remain outside scope.
- **blocked:** unknown/unregistered professional capabilities; the planner must request clarification or report the gap rather than invent a role.
