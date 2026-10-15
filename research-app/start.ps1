# ASCII only: compatible with Windows PowerShell 5.1.
# Probe real interpreters instead of trusting a stale `py -3` registration.
$ErrorActionPreference = "Stop"
$AppArgs = @($args)
$Candidates = New-Object 'System.Collections.Generic.List[object]'

function Add-PythonCandidate {
    param([string]$File, [string[]]$PrefixArgs = @())
    if (-not $File -or $File -like '*\Microsoft\WindowsApps\*') { return }
    if (Test-Path -LiteralPath $File -PathType Leaf) {
        $Candidates.Add([pscustomobject]@{ File = $File; PrefixArgs = $PrefixArgs })
    }
}

function Find-WorkingPython {
    $ProbeCode = 'import sys; print(sys.executable); sys.exit(0 if sys.version_info >= (3, 12) else 1)'
    foreach ($Candidate in $Candidates) {
        try {
            $PrefixArgs = @($Candidate.PrefixArgs)
            $OutputLines = @(& $Candidate.File @PrefixArgs -I -X utf8 -c $ProbeCode 2>$null)
            if ($LASTEXITCODE -eq 0 -and $OutputLines.Count -eq 1) {
                $ResolvedPython = [string]$OutputLines[0]
                if (Test-Path -LiteralPath $ResolvedPython -PathType Leaf) { return $ResolvedPython }
            }
        } catch {
            # Invalid executables, removed installs and broken launcher entries
            # are skipped. No registry entry or user installation is changed.
        }
    }
    return $null
}

Add-PythonCandidate -File $env:GEMS_PYTHON
foreach ($Name in @('python.exe', 'python3.exe')) {
    foreach ($Command in @(Get-Command $Name -All -ErrorAction SilentlyContinue)) {
        Add-PythonCandidate -File $Command.Source
    }
}

# The normal Python installer records its executable here, even without PATH.
foreach ($RegistryRoot in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore', 'HKLM:\Software\WOW6432Node\Python\PythonCore')) {
    foreach ($Entry in @(Get-ChildItem $RegistryRoot -ErrorAction SilentlyContinue)) {
        $Install = Get-Item ($Entry.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
        if ($Install) {
            Add-PythonCandidate -File ([string]$Install.GetValue('ExecutablePath'))
            $InstallDir = [string]$Install.GetValue('')
            if ($InstallDir) { Add-PythonCandidate -File (Join-Path $InstallDir 'python.exe') }
        }
    }
}

# Explicit versions can succeed even when `py -3` points at a removed install.
foreach ($Command in @(Get-Command py.exe -All -ErrorAction SilentlyContinue)) {
    foreach ($Version in @('-3.12', '-3.13', '-3.14', '-3')) {
        Add-PythonCandidate -File $Command.Source -PrefixArgs @($Version)
    }
}

$SelectedPython = Find-WorkingPython
if (-not $SelectedPython) {
    Write-Host 'No working Python 3.12+ interpreter was found.'
    Write-Host 'Install Python 3.12, then run start.cmd again:'
    Write-Host '  winget install --id Python.Python.3.12 -e'
    Write-Host 'Or set GEMS_PYTHON to the full path of a working python.exe.'
    exit 1
}
Write-Host ('Selected Python: ' + $SelectedPython)
if ($AppArgs -contains '--diagnose-python') { exit 0 }
& $SelectedPython -I -X utf8 (Join-Path $PSScriptRoot 'start.py') @AppArgs
exit $LASTEXITCODE
