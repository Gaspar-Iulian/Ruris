function Get-RurisComposeContext {
    param([string]$EnvFile, [string]$ProjectName, [string]$DockerExe)
    $workspacePath = Split-Path -Parent $PSScriptRoot
    if (-not $DockerExe) {
        $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
        if ($dockerCommand) { $DockerExe = $dockerCommand.Source }
        else { $DockerExe = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe' }
    }
    if (-not (Test-Path -LiteralPath $DockerExe -PathType Leaf)) { throw 'Docker nu este disponibil.' }
    if (-not $EnvFile) { $EnvFile = Join-Path $workspacePath '.env' }
    $EnvFile = (Resolve-Path -LiteralPath $EnvFile -ErrorAction Stop).Path
    $arguments = @('compose', '--project-directory', $workspacePath, '--env-file', $EnvFile)
    if ($ProjectName) {
        if ($ProjectName -notmatch '^[a-z0-9][a-z0-9_-]*$') { throw 'Nume de proiect Docker invalid.' }
        $arguments += @('--project-name', $ProjectName)
    }
    $arguments += @('--profile', 'app', '--profile', 'maintenance')
    return @{ Docker = $DockerExe; Arguments = $arguments; Root = $workspacePath; EnvFile = $EnvFile }
}

function Invoke-RurisCompose {
    param($Context, [string[]]$CommandArguments)
    $previousEnvFile = $env:RURIS_ENV_FILE
    try {
        $env:RURIS_ENV_FILE = $Context.EnvFile
        & $Context.Docker @($Context.Arguments) @CommandArguments
        if ($LASTEXITCODE -ne 0) { throw "Comanda Docker a esuat (cod $LASTEXITCODE)." }
    } finally {
        $env:RURIS_ENV_FILE = $previousEnvFile
    }
}
