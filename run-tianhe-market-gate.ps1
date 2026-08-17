$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:STORY_FILE = Join-Path $root "data\tianhe-market-gate.story.json"
$env:INTERACTIVE_FILM_PORT = if ($env:INTERACTIVE_FILM_PORT) { $env:INTERACTIVE_FILM_PORT } else { "5101" }

Write-Host "STORY_FILE=$env:STORY_FILE"
Write-Host "Starting interactive film demo on http://127.0.0.1:$env:INTERACTIVE_FILM_PORT/"

Set-Location $root
py -3 app.py
