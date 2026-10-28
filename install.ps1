<#
.SYNOPSIS
    Install, update or uninstall PyLZR on Windows.

.DESCRIPTION
    1. Installs what's missing (uv, Python 3.12), after asking once.
    2. Downloads PyLZR into %LOCALAPPDATA%\PyLZR\app (or updates it), unless
       run from inside a PyLZR folder or given -Source.
    3. Sets it up with `uv sync --locked` (the exact versions tested in CI).
    4. Adds a Start Menu entry, a Desktop shortcut and a `pylzr` command.
    Run it again to update. Saved settings are never touched.

    From the web:   irm https://raw.githubusercontent.com/oh-ok-i-get-it/PyLZR/main/install.ps1 | iex
    From a clone:   powershell -ExecutionPolicy Bypass -File install.ps1

.PARAMETER Yes          Don't ask before installing prerequisites.
.PARAMETER Source       Use this PyLZR folder instead of downloading one.
.PARAMETER NoLaunchers  Skip the Start Menu entry, Desktop shortcut and `pylzr` command.
.PARAMETER Uninstall    Remove the launchers and the downloaded copy (keeps settings,
                        uv and Python).
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [string]$Source,
    [switch]$NoLaunchers,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$RepoUrl   = 'https://github.com/oh-ok-i-get-it/PyLZR'
$AppDir    = Join-Path $env:LOCALAPPDATA 'PyLZR'      # everything this script creates
$CodeDir   = Join-Path $AppDir 'app'                  # downloaded copy of PyLZR
$BinDir    = Join-Path $AppDir 'bin'                  # holds pylzr.cmd, added to PATH
$Shortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'PyLZR.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop'))  'PyLZR.lnk')
)
$SettingsFile = Join-Path $env:APPDATA 'PyLZR\PyLZR.ini'

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Step([string]$Text) { Write-Host ''; Write-Host "==> $Text" -ForegroundColor Cyan }

