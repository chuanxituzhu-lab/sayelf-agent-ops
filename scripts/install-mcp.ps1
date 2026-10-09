# Sayelf Agent Ops - register the local MCP entry for Codex and Claude Code.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File D:\Codex\skills\sayelf-agent-ops\scripts\install-mcp.ps1
# Safe to re-run: skips what is already registered; backs up Codex config.toml before changing it.

# Native tools (pip, claude) write warnings to stderr; with "Stop", Windows PowerShell 5.1
# would turn those into terminating errors. Every step checks $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Name = "sayelf-agent-ops"
function Ok($m)   { Write-Host "[ OK ] $m" -ForegroundColor Green }
function Skip($m) { Write-Host "[SKIP] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

# 1. Python 3.11+
$PyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PyCmd) { Fail "python not found (need 3.11+)" }
$Py = $PyCmd.Source
& $Py -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { Fail "Python 3.11+ required: $Py" }
Ok "python: $Py"

# 2. Optional dependency: the official MCP Python SDK
& $Py -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('mcp') else 1)"
if ($LASTEXITCODE -ne 0) {
    & $Py -m pip install --user "mcp>=1.2"
    if ($LASTEXITCODE -ne 0) { Fail "pip install mcp failed" }
}
Ok "mcp SDK installed"

# 3. Smoke test: the server module imports from the repo
Push-Location $Repo
try {
    & $Py -c "import sayelf_agent_ops.mcp_server as m; m.build_server()"
    if ($LASTEXITCODE -ne 0) { Fail "MCP server failed to load" }
} finally { Pop-Location }
Ok "MCP server loads"

# 4. Codex: append [mcp_servers.sayelf-agent-ops] to config.toml (with backup)
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { "D:\Codex" }
$Config = Join-Path $CodexHome "config.toml"
if (Test-Path $Config) {
    $Text = Get-Content -Raw -Encoding UTF8 $Config
    if ($Text -match "(?m)^\[mcp_servers\.$([regex]::Escape($Name))\]") {
        Skip "Codex already has [mcp_servers.$Name]"
    } else {
        $Backup = "$Config.bak-sayelf-agent-ops-$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $Config $Backup -ErrorAction Stop
        $Block = @"

[mcp_servers.$Name]
command = '$Py'
args = ['-m', 'sayelf_agent_ops.mcp_server']
cwd = '$Repo'
startup_timeout_sec = 60
"@
        [System.IO.File]::AppendAllText($Config, $Block, (New-Object System.Text.UTF8Encoding($false)))
        Ok "Codex registered (backup: $Backup)"
    }
} else { Skip "Codex config not found at $Config" }

# 5. Claude Code: user scope
$Claude = Get-Command claude -ErrorAction SilentlyContinue
if ($Claude) {
    & claude mcp get $Name *> $null
    if ($LASTEXITCODE -eq 0) {
        Skip "Claude Code already has $Name"
    } else {
        & claude mcp add --env "PYTHONPATH=$Repo" --transport stdio --scope user $Name '--' $Py -m sayelf_agent_ops.mcp_server
        if ($LASTEXITCODE -ne 0) { Fail "claude mcp add failed" }
        Ok "Claude Code registered (user scope)"
    }
} else { Skip "claude CLI not found; Claude Code not registered" }

Write-Host ""
Write-Host "Done. Restart Codex / Claude Code to load the tools." -ForegroundColor Cyan
Write-Host "Human approval (terminal only):  cd $Repo; python -m sayelf_agent_ops.approve_cli list"
