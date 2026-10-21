$ErrorActionPreference = 'Stop'
$previousPath = $env:PATH
try {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        $portableRoot = Join-Path $PSScriptRoot '..\.tools'
        $portableNode = Get-ChildItem -LiteralPath $portableRoot -Filter 'node-v*-win-x64' -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'node.exe') } |
            Sort-Object Name -Descending | Select-Object -First 1
        if (-not $portableNode) { throw 'Instaleaza Node.js LTS, apoi redeschide terminalul.' }
        $env:PATH = $portableNode.FullName + ';' + $env:PATH
    }
    Push-Location $PSScriptRoot
    try { & npm.cmd run dev }
    finally { Pop-Location }
}
finally { $env:PATH = $previousPath }