function Confirm-Action([string]$Question) {
    if ($Yes) { return $true }
    $answer = Read-Host "$Question [Y/n]"
    return ($answer -eq '' -or $answer -match '^[Yy]')
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Update-SessionPath {
    # Tools installed since this terminal opened (e.g. by winget) are only on the
    # saved PATH; add it to this session's PATH, keeping session-only entries
    $env:Path = $env:Path + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') +
                ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Invoke-Checked([string]$What, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function Test-NativeSuccess([scriptblock]$Command) {
    # Run a program quietly; true if it exits with 0. 'Continue' locally:
    # Windows PowerShell 5.1 would otherwise stop on its redirected stderr.
    $ErrorActionPreference = 'Continue'
    & $Command *> $null
    return ($LASTEXITCODE -eq 0)
}

# --- Which PyLZR folder -----------------------------------------------------

function Test-PyLZRFolder([string]$Dir) {
    $pyproject = Join-Path $Dir 'pyproject.toml'
    return (Test-Path $pyproject) -and ((Get-Content $pyproject -Raw) -match '(?m)^name = "pylzr"')
}

function Resolve-PyLZRFolder {
    if ($Source) {
        $dir = (Resolve-Path $Source).Path
        if (-not (Test-PyLZRFolder $dir)) { throw "$dir is not a PyLZR folder (no pyproject.toml for pylzr)." }
        return @{ Dir = $dir; Managed = $false }
    }
    if ($PSScriptRoot -and (Test-PyLZRFolder $PSScriptRoot)) {
        return @{ Dir = $PSScriptRoot; Managed = $false }     # run from a clone
    }
    return @{ Dir = $CodeDir; Managed = $true }               # run from the web
}

# --- Prerequisites ----------------------------------------------------------

function Test-Python312 {
    # python.org installs (installer or `py install`) register here (PEP 514).
    # Not `py -3.12`: the Python install manager may offer to install a missing
    # version and wait for an answer.
    foreach ($root in 'HKCU:', 'HKLM:') {
        if (Get-ChildItem "$root\SOFTWARE\Python\PythonCore" -ErrorAction SilentlyContinue |
                Where-Object { $_.PSChildName -match '^3\.12(-64|-32)?$' }) { return $true }
    }
    if (Test-Command 'uv') {
        # Any other 3.12 on PATH. uv's own downloads don't count on purpose:
        # Windows Application Control often blocks them.
        return (Test-NativeSuccess { uv python find --python-preference only-system 3.12 })
    }
    return $false
}

function Install-Prerequisites {
    Step 'Checking prerequisites'
    Update-SessionPath
    $missing = @()
    if (-not (Test-Command 'uv'))  { $missing += 'uv (sets up and runs PyLZR)' }
    if (-not (Test-Python312))     { $missing += 'Python 3.12 (from python.org)' }
    if ($missing.Count -eq 0) { Say 'uv and Python 3.12 are installed.' 'Green'; return }

    Say 'Missing:'
    $missing | ForEach-Object { Say "  - $_" 'Yellow' }
    if (-not (Confirm-Action 'Install them now?')) { throw 'Prerequisites not installed; nothing changed.' }

    if (-not (Test-Command 'uv')) {
        if (Test-Command 'winget') {
            Invoke-Checked 'Installing uv' { winget install -e --id astral-sh.uv --source winget `
                --accept-source-agreements --accept-package-agreements --disable-interactivity }
        } else {
            Invoke-Checked 'Installing uv' { powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex' }
        }
        Update-SessionPath
        if (-not (Test-Command 'uv')) { throw 'uv was installed but is not on PATH yet. Open a new terminal and run this again.' }
    }

    if (-not (Test-Python312)) {
        if ((Test-Command 'py') -and (Test-NativeSuccess { py install --help })) {
            Invoke-Checked 'Installing Python 3.12' { py install 3.12 }       # Python install manager
        } elseif (Test-Command 'winget') {
            Invoke-Checked 'Installing Python 3.12' { winget install -e --id Python.Python.3.12 --source winget `
                --accept-source-agreements --accept-package-agreements --disable-interactivity }
        } else {
            throw 'Install Python 3.12 from https://www.python.org/downloads/windows/, then run this again.'
        }
        Update-SessionPath
        if (-not (Test-Python312)) { throw 'Python 3.12 was installed but is not visible yet. Open a new terminal and run this again.' }
    }
    Say 'Prerequisites installed.' 'Green'
}

# --- Code -------------------------------------------------------------------

function Update-Code([string]$Dir) {
    Step "Getting PyLZR into $Dir"
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    if (Test-Command 'git') {
        if (Test-Path (Join-Path $Dir '.git')) {
            Invoke-Checked 'git pull' { git -C $Dir pull --ff-only }
        } else {
            if (Test-Path $Dir) { Remove-Item -Recurse -Force $Dir }
            Invoke-Checked 'git clone' { git clone $RepoUrl $Dir }
        }
        return
    }
    # No git: download the latest main as a ZIP and replace the code, keeping .venv
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $zip     = Join-Path $env:TEMP 'pylzr-main.zip'
    $extract = Join-Path $env:TEMP 'pylzr-main'
    Invoke-WebRequest "$RepoUrl/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive $zip -DestinationPath $extract
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Get-ChildItem -Force $Dir | Where-Object Name -ne '.venv' | Remove-Item -Recurse -Force
    Get-ChildItem -Force (Join-Path $extract 'PyLZR-main') | Move-Item -Destination $Dir
    Remove-Item -Recurse -Force $zip, $extract
}

function Sync-Environment([string]$Dir, [bool]$Managed) {
    Step 'Installing PyLZR and its packages (uv sync --locked)'
    $env:UV_SYSTEM_CERTS = '1'                     # works behind HTTPS-inspecting networks too
    $env:UV_PYTHON_PREFERENCE = 'only-system'      # use python.org's Python, not uv's download
    if ($Managed) {
        Invoke-Checked 'uv sync' { uv sync --locked --project $Dir }
    } else {
        # Your own folder: keep extra packages you installed (e.g. the dev tools)
        Invoke-Checked 'uv sync' { uv sync --locked --inexact --project $Dir }
    }
}

# --- Launchers --------------------------------------------------------------

function Send-EnvironmentChanged {
    # Tell Windows the user PATH changed, so new terminals see it without signing out
    if (-not ('PyLZR.NativeMethods' -as [type])) {
        Add-Type -Namespace PyLZR -Name NativeMethods -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam,
    uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
    }
    $result = [UIntPtr]::Zero
    [PyLZR.NativeMethods]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$result) | Out-Null
}

function Set-UserPathEntry([string]$Entry, [bool]$Present) {
    # Edit the raw registry value so entries like %USERPROFILE%\... stay unexpanded,
    # and so adding then removing the entry gives back exactly the original text
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
    try {
        $raw    = [string]$key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        $others = @($raw -split ';' | Where-Object { $_.TrimEnd('\') -ne $Entry.TrimEnd('\') })
        if (-not $Present) {
            $new = $others -join ';'
        } elseif ($others.Count -lt @($raw -split ';').Count) {
            return                                    # already there
        } elseif ($raw -eq '' -or $raw.EndsWith(';')) {
            $new = "$raw$Entry;"
        } else {
            $new = "$raw;$Entry"
        }
        if ($new -eq $raw) { return }                 # nothing to change
        $key.SetValue('Path', $new, [Microsoft.Win32.RegistryValueKind]::ExpandString)
    } finally {
        $key.Close()
    }
    Send-EnvironmentChanged
}

function Install-Launchers([string]$Dir) {
    Step 'Adding the Start Menu entry, Desktop shortcut and pylzr command'
    $pythonw = Join-Path $Dir '.venv\Scripts\pythonw.exe'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in $Shortcuts) {
        $link = $shell.CreateShortcut($path)
        $link.TargetPath       = $pythonw              # pythonw: no console window
        $link.Arguments        = '-m pylzr'
        $link.WorkingDirectory = $Dir
        $link.Description      = 'PyLZR sound-reactive laser controller'
        $link.Save()
        Say "  $path"
    }

    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $cmd = Join-Path $BinDir 'pylzr.cmd'
    Set-Content -Path $cmd -Encoding ASCII -Value "@`"$(Join-Path $Dir '.venv\Scripts\pylzr.exe')`" %*"
    Set-UserPathEntry $BinDir $true
    Say "  $cmd (on your PATH; open a new terminal to use it)"
}

# --- Uninstall --------------------------------------------------------------

function Uninstall-PyLZR {
    Step 'Uninstalling PyLZR'
    foreach ($path in $Shortcuts) {
        if (Test-Path $path) { Remove-Item -Force $path; Say "  removed $path" }
    }
    Set-UserPathEntry $BinDir $false
    if (Test-Path $AppDir) {
        Set-Location $env:USERPROFILE                 # never delete the folder we're standing in
        Remove-Item -Recurse -Force $AppDir
        Say "  removed $AppDir"
    }
    Say ''
    Say 'PyLZR is uninstalled. uv and Python were left installed.' 'Green'
    Say "Your saved settings are kept in $SettingsFile (delete that folder to remove them)."
}

# --- Main -------------------------------------------------------------------

if ($Uninstall) {
    Uninstall-PyLZR
    return
}

$target = Resolve-PyLZRFolder
Install-Prerequisites
if ($target.Managed) { Update-Code $target.Dir } else { Step "Using PyLZR in $($target.Dir)" }
Sync-Environment $target.Dir $target.Managed
if (-not $NoLaunchers) { Install-Launchers $target.Dir }

Say ''
Say 'PyLZR is installed.' 'Green'
if (-not $NoLaunchers) {
    Say 'Start it from the Start Menu or Desktop (PyLZR), or type `pylzr` in a new terminal.'
}
Say 'To update, run this installer again. To remove PyLZR, run it with -Uninstall.'
