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
