[CmdletBinding()]
param(
    [switch]$SkipComposeConfig
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-PathExists([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Expected path was not found: $Path"
    }
}

function Assert-Contains([string]$Path, [string]$Pattern) {
    if (-not (Select-String -LiteralPath $Path -Pattern $Pattern -Quiet)) {
        throw "Expected '$Pattern' in $Path"
    }
}

$compose = Join-Path $repoRoot 'infra/docker-compose.yml'
$nginx = Join-Path $repoRoot 'infra/nginx/nginx.conf'
$devScript = Join-Path $repoRoot 'scripts/dev.ps1'
$workflow = Join-Path $repoRoot '.github/workflows/ci.yml'

Assert-PathExists $compose
Assert-PathExists $nginx
Assert-PathExists $devScript
Assert-PathExists $workflow

foreach ($service in @('mysql:', 'redis:', 'rabbitmq:', 'opensearch:', 'clickhouse:', 'minio:', 'backend:', 'reader:', 'writer:', 'admin:', 'nginx:')) {
    Assert-Contains $compose ([regex]::Escape($service))
}

$composeHealthchecks = (Select-String -LiteralPath $compose -Pattern '^    healthcheck:' -AllMatches).Matches.Count
if ($composeHealthchecks -lt 11) {
    throw "Expected healthchecks for all local services; found $composeHealthchecks"
}

foreach ($route in @('/api/v1/', '/writer/api/v1/', '/admin/api/v1/')) {
    Assert-Contains $nginx ([regex]::Escape($route))
}

Assert-Contains $devScript 'docker compose'
Assert-Contains $workflow 'docker compose'
Assert-Contains $workflow 'config --quiet'

if (-not $SkipComposeConfig) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw 'Docker CLI is required for compose validation. Use -SkipComposeConfig only for static checks.'
    }

    & $docker.Source compose -f $compose --env-file (Join-Path $repoRoot '.env.example') config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose config failed with exit code $LASTEXITCODE"
    }

    & $docker.Source compose -f $compose --env-file (Join-Path $repoRoot '.env.example') --profile apps config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose apps config failed with exit code $LASTEXITCODE"
    }
}

Write-Host 'Foundation validation passed.'
