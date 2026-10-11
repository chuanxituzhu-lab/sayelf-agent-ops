# Build decision: route Sayelf self-assessment and retain host-run evidence

1. **Real task:** A read-only request to assess Sayelf Agent Ops currently returns `UNROUTABLE_DELIVERABLE`; the connected MCP reports fewer industry packs than the local checkout. Establish a precise route to existing QA capability, verify the local MCP contract, and retain a truthful record of one host-executed run.
2. **Closest solutions:** The workspace already has `software.qa` / `software.test-and-review`, a deterministic test suite, MCP stdio integration tests, and host execution evidence requirements. Azure AgentOps emits local evaluation reports and evidence packs; the smaller `agent-ops` project uses inspectable receipts. Reuse these patterns; do not copy code or add a dependency. References: [Azure AgentOps evaluation report](https://github.com/Azure/agentops/blob/main/docs/tutorial-http-agent.md), [Azure AgentOps evidence pack](https://github.com/Azure/agentops/blob/main/docs/operate.md), [agent-ops receipts](https://github.com/nstranquist/agent-ops).
3. **Step 0:** **Integrate**. Route only explicit Sayelf Agent Ops self-assessment requests to the existing software QA skill and exercise the current local MCP server; resolve pack/version mismatch through configuration/restart guidance.
3a. **Execution Verdict:** **GO** for the bounded deterministic route, local MCP smoke test, and evidence record. **CLARIFY** before treating the separately connected MCP service as updated; its process/configuration is outside this checkout.
4. **Measurable improvement:** The reported self-assessment phrase moves from `UNROUTABLE_DELIVERABLE` to `software.qa` / `software.test-and-review`, while unrelated assessment requests remain unrouted. The local MCP handshake reports the same three packs as the current source. A host-run record carries the repository revision, route decision, validation result, and honest independent-review status.
5. **Success evidence:** Regression tests cover positive self-assessment routing, unrelated requests, current source pack discovery, and a real stdio `route_task` call. Run the suite and record its exact result plus host-side self-check. Independent review is a separate status and cannot be inferred from this run.
6. **Minimum Core:** One narrowly gated predicate reusing the existing QA route; source-to-MCP pack discovery check; one local run evidence record.
7. **Plugin boundary:** No new Pack, role, Skill, model, or orchestration framework. The QA skill remains owned by the software Pack; MCP remains a protocol adapter.
8. **Local-first:** Routing, tests, source inspection, and the evidence record run locally. No task text, artifacts, traces, or credentials are sent to a model or public service.
9. **Data classification:** Generic source, synthetic regression requests, and code/test evidence are `Public` after review. User work materials, credentials, and local runtime records remain `Sensitive`/`Restricted` and local.
10. **Public release:** Yes, continuing the user's standing request to update the repository; publish only reviewed source, synthetic tests, and this generic evidence record.
11. **External transfer:** Only the public staged source/docs/tests/evidence to the configured GitHub repository. No user input, local database, environment configuration, or secrets.
12. **State/check:** `observed → locally reproduced → routed → host-executed → self-checked → independent-review-pending` (or reviewed by a distinct reviewer). Recheck MCP pack discovery after restart/configuration changes.
13. **Epistemic labels:** MCP `UNROUTABLE_DELIVERABLE` and reported pack list are observations; stale process/configuration is an inference; the local route/test outcomes are facts only for the checked revision and environment. They do not prove production quality.
14. **Evolution / rollback:** Keep the route predicate isolated and reversible; rollback by removing its test-intent alias. No data migration. Do not declare the external MCP fixed until its own capability response matches the source.
15. **WebUI:** Not required; route through MCP and retain a text evidence record.
16. **Simplest implementation:** Extend the existing QA predicate and stdio test; no new dependency, role, database, service, or evaluation platform.
17. **Explicitly not built:** General-purpose self-scoring, automatic production certification, a second evaluator, new framework integration, or any claim that one local run establishes production effectiveness.

## Principle profile

- **mandatory:** truthful evidence/status, deterministic scoped routing, local data sovereignty, source-to-MCP version distinction, independent review separation, rollback.
- **conditional:** public transfer only after staged diff and artifact leak review.
- **not applicable:** remote models, WebUI, telemetry, deployment, installer changes.
- **blocked:** claiming the separately connected MCP is updated without restarting/verifying that process; claiming independent review from the producing host.
