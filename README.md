# Sayelf Agent Ops

Sayelf（山野精灵）一人公司 Agent Ops。

> **最少岗位，专业闭环。**

## Sprint 01 Baseline

Sprint 01 intentionally implements only the minimum execution spine:

```text
User Input
→ WorkItem
→ Deliverable-first Router
→ Minimum Planner
→ Role + Skill
→ State Engine
→ READY
```

Implemented:

- WorkItem
- State Engine
- Role Registry
- Skill Registry
- Deliverable-first Router
- Minimum Planner
- 10 normal routing evals
- 5 confusion routing evals
- idle-registry and state-transition guards

Not implemented yet:

- Evidence
- Review
- Local Rework
- Risk
- Human Gate
- Executor
- Connector Runtime

## Core rules

1. Deliverable first, not keyword first.
2. Single-role first.
3. Minimum skill set.
4. Existing work is reused; it is not regenerated without need.
5. Installed roles are not automatically active.
6. Registered skills are not automatically loaded.
7. Media and Engineering responsibilities are isolated.
8. Cross-industry work is split into professional subtasks; no super-agent.

## Run demo

```powershell
python -m sayelf_agent_ops.demo
```

Expected first vertical slice:

```text
WorkItem: WI-0001
Industry: media
Deliverable: title-list
Role: media.content-planner
Skills: media.title-writing
Excluded: media.creative-producer, media.growth-operator
State: READY
```

## Run tests

```powershell
python -m unittest discover -s evals -v
```

## Desktop installer baseline

The Tauri 2 shell wraps the frozen Sprint 01 Core with a bundled Python sidecar. End-user machines need no Python, Node.js, Git, Docker, database server or terminal. First launch initializes and checks a local SQLite metadata store and the Core without starting a network service.

| Platform | Builder route | User artifact | Default data |
| --- | --- | --- | --- |
| Windows x64 | `installer/windows/build.ps1` on Windows x64 | `installer/windows/dist/Sayelf-Agent-Ops-Setup-x64.exe` (NSIS; offline WebView2 included) | `%LOCALAPPDATA%\Sayelf` |
| macOS Apple Silicon | `installer/macos/build.sh arm64` on Apple Silicon | `installer/macos/dist/Sayelf-Agent-Ops-macOS-arm64.dmg` | `~/Library/Application Support/Sayelf` |
| macOS Intel | `installer/macos/build.sh x64` on Intel | `installer/macos/dist/Sayelf-Agent-Ops-macOS-x64.dmg` | `~/Library/Application Support/Sayelf` |

Builder requirements and signing limits are in `installer/windows/README.md` and `installer/macos/README.md`. Each native build uses Python 3.12 and embeds it with PyInstaller. The app asks for an industry pack, creates `workitems/`, `outputs/`, `evidence/`, `logs/`, `backups/`, and `runtime.sqlite3`, then runs a database write/read, directory access, registry and Sprint 01 Core health check. Repeat initialization is safe. Unknown folders, corrupt data, future schema versions and attempts to change the pack in an existing data directory fail closed. App removal leaves data in place.

The UI reports registered roles with zero active roles and states that the executor and team mode are not available in Sprint 01. This baseline does not start a background server or configure a firewall.

The Core evaluation suite remains the same 18 cases. A local build is not a signed public release: Windows publisher signing and Apple signing/notarization belong to the release owner's credentialed process. Native macOS artifacts must be built on their matching architecture.

See `docs/desktop-build-decision.md` for the implementation boundary and release data classification.

## Frozen Sprint 01 boundary

Do not add Review / Risk / Human Gate / Executor until Sprint 01 routing and state tests remain stable.
