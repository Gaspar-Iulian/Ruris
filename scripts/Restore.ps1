param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$BackupName,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9][a-z0-9_-]*$')][string]$ProjectName,
    [string]$EnvFile,
    [string]$DockerExe
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ComposeTools.ps1')
$context = Get-RurisComposeContext -EnvFile $EnvFile -ProjectName $ProjectName -DockerExe $DockerExe
$running = @(Invoke-RurisCompose $context @('ps', '--status', 'running', '--services'))
if (@($running | Where-Object { $_ -in @('api', 'web', 'notification-worker') }).Count) {
    throw 'Serviciile aplicatiei trebuie oprite in proiectul destinatie. Baza si documentele trebuie sa fie goale.'
}
Invoke-RurisCompose $context @('up', '-d', '--wait', 'db')
Invoke-RurisCompose $context @('run', '--rm', '--no-deps', '-e', "BACKUP_NAME=$BackupName", 'maintenance', '/ops/restore.sh')
Invoke-RurisCompose $context @('run', '--rm', '--no-deps', 'api', 'python', '-m', 'flask', '--app', 'app', 'db', 'upgrade')
Invoke-RurisCompose $context @('run', '--rm', '--no-deps', 'api', 'python', '-m', 'flask', '--app', 'app', 'check-attachments')
Write-Output 'Restaurare verificata. Poti porni profilul app in proiectul destinatie.'
