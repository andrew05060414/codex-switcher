$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

param(
  [Parameter(Mandatory = $true)][string]$Provider,
  [Parameter(Mandatory = $true)][string]$Model,
  [string]$CodexRoot = "$HOME\.codex",
  [string]$BaseUrl,
  [string]$WireApi = 'responses',
  [string]$ReasoningEffort,
  [string]$SubagentModel,
  [switch]$RequiresOpenAIAuth,
  [switch]$DisableResponseStorage,
  [switch]$BackupOnly,
  [switch]$RepairOnly,
  [switch]$DryRun
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir 'codex_switcher.py'

$argsList = @(
  $pythonScript,
  '--provider', $Provider,
  '--model', $Model,
  '--codex-root', $CodexRoot
)

if ($BaseUrl) { $argsList += @('--base-url', $BaseUrl) }
if ($WireApi) { $argsList += @('--wire-api', $WireApi) }
if ($ReasoningEffort) { $argsList += @('--reasoning-effort', $ReasoningEffort) }
if ($SubagentModel) { $argsList += @('--subagent-model', $SubagentModel) }
if ($RequiresOpenAIAuth) { $argsList += '--requires-openai-auth' }
if ($DisableResponseStorage) { $argsList += '--disable-response-storage' }
if ($BackupOnly) { $argsList += '--backup-only' }
if ($RepairOnly) { $argsList += '--repair-only' }
if ($DryRun) { $argsList += '--dry-run' }

& python @argsList
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
