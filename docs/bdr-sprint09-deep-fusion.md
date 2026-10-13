# Build Decision Record: Sprint 09 Deep Fusion

1. **Real task:** Bring the Sprint 09 snapshot's useful local file intake and product workbench entry into the current shared Agent Ops core, while preserving the current minimum-role router, reversible role overlays, `route_task` host contract, independent review, and human approval gates.
2. **Closest solutions:** The current Workspace API already provides identity, work items, human tasks, approvals, persistence, and evidence. The Sprint 09 snapshot adds a standard-library local console and bounded file intake. Codex host execution is already defined by the current `route_task` contract; the snapshot's alternate `run_task` host loop and provider gateway are outside this fusion.
3. **Step 0 classification:** **Integrate** — connect existing Workspace API capabilities with the snapshot's local console and secure file intake; do not create a second runtime or replace the current service.
3a. **Execution verdict:** GO for an additive, local-only slice; NO-GO for copying the snapshot's alternate service, model gateway, compiled build output, or `run_task` execution loop.
4. **Measurable difference:** A user can open a local workbench, attach bounded text/spreadsheet/document/image files, preview the existing route, submit one work item, and inspect the resulting role chain and evidence without exposing file contents or tokens to logs or public services.
5. **Success evidence:** Focused tests cover safe file names/types, size and archive/XML limits, text extraction, content-hash identity, upload/download authorization, console security headers/no directory listing, route preview, and additive persistence compatibility; the pre-existing full suite remains green.
6. **Minimum Core:** Existing registry/router/planner/workflow contract/runtime/workspace identity and approval rules; one secure local file store; one thin static console; additive API routes.
7. **Plugin boundary:** File parsers are local intake adapters only. Industry packs and registered skills remain canonical. No uploaded file may create a role, skill, executable handler, or permission. Codex remains the execution host through `route_task`; the console only submits and displays.
8. **Local-first boundary:** Files, extracted text, route plans, work items, outputs, and evidence stay under the configured local home. The console binds to loopback. No OCR, remote model, gateway, or external upload is added by this change.
9. **Data classification:** User text and attachments are `Unknown` and treated as `Sensitive`; tokens/credentials are `Restricted`; source code and tests in this repository are `Public` only after staged-diff review. File views expose metadata and hashes, not full contents.
10. **GitHub/public release:** Allowed for reviewed source, tests, docs, and static UI only. Exclude the supplied ZIP, extracted review directory, local workspace state, uploaded files, compiled `target` artifacts, and secrets.
11. **State/check rule:** `received → classified → route-previewed → submitted → executed-by-host → reviewed → closed`; a failed parser, missing capability, or missing host evidence remains visible and cannot claim completion.
12. **Epistemic labels:** Archive behavior is reference evidence; route decisions are proposals until validated; file metadata/hash is a local fact; extracted text is a parser result with format limits; delivery is a fact only after current acceptance, independent review, and human gate rules pass.
13. **Evolution/rollback:** All changes are additive. Disable the console or file routes independently, remove the new package files, and keep existing state files readable. Do not migrate existing work-item snapshots unless a backward-compatible default is sufficient.
14. **WebUI decision:** Required. Use the ordinary flow `Open → Input/Attach → Route preview → Execute/inspect → Result`, with technical settings hidden behind existing token/API configuration.
15. **Simplest implementation:** Add `files.py`, optional attachment metadata on `WorkItem`, local file methods and API routes, then the snapshot's static console adapted to the current API. Use only the Python standard library and existing tests.
16. **Explicitly not built:** A second service implementation, LangGraph/Microsoft Agent Framework runtime, unrestricted agent spawning, remote provider integration, OCR/PDF semantic extraction, automatic publishing, or automatic role/skill mutation from file contents.
17. **Stop triggers:** Stop and report if existing route/evidence tests regress, if an upload can escape the workspace or leak contents, if the console requires a remote origin, or if the archive's code cannot be integrated without replacing current invariants.

## Principle profile

- **mandatory:** local trust boundary, fail-closed file validation, content-hash identity, existing role/workflow/evidence contracts, independent review, truthful UI status, rollback.
- **conditional:** text extraction applies only to supported safe formats; opaque file metadata remains available for unsupported formats.
- **not_applicable:** external model gateway and framework orchestrator; no provider is needed for this fusion.
- **blocked:** unsupported file format, unsafe archive/XML, missing host execution evidence, or a non-local origin.
