# Builds the Windows shell into dist/windows (what `pyxpo build desktop` copies on Windows):
#   PyxpoShell.exe + .NET / Windows App SDK files   (dotnet publish, self-contained)
#   pyxpo_native.dll                                (cmake: bridge + layout engine + Python host)
#   python/                                         (CPython embeddable distribution, same 3.13.x as the build)
#
# Needs: Windows x64, Visual Studio 2022 C++ tools, CMake 3.20+, .NET 8 SDK, Python 3.13 x64 (headers + libs).
# Usage: pwsh tools/build_windows_shell.ps1 [-Python C:\Python313\python.exe] [-Out dist\windows]
param(
    [string]$Python = "",
    [string]$Out = ""
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $Repo "dist\windows" }
if (-not $Python) { $Python = (Get-Command python).Source }

$PyVersion = & $Python -c "import platform, struct; assert struct.calcsize('P') == 8, 'needs 64-bit Python'; print(platform.python_version())"
if (-not $PyVersion.StartsWith("3.13.")) { throw "needs Python 3.13 x64, got $PyVersion ($Python)" }
$PyRoot = & $Python -c "import sys; print(sys.base_prefix)"
Write-Host "Python $PyVersion at $PyRoot"

$Work = Join-Path $Repo "build\windows-shell"
New-Item -ItemType Directory -Force -Path $Work | Out-Null
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# 1. pyxpo_native.dll
$Native = Join-Path $Work "native"
cmake -S (Join-Path $Repo "windows\native") -B $Native -A x64 "-DPython3_ROOT_DIR=$PyRoot"
if ($LASTEXITCODE) { throw "cmake configure failed" }
cmake --build $Native --config Release
if ($LASTEXITCODE) { throw "cmake build failed" }
Copy-Item (Join-Path $Native "Release\pyxpo_native.dll") $Out

# 2. The WinUI shell
dotnet publish (Join-Path $Repo "windows\PyxpoShell\PyxpoShell.csproj") -c Release -r win-x64 -o $Out
if ($LASTEXITCODE) { throw "dotnet publish failed" }
# A build renames the exe after the app; the resource index must not follow the exe name.
# A code-only shell may get no .pri at all, or one already named resources.pri.
$Pri = Join-Path $Out "PyxpoShell.pri"
if (Test-Path $Pri) { Copy-Item $Pri (Join-Path $Out "resources.pri") -Force }
Get-ChildItem $Out -Filter *.pri | ForEach-Object { Write-Host "resource index: $($_.Name)" }
Get-ChildItem $Out -Filter *.pdb | Remove-Item -Force

# 3. CPython embeddable distribution (stdlib zip, DLLs, extension modules)
$Zip = Join-Path $Work "python-$PyVersion-embed-amd64.zip"
if (-not (Test-Path $Zip)) {
    $Url = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
    Write-Host "download $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Zip
}
$PyDir = Join-Path $Out "python"
Expand-Archive -Path $Zip -DestinationPath $PyDir -Force
# The ._pth file would replace the search paths the host sets (app\, app_packages\); python.exe is not used.
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $PyDir "python313._pth"), (Join-Path $PyDir "python.exe"), (Join-Path $PyDir "pythonw.exe")

Write-Host "built $Out"
Get-ChildItem $Out | Select-Object -First 12 Name | Format-Table -HideTableHeaders
