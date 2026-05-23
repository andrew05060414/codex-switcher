param(
  [string]$Provider,
  [string]$Model,
  [string]$CodexRoot = (Join-Path $HOME '.codex'),
  [string]$BaseUrl,
  [string]$WireApi = 'responses',
  [string]$ReasoningEffort,
  [string]$SubagentModel,
  [switch]$RequiresOpenAIAuth,
  [switch]$DisableResponseStorage,
  [switch]$BackupOnly,
  [switch]$RepairOnly,
  [switch]$RepairSessionTimesOnly,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir 'codex_switcher.py'

$argsList = @($pythonScript, '--codex-root', $CodexRoot)

if ($Provider) { $argsList += @('--provider', $Provider) }
if ($Model) { $argsList += @('--model', $Model) }

if ($BaseUrl) { $argsList += @('--base-url', $BaseUrl) }
if ($WireApi) { $argsList += @('--wire-api', $WireApi) }
if ($ReasoningEffort) { $argsList += @('--reasoning-effort', $ReasoningEffort) }
if ($SubagentModel) { $argsList += @('--subagent-model', $SubagentModel) }
if ($RequiresOpenAIAuth) { $argsList += '--requires-openai-auth' }
if ($DisableResponseStorage) { $argsList += '--disable-response-storage' }
if ($BackupOnly) { $argsList += '--backup-only' }
if ($RepairOnly) { $argsList += '--repair-only' }
if ($RepairSessionTimesOnly) { $argsList += '--repair-session-times-only' }
if ($DryRun) { $argsList += '--dry-run' }

& python @argsList
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
