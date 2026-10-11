# Build decision: industry-specific AI role consolidation

1. **Real task:** Keep one shared Agent Ops kernel while deriving the fewest practical AI roles for each industry's actual deliverables; reconcile user role proposals against registered capabilities.
2. **Closest solutions:** The local Registry/Router/MinimumPlanner already selects roles by deliverable, composes explicit multi-output requests, and orders skills by accepted/produced outputs. Packs define reusable skill contracts. External agent frameworks orchestrate agents but do not justify duplicating this registry or converting a human org chart into agents. Existing role proposals are browser-only and do not affect routes.
3. **Step 0:** Improve.
3a. **Execution Verdict:** GO for a local-only, reversible role bundle overlay backed solely by registered skills; CLARIFY for any new skill implementation, tool, permission or cross-industry bundle.
4. **Measurable improvement:** A verified bundle combines at least two existing same-industry producer roles into one AI execution role (role reduction `N-1`) while preserving per-skill routing, dependency order, zero new executable skills, zero added tools, and independent reviewer separation. Bundles that do not reduce the role count are rejected.
5. **Success evidence:** Each skill has positive and negative examples; positive examples route to its cloned registered skill; negatives do not route to the custom role; aliases remain scoped to their registered industry; conflicting or redundant outputs are rejected; explicit compound work selects multiple bundle skills in dependency order; local persistence, restart loading and revoke are supported.
6. **Minimum Core:** Local validation and audit; one custom role contract with cloned contracts for selected existing skills; per-skill aliases; Router composition; revoke path.
7. **Plugin boundary:** Industry packs remain the canonical source of role/skill implementations. Reconciled role bundles are local overlays and never rewrite packs.
8. **Local-first:** Proposal text, examples and audit events stay in local SQLite; no model calls or network transfer.
9. **Data classification:** Suggestions/examples are Unknown and treated Sensitive. Credentials and arbitrary tool permissions are forbidden fields.
10. **Public release:** Yes; the user explicitly requested a GitHub update. Only this reviewed source, tests and documentation are classified `Public`; user role suggestions and local SQLite state are not included.
11. **External transfer:** Push the reviewed public source diff to `chuanxituzhu-lab/sayelf-agent-ops`; no local role data, user inputs, credentials or runtime artifacts are transferred.
12. **State/check:** `received → verified → applied` or `rejected`; applied overlays load on startup; revoke appends an audit event and removes role, skills and routes.
13. **Epistemic labels:** User proposal is input; registry structure and example routing are deterministic checks; those checks establish route consistency, not professional certification or execution quality.
14. **Evolution/rollback:** Additive local SQLite overlay and runtime route rules; revoke a single update or remove the overlay module to roll back. Canonical packs stay unchanged.
15. **WebUI:** Not required; use the host MCP tools and existing role registry.
16. **Simplest implementation:** Python standard-library SQLite plus current RoleContract, SkillContract, Registry, Router and planner; no new dependencies or orchestration frameworks.
17. **Explicitly not built:** Generic super-agent, copied human org charts, new skills/tools/permissions, model-based judging, automatic publication/deployment, cross-device sync, or silent changes to canonical industry packs.

## Principle profile

- **mandatory:** local data sovereignty, per-skill capability bounds, minimal-role routing, reviewer separation, positive/negative route evidence, audit history and rollback.
- **conditional:** human clarification when the proposal crosses industries, requires unregistered capabilities, combines a producer with its own reviewer, or lacks a safe route.
- **not applicable:** WebUI and external providers for this local MCP workflow.
- **blocked:** unregistered executable capability, authority increase, self-review consolidation, alias collisions, or redundant output contracts.
