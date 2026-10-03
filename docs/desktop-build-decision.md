# Desktop installer build decision — 2026-10-03

1. Task: add an installable desktop baseline around the frozen Sprint 01 Core, with no end-user Python, Node, Git, Docker, database setup or terminal.
2. Existing solutions: workspace/remote Sprint 01 at `f343bc5` (18/18 evals pass); Tauri 2 provides native shells, sidecars, NSIS and DMG; PyInstaller freezes Python and SQLite. Search: local project inventory, GitHub `tauri-apps/tauri`, PyInstaller documentation, Tauri distribution documentation. AgentOps observability projects solve a different task and are not replacements for this Core.
3. Step 0: **Integrate**. Connect existing Core, PyInstaller and Tauri; do not rebuild their engines.
3a. Execution Verdict: **GO**, limited to the installer baseline and local validation. Shipping signed production binaries has a separate platform acceptance gate.
4. Measurable difference: end-user prerequisite installs fall from Python + manual launch to zero developer tools; initialization and health checks become one desktop action; Core files remain byte-for-byte unchanged.
5. Evidence: 18 Core evals remain green; first launch/relaunch tests; missing/corrupt/future-schema rejection; frozen sidecar initializes and checks data with developer executables absent from PATH; native builds yield Setup.exe / architecture-specific DMG. Clean-machine GUI and signing checks must be recorded separately.
6. Minimum Core: frozen business Core. Packaging adapter owns only bootstrap metadata, directory initialization, SQLite health and Core smoke check.
7. Replaceable boundaries: Tauri shell; PyInstaller sidecar; platform bundle configuration and build scripts. No business rules in the installer.
8. Local boundary: data, metadata, health probes and preferences remain local. No application network services, telemetry, model calls or firewall changes.
9. Classification: existing public repository and newly authored generic source/docs/config/tests are **Public** after explicit diff/artifact review. User data, preferences, machine logs and credentials are **Internal/Sensitive**, excluded from upload. Unknown files stay local.
10. Public release: source branch/PR authorized by the user's repository implementation request. No public binary release or automatic deployment in this baseline.
11. Transfer: only reviewed Public source, generic test results and release metadata to `chuanxituzhu-lab/sayelf-agent-ops`; GitHub retains repository history. Dependency downloads use official package registries; no local data in requests. No user paths, diagnostic dumps or credentials in published artifacts. Review staged diff and source archive before transfer.
12. State: inspect → baseline → implement → validate → source review → repository delivery. Recheck after failures or source changes. Native build availability triggers platform validation; no recurring loop.
13. Fact: checked out Sprint 01 is Python, 18 tests pass. Observation: connector permission is read-only but local GitHub API reports push/admin. Inference: local authenticated Git can deliver the branch. Hypothesis: clean-machine installation succeeds, until demonstrated on each platform.
14. Evolution/rollback: additive branch and PR; retain base commit. No migrations beyond schema 1; refuse unknown future schemas; uninstall removes application only. Backup data before any later migration; downgrades do not silently rewrite data.
15. WebUI: **Required** as the embedded desktop setup/status surface for nontechnical users. Default path: open → choose industry → initialize → result; optional native folder selection. Advanced diagnostics use progressive disclosure. Team mode is visibly unavailable until implemented.
16. Simplest implementation: static HTML/CSS/JS (no frontend framework or Node runtime), Tauri 2 Rust commands, short-lived bundled Python sidecar with JSON response, stdlib SQLite. No daemon/port/process supervision required for this Sprint 01 baseline. Windows NSIS embeds offline WebView2; macOS uses system WebKit.
17. Not built: executor, cloud AI, updater, setup agents, background server, team accounts/firewall, external connectors, data deletion, universal cross-compiled Python binary, custom installer framework. Architecture-specific Mac packages are built on matching Mac hosts.

Sources:
- https://github.com/tauri-apps/tauri
- https://v2.tauri.app/develop/sidecar/
- https://v2.tauri.app/distribute/windows-installer/
- https://v2.tauri.app/distribute/dmg/
- https://pyinstaller.org/en/stable/operating-mode.html

## README product positioning and download decision — 2026-10-03

1. Task: make the repository homepage bilingual, explain the reusable Agent Ops Core and the first media-company vertical, and link each platform download to the latest release asset.
2. Closest existing capability: this repository's WorkItem, router, planner, role/skill registries, State Engine, and media/engineering routing examples. GitHub ecosystem scan: [agent-ops-stack](https://github.com/ellmos-ai/agent-ops-stack) describes manifest-driven local composition; [agent-ops](https://github.com/InfiniteRoomLabs/agent-ops) describes role/scenario-based agents and playbooks; [agents](https://github.com/wshobson/agents) describes a multi-harness plugin marketplace. These are useful evidence that composition patterns exist, but they do not replace this repository's deliverable-first workflow and desktop baseline. Source inspection found the gap: Sprint 01 keeps media and engineering definitions in the default Registry and Router, with no dynamically loadable Pack boundary yet.
3. Step 0: **Integrate**. Present the existing Core as a general product and media as the first business workflow. Document the Pack boundary as a target, not a completed runtime capability; engineering routing remains a baseline example. No new framework or Core is justified in this README/download scope.
4. Measurable difference: one Chinese/English homepage documents the same implemented scope and provides three architecture-specific stable download URLs; no industry-specific engine fork is introduced.
5. Success evidence: mirrored Chinese and English sections; all three URLs use GitHub's `/releases/latest/download/` route and match installer build names; implemented work and roadmap are explicitly separated. No release currently exists, so the README states that downloads become available after the first public release.
6. Public content: reviewed generic project positioning, build names, and repository release URLs only. No user data, local logs, credentials, build outputs, or unsigned binaries are transferred. No public binary release is created by this change.

