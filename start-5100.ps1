param(
    [switch]$SkipInstall,
    [switch]$PreviewOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Resolve-PythonCommand {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        return @{ Exe = $launcher.Source; Prefix = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Prefix = @() }
    }
    throw "Python 3 was not found. Install Python 3.10 or newer and enable the py launcher or PATH entry."
}

$python = Resolve-PythonCommand
$pythonExe = $python.Exe
$pythonPrefix = $python.Prefix

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created $root\.env"
    Write-Host "Fill VIDU_API_KEY with the receiver's own key, then run this script again."
    exit 2
}

$envText = Get-Content -LiteralPath ".env" -Raw -Encoding UTF8
$hasApiKey = $envText -match '(?m)^\s*VIDU_API_KEY\s*=\s*(?!replace_with_your_key\s*$)\S+'
if (-not $hasApiKey -and -not $PreviewOnly) {
    Write-Host "VIDU_API_KEY is missing or still uses the placeholder in $root\.env"
    Write-Host "Use the receiver's own key for the S1 full chain, or run .\start-5100.ps1 -PreviewOnly for pre-generated playback only."
    exit 2
}

if (-not $SkipInstall) {
    & $pythonExe @pythonPrefix -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $pythonExe @pythonPrefix tools\verify_delivery.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Delivery validation failed. Re-copy the complete package, especially generated\ and data\production-jobs.json."
    exit $LASTEXITCODE
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg is not on PATH. Existing movies can play, but missing movies cannot be composed locally."
}

$url = "http://127.0.0.1:5100/"
Write-Host "Starting Vidu interactive film at $url"
Write-Host "Keep this window open. Press Ctrl+C to stop the server."

$browserJob = $null
if (-not $NoBrowser) {
    $browserJob = Start-Job -ScriptBlock {
        param($healthUrl, $pageUrl)
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2 | Out-Null
                Start-Process $pageUrl
                return
            } catch {
                Start-Sleep -Seconds 1
            }
        }
    } -ArgumentList "http://127.0.0.1:5100/api/health", $url
}

try {
    & $pythonExe @pythonPrefix app.py
} finally {
    if ($browserJob) {
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
}
