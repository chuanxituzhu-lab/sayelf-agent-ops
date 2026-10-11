# Software pack: Codex host execution

Release classification: Public. This change intentionally publishes the software routing pack and the Codex host execution contract, superseding the earlier local-only boundary for this limited capability. Other local-only work and model-backed software generation are excluded.

Build decision: Integrate. Reuse the existing local software pack, Registry, Router and MinimumPlanner. LangGraph and Microsoft Agent Framework were compared; no additional orchestration dependency is needed for this bounded host workflow.

The smallest addition is a generic code-change role and an additive host_execution contract in route_task. Success means general changes and specialist work route correctly, plans declare evidence requirements, and routing never executes code or calls a model. Core state transitions remain unchanged. Software packs remain optional; no new WebUI is required.

Repository contents, work inputs and execution evidence remain local (Internal/Unknown by default); only the source, tests and documentation listed in this release are Public. No credentials, automatic deployment, direct model integration, agent approval, or new orchestration framework are included. Rollback removes the generic role/rule and additive service contract; existing uncommitted work must be preserved.

## Host workflow

1. Call route_task with a repository-specific deliverable and acceptance criteria.
2. Read host_execution.steps and execute the authorized changes with Codex.
3. Record changed files, real checks and their results. Unrun checks are not_run.
4. Perform producer self-check and obtain independent review. If unavailable, report review_pending; different role names on the same actor are insufficient.
5. Show the result, verification evidence and limitations. External publishing/deployment needs specific human authorization.

Do not call run_task for this workflow. host_execution.status=planned is only a handoff, never proof of completed implementation. Evidence is reported by Codex; this slice does not add automatic persistence of host results to the workspace or claim that the existing model executor implements software changes.

Observation: local software specialists and registration already existed as uncommitted changes. Decision: integrate rather than overwrite. Verification trigger: any routing or execution-contract change requires the software routing tests and the repository evaluation suite. Authorization, local data boundaries, truthful evidence and rollback are mandatory. Public release is limited to the explicitly classified files in this change.
