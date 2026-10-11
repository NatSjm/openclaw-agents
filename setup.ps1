<#
.SYNOPSIS
  One-command setup of the research agent team on Windows (Docker Desktop).

.DESCRIPTION
  1. Creates the private file .local\openclaw.env from .env.example and
     generates the dashboard and A2A tokens.
  2. Stops so you can paste your OpenAI key and Telegram bot token privately.
  3. Installs the agent config into the Docker volume, registers the OpenAI
     key for every agent, and starts OpenClaw + Jaeger.

  Safe to run again at any time (for example after editing config/openclaw.json
  or adding the Telegram token): existing tokens, memory and sessions are kept.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$EnvFile = Join-Path $PSScriptRoot '.local\openclaw.env'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Agents = @('main', 'researcher', 'writer')

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

function Read-EnvFile($path) {
    $values = @{}
    foreach ($line in [IO.File]::ReadAllLines($path)) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
        $key, $value = $trimmed.Split('=', 2)
        $values[$key.Trim()] = $value.Trim().Trim('"').Trim("'")
    }
    return $values
}

function New-Token {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker $($args -join ' ') failed with exit code $LASTEXITCODE" }
}

Step 'Checking Docker'
docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop and run this script again.' }
Invoke-Docker compose version

Step 'Preparing private settings in .local\openclaw.env'
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot '.local') | Out-Null
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination $EnvFile
}
$lines = [IO.File]::ReadAllLines($EnvFile)
$changed = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    foreach ($name in @('OPENCLAW_GATEWAY_TOKEN', 'A2A_CLIENT_TOKEN')) {
        if ($lines[$i] -eq "$name=") { $lines[$i] = "$name=$(New-Token)"; $changed = $true }
    }
}
if ($changed) {
    [IO.File]::WriteAllText($EnvFile, (($lines -join "`n") + "`n"), $Utf8NoBom)
    Write-Host 'Generated the dashboard token and the A2A client token.'
}
$values = Read-EnvFile $EnvFile
if (-not $values['OPENAI_API_KEY']) {
    Write-Host ''
    Write-Host 'Opening .local\openclaw.env in Notepad.' -ForegroundColor Yellow
    Write-Host 'Paste your OPENAI_API_KEY (and TELEGRAM_BOT_TOKEN if you have it), save, close Notepad,'
    Write-Host 'then run this script again. Do not share these values anywhere.'
    Start-Process notepad.exe -ArgumentList "`"$EnvFile`""
    exit 0
}
if (-not $values['TELEGRAM_BOT_TOKEN']) {
    Write-Host 'TELEGRAM_BOT_TOKEN is empty: the team will work in the dashboard; add the token and rerun for Telegram.' -ForegroundColor Yellow
}

Step 'Pulling pinned images (first run downloads about 3.5 GB)'
Invoke-Docker compose pull

Step 'Installing the agent team config into the OpenClaw volume'
Invoke-Docker compose run --rm --no-deps --user 0 --entrypoint python3 openclaw /project/docker/init.py

Step 'Installing the pinned web search plugin (Parallel Search, key-free)'
Invoke-Docker compose run --rm --no-deps --entrypoint sh openclaw -c "openclaw plugins list 2>/dev/null | grep -q parallel-plugin && echo 'Already installed.' || openclaw plugins install @openclaw/parallel-plugin@2026.9.8"

Step 'Registering the OpenAI API key for each agent (read from the private env file, never printed)'
foreach ($agent in $Agents) {
    Invoke-Docker compose run --rm --no-deps --entrypoint sh openclaw -c "printf '%s\n' `${OPENAI_API_KEY} | openclaw models auth paste-api-key --provider openai --agent $agent >/dev/null && echo 'OpenAI key saved for $agent'"
}

Step 'Starting OpenClaw and Jaeger'
Invoke-Docker compose up -d --force-recreate
Write-Host 'Waiting for the OpenClaw gateway to become healthy (first start can take 3-5 minutes)...'
$healthy = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri 'http://127.0.0.1:18789/healthz'
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 3
}
if (-not $healthy) { throw 'Gateway did not become healthy. Inspect: docker compose logs --tail=80 openclaw' }

Step 'Done'
Write-Host 'Dashboard (OpenClaw Control UI): http://127.0.0.1:18789'
Write-Host '  Log in with OPENCLAW_GATEWAY_TOKEN from .local\openclaw.env (open it in Notepad; do not paste it in chat).'
Write-Host 'Tracing (Jaeger UI):              http://127.0.0.1:16686   service: openclaw-research-team'
Write-Host 'Next: follow README.md section "Run the scenario".'
