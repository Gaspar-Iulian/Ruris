param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [string]$EnvFile,
    [string]$ProjectName,
    [string]$DockerExe
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ComposeTools.ps1')
$context = Get-RurisComposeContext -EnvFile $EnvFile -ProjectName $ProjectName -DockerExe $DockerExe
$source = (Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $source 'objects') -PathType Container)) { throw 'Sursa nu contine directorul objects.' }
$running = @(Invoke-RurisCompose $context @('ps', '--status', 'running', '--services'))
if (@($running | Where-Object { $_ -in @('api', 'web', 'notification-worker') }).Count) {
    throw 'Opreste serviciile aplicatiei inainte de importul fisierelor.'
}
Invoke-RurisCompose $context @('run', '--rm', '--no-deps', '--volume', "${source}:/import:ro", 'maintenance', '/ops/import-attachments.sh')
Invoke-RurisCompose $context @('run', '--rm', '--no-deps', 'api', 'python', '-m', 'flask', '--app', 'app', 'check-attachments')
