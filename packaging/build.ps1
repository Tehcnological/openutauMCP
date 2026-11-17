# Builds dist\openutau-mcp.exe (the whole server in one Windows .exe, no Python needed, with the bridge plugin inside)
# and dist\OpenUtauMcp.Plugin.dll (the same plugin, for installs that copy it by hand).
# Needs uv (https://docs.astral.sh/uv/), a .NET 10+ SDK and an OpenUtau install to compile the plugin against.
# From the repo root:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-OpenUtauDir "D:\Apps\OpenUtau"]
param([string]$OpenUtauDir = "C:\Program Files\OpenUtau", [string]$Dotnet = "dotnet")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root
$venv = "$root\.build\venv"
$plugin = "$root\.build\plugin"

& $Dotnet build "$root\plugin" -c Release -p:OpenUtauDir="$OpenUtauDir" -o $plugin --nologo -v quiet --no-incremental -p:DebugType=none -p:DebugSymbols=false -p:Deterministic=true
if ($LASTEXITCODE) { throw "plugin build failed" }

uv venv -q -p 3.11 --clear $venv
if ($LASTEXITCODE) { throw "uv venv failed" }
uv pip install -q -p $venv ".[kanji]"
if ($LASTEXITCODE) { throw "uv pip install failed" }
# What goes into the exe, before the build tools are added (local package lines would carry local paths)
$packages = uv pip freeze -p $venv | Where-Object { $_ -notmatch ' @ file:' }
uv pip install -q -p $venv "pyinstaller==6.22.3"
if ($LASTEXITCODE) { throw "uv pip install failed" }

& "$venv\Scripts\pyinstaller.exe" --onefile --noconfirm --clean --log-level WARN -n openutau-mcp `
    --collect-data pykakasi --add-data "$root\skill\SKILL.md;openutau_mcp" `
    --add-data "$plugin\OpenUtauMcp.Plugin.dll;openutau_mcp" `
    --distpath "$root\dist" --workpath "$root\.build\pyinstaller" --specpath "$root\.build" `
    "$root\packaging\entry.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Copy-Item "$plugin\OpenUtauMcp.Plugin.dll" "$root\dist\" -Force

# Record exactly what went into the build, next to it.
$ou = (Get-Item "$OpenUtauDir\OpenUtau.exe").VersionInfo.ProductVersion -replace '\+.*'
"Plugin compiled against OpenUtau $ou" | Out-File -Encoding utf8 "$root\dist\openutau-mcp-packages.txt"
$packages | Out-File -Encoding utf8 -Append "$root\dist\openutau-mcp-packages.txt"
Get-FileHash "$root\dist\openutau-mcp.exe", "$root\dist\OpenUtauMcp.Plugin.dll" -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash)  $(Split-Path $_.Path -Leaf)" } | Out-File -Encoding ascii "$root\dist\SHA256SUMS.txt"
Write-Host "Built $root\dist\openutau-mcp.exe and OpenUtauMcp.Plugin.dll (OpenUtau $ou)"
