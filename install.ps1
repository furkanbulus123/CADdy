# CADdy installer - links this folder into FreeCAD's Mod directory.
#
# No admin rights needed: a junction (/J) does not require elevation,
# a symbolic link (/D) would. That is why a junction is used.
#
# Nothing is copied, it is LINKED. There is one source: this folder.
# After "git pull", FreeCAD loads the new version on its next start.
#
#     .\install.ps1                              # find everything automatically
#     .\install.ps1 -FreeCadDir "D:\FreeCAD 1.1"
#     .\install.ps1 -Force                       # replace an existing link
#
# NOTE: keep this file PURE ASCII. Windows PowerShell 5.1 reads a .ps1
# without BOM in the ANSI code page; non-ASCII characters (accented letters,
# long dashes) make the script fail to parse.

[CmdletBinding()]
param(
    [string] $FreeCadDir = "",
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$script:problems = 0

function Ok($m)     { Write-Host "  [+] $m" -ForegroundColor Green }
function Warn($m)   { Write-Host "  [!] $m" -ForegroundColor Yellow }
function Fail($m)   { Write-Host "  [x] $m" -ForegroundColor Red
                      $script:problems = $script:problems + 1 }
function Header($m) { Write-Host ""; Write-Host $m -ForegroundColor Cyan }

Write-Host ""
Write-Host "CADdy installer" -ForegroundColor White
Write-Host "source: $source"

# --- 1. Is this really the CADdy folder ---------------------------------
Header "1) Repository"
if ((Test-Path (Join-Path $source "InitGui.py")) -and
    (Test-Path (Join-Path $source "caddy\conversation.py"))) {
    Ok "repository files found"
} else {
    Fail "this folder is not the CADdy repository (InitGui.py / caddy\ missing)"
    Write-Host ""
    exit 1
}

# --- 2. FreeCAD ---------------------------------------------------------
Header "2) FreeCAD 1.1"
$candidates = @()
if ($FreeCadDir) { $candidates += $FreeCadDir }
$candidates += "$env:ProgramFiles\FreeCAD 1.1"
$candidates += "${env:ProgramFiles(x86)}\FreeCAD 1.1"
$candidates += "$env:LOCALAPPDATA\Programs\FreeCAD 1.1"

$fc = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path (Join-Path $c "bin\freecadcmd.exe"))) { $fc = $c; break }
}
if ($fc) {
    Ok "found: $fc"
    # Ask FreeCAD itself for its version: the exe's file info is empty.
    $script = "import FreeCAD; print('.'.join(FreeCAD.Version()[0:3]))"
    try {
        $v = & (Join-Path $fc "bin\freecadcmd.exe") -c $script | Select-Object -Last 1
    } catch {
        $v = $null
    }
    if ($v -and $v -match "^1\.1") {
        Ok "version $v"
    } elseif ($v) {
        Warn "version $v - CADdy is written for 1.1.x"
    } else {
        Warn "could not read the version (continuing anyway)"
    }
} else {
    Fail "FreeCAD 1.1 not found"
    Write-Host "      install it from https://www.freecad.org/downloads.php, or:"
    Write-Host '      .\install.ps1 -FreeCadDir "D:\FreeCAD 1.1"'
}

# --- 3. Claude Code CLI -------------------------------------------------
Header "3) Claude Code CLI"
$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
    Ok "command found: $($claude.Source)"
    try {
        $cv = & claude --version | Select-Object -First 1
    } catch {
        $cv = $null
    }
    if ($cv) { Ok "version $cv" } else { Warn "claude --version did not answer" }
} else {
    Fail "the claude command is not on PATH"
    Write-Host "      npm install -g @anthropic-ai/claude-code"
    Write-Host "      then:  claude     (sign in with your Claude plan in the browser)"
}

# --- 4. Subscription or API key -----------------------------------------
Header "4) Subscription or API key"
if ($env:ANTHROPIC_API_KEY) {
    Warn "ANTHROPIC_API_KEY is set - the CLI will bill that API key, not your plan."
    Write-Host '      To remove it permanently:'
    Write-Host '      [Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY",$null,"User")'
} else {
    Ok "ANTHROPIC_API_KEY is not set - your Claude plan will be used"
}

# --- 5. Junction --------------------------------------------------------
Header "5) Link into FreeCAD"
$mod  = Join-Path $env:APPDATA "FreeCAD\v1-1\Mod"
$link = Join-Path $mod "CADdy"

if (-not (Test-Path $mod)) {
    New-Item -ItemType Directory -Force -Path $mod | Out-Null
    Ok "Mod directory created: $mod"
}

function New-Junction($link, $target) {
    cmd /c mklink /J "$link" "$target" | Out-Null
    if (Test-Path $link) { Ok "linked: $link -> $target"; return $true }
    Fail "could not create the junction: $link"
    return $false
}

function Set-Link($link, $target, $name) {
    $existing = Get-Item $link -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        New-Junction $link $target | Out-Null
        return
    }
    $isLink = [bool] $existing.LinkType
    $current = $null
    if ($isLink) { $current = ($existing.Target | Select-Object -First 1) }

    if ($current -and ($current.TrimEnd('\') -ieq $target.TrimEnd('\'))) {
        Ok "$name link already points to the right place"
    } elseif (-not $isLink) {
        # NEVER delete a real folder: it may contain the user's work.
        Fail "a real folder is in the way: $link"
        Write-Host "      move or delete it, then run this script again"
    } elseif ($Force) {
        cmd /c rmdir "$link" | Out-Null
        New-Junction $link $target | Out-Null
    } else {
        Warn "$name link exists but points elsewhere: $current"
        Write-Host "      to replace it:  .\install.ps1 -Force"
    }
}

Set-Link $link $source "CADdy"


# --- Result -------------------------------------------------------------
Write-Host ""
if ($script:problems -eq 0) {
    Write-Host "Installation complete." -ForegroundColor Green
    Write-Host "Start FreeCAD; CADdy will appear in the workbench list."
    if ($fc) {
        Write-Host ""
        Write-Host "To verify:"
        Write-Host "  & '$fc\bin\freecadcmd.exe' '$source\tests\test_yukleme_fc.py'"
    }
    Write-Host ""
} else {
    Write-Host "$script:problems problem(s) left - fix the [x] lines above." -ForegroundColor Red
    Write-Host ""
    exit 1
}
