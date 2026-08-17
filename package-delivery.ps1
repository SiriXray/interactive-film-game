param(
    [string]$OutputPath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent = Split-Path -Parent $root
$folderName = Split-Path -Leaf $root

if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $parent) "interactive-film-game-full.zip"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

Set-Location $root
py -3 tools\verify_delivery.py
if ($LASTEXITCODE -ne 0) {
    throw "Delivery validation failed; the package was not created."
}

if (Test-Path -LiteralPath $OutputPath) {
    if (-not $Force) {
        throw "Output already exists: $OutputPath. Use -Force to replace it."
    }
    Remove-Item -LiteralPath $OutputPath -Force
}

$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if (-not $tar) {
    throw "tar.exe was not found. Use a current Windows 10/11 installation or install bsdtar."
}

$items = @(
    "$folderName\app.py",
    "$folderName\requirements.txt",
    "$folderName\README.txt",
    "$folderName\DELIVERY.md",
    "$folderName\.env.example",
    "$folderName\start-5100.ps1",
    "$folderName\start-5100.cmd",
    "$folderName\package-delivery.ps1",
    "$folderName\browser_check.cjs",
    "$folderName\static",
    "$folderName\tools",
    "$folderName\tests",
    "$folderName\data\stories.json",
    "$folderName\data\story.json",
    "$folderName\data\tianhe-market-gate.story.json",
    "$folderName\data\production-jobs.json",
    "$folderName\data\imports",
    "$folderName\generated",
    "agent"
)

Push-Location $parent
try {
    & $tar.Source -a -c -f $OutputPath --exclude="*/__pycache__" --exclude="*.pyc" --exclude="*.log" @items
    if ($LASTEXITCODE -ne 0) {
        throw "tar.exe failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$size = [math]::Round((Get-Item -LiteralPath $OutputPath).Length / 1GB, 2)
Write-Host "Created: $OutputPath"
Write-Host "Archive size: $size GB"
Write-Host "No .env, API keys, console password, logs, or production-autopilot authorization were included."
