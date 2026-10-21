param([string]$EnvFile, [string]$ProjectName, [string]$DockerExe)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ComposeTools.ps1')
$context = Get-RurisComposeContext -EnvFile $EnvFile -ProjectName $ProjectName -DockerExe $DockerExe
$running = @(Invoke-RurisCompose $context @('ps', '--status', 'running', '--services'))
if ('api' -notin $running) { throw 'Backupul automat necesita portalul Docker pornit. Opreste orice server local care foloseste aceeasi baza.' }
$resume = @('api', 'notification-worker', 'web') | Where-Object { $_ -in $running }
$backupName = 'ruris-' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
try {
    Invoke-RurisCompose $context (@('stop') + $resume)
    Invoke-RurisCompose $context @('run', '--rm', '--no-deps', 'api', 'python', '-m', 'flask', '--app', 'app', 'check-attachments')
    Invoke-RurisCompose $context @('run', '--rm', '--no-deps', '-e', "BACKUP_NAME=$backupName", 'maintenance', '/ops/backup.sh')
    Write-Output "Backup creat: backups/$backupName"
} finally {
    Invoke-RurisCompose $context (@('start') + $resume)
}