## General Core and media-first Pack boundary — 2026-10-03

1. Task: make the existing Agent Ops workflow reusable across industries and register the self-media workflow as its first business Pack.
2. Closest solutions and gap: repository inspection showed media and engineering catalogs and keyword rules embedded in `registry.py` and `router.py`. Ecosystem scan above found manifest- and plugin-based agent collections, but they do not provide this repository's WorkItem / deliverable-first route contract. No new plugin framework is needed.
3. Step 0: **Improve**. Keep the frozen WorkItem, Planner, and State Engine; move industry roles, skills, and route predicates into separately registerable code Packs and let the generic Router evaluate registered rules. Keep cross-industry coordination as a workflow rule set.
4. Measurable difference: a new industry can be added by registering its Pack without editing Router or the existing media and engineering Packs. Existing Sprint 01 routes preserve their outputs; registered roles remain idle and skills remain unloaded.
5. Success evidence: all existing routing/state evals pass; a synthetic independent Pack registers in an empty Registry and routes its deliverable; evals also verify duplicate-pack and invalid role/skill rejection plus fail-closed equal-priority ambiguity.
6. Minimum Core: WorkItem and contract models, generic Registry validation, deterministic Router, Minimum Planner, and State Engine. No AI-based classifier or execution runtime.
7. Pack boundary: a Pack declares one industry, its roles, skills, and route rules. Cross-industry decomposition uses separately registered workflow rules. External directory discovery, third-party pack installation, and version negotiation are out of scope.
8. Local-first boundary: registration and routing happen in-process; the desktop data tree and SQLite health checks remain local. No network service or telemetry is added.
9. Data classification: Pack definitions, generic tests, and docs are **Public**. Local user tasks, outputs, evidence, logs, settings, and credentials are not part of Pack source and remain local.
10. Public release: continue the existing source-only draft PR. Do not publish installer binaries; Windows signing and both macOS native builds remain separate release requirements.
11. Transfer: only the reviewed source/doc diff and generic test evidence may update the existing public PR. Inspect staged files and secret patterns before push; no local user data or binaries are included.
12. State/check rule: baseline evals → extract Pack modules → register and validate → run evals → review staged public diff → update the same branch/PR. Any changed route output requires focused routing review.
13. Epistemic labels: Fact — current Sprint 01 has deterministic media and engineering routing. Fact — new Pack registration is tested with a third industry. Hypothesis — this boundary will make later industry additions cheaper; no third production Pack is included.
14. Evolution and rollback: additive modules and Registry API; revert the feature commit to restore the previous monolithic registry/router. No stored user-data migration.
15. WebUI: no change. Existing desktop setup/status UI remains the user interface; pack discovery and editing stay out of this slice.
16. Simplest implementation: Python dataclasses, explicit imports at application bootstrap, registered predicates with numeric priority, and stdlib tests. No new dependency or runtime plugin loader.
17. Not built: executor, AI routing, media-platform publishing, content generation, external Pack marketplace/loader, updater, team mode, or new industry pack beyond existing engineering examples.

## Brand icon integration — 2026-10-03

1. Task: integrate the user-provided Sayelf artwork as the desktop product logo and platform application icon.
2. Closest capability: the setup page had a text-only “S” mark; Tauri already owns Windows, macOS, and installer icon paths. Use that existing icon pipeline rather than adding an image or icon dependency.
3. Step 0: **Integrate**. Preserve the supplied artwork, add it to the desktop frontend and README, and generate the configured PNG / ICO / ICNS assets with the installed Tauri CLI.
4. Measurable difference: the same brand image appears in the setup header, browser/app favicon, Windows installer/app icon, macOS app icon, and repository homepage; no separate brand assets or runtime dependency are introduced.
5. Success evidence: verify the source asset and generated icon set; Vite production build includes the logo; Tauri/NSIS build succeeds; frozen Runtime and installer remain operational. macOS artifact generation still requires a native Mac builder.
6. Minimum implementation: one source PNG, one frontend image reference, existing configured icon slots, and a README image. No redesign or new branding system.
7. Boundaries: logo is a static frontend/package asset; it does not enter Core logic, runtime data, telemetry, or user task records.
8. Data classification: **Public product-brand asset**. The user supplied it specifically for use as the Sayelf product logo. The PNG has no text or EXIF metadata; publish only the logo and mechanically derived desktop icon sizes.
9. GitHub transfer: update the existing source PR and local branch only. Do not attach installer binaries or publish a release.
10. Verification state: inspect source and generated assets → build frontend and Windows installer → verify local package checksum and Authenticode status → stage and scan source diff → update PR.
11. Epistemic labels: Fact — the supplied PNG is 627×627 and opaque; generated sizes preserve its existing artwork. Fact — local Windows build is unsigned. Hypothesis — the round crop in the header remains legible at typical desktop sizes; verify in the packaged UI.
12. Rollback: revert the branding commit and restore the previous text mark and icon files; no stored-data migration.
13. WebUI: keep the current setup workflow; replace only its placeholder mark with the product logo.
14. Simplest path: existing Tauri icon generator, static public image, and CSS sizing. No external service, image-processing package, or generated artwork.
15. Not built: logo variants, background removal, animations, mobile branding, or public binary release.
