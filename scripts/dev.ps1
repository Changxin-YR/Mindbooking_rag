[CmdletBinding()]
param(
    [switch]$Down,
    [switch]$WithApps,
    [switch]$Build,
    [switch]$Logs
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$composeFile = Join-Path $repoRoot 'infra/docker-compose.yml'
$envFile = Join-Path $repoRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    $envFile = Join-Path $repoRoot '.env.example'
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI was not found. Install Docker Desktop and retry.'
}

$composeArgs = @('-f', $composeFile, '--env-file', $envFile)
if ($WithApps) {
    $composeArgs += @('--profile', 'apps')
}

if ($Down) {
    & docker compose @composeArgs down
    exit $LASTEXITCODE
}

& docker compose @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed with exit code $LASTEXITCODE"
}

if ($Build) {
    & docker compose @composeArgs up -d --build
} else {
    & docker compose @composeArgs up -d
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Logs) {
    & docker compose @composeArgs logs -f
    exit $LASTEXITCODE
}

Write-Host "Local services started using $envFile"
