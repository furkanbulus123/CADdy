"""Finds claude.exe.

Why the effort: on Windows, `claude` on PATH is usually a `.cmd` or `.ps1`
shim. Handing that to QProcess opens a string of problems (`shell=True`,
COMSPEC, quoting). We find the REAL `claude.exe` next to it or inside the
npm package and run that directly.

The path found is verified once per process and cached (--version takes
1-2 s, not worth paying on every turn).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import log

# Do not open a console window on Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_onbellek: Path | None = None
_onbellek_denendi = False


class BulunamadiHatasi(RuntimeError):
    pass


def _adaylar() -> list[Path]:
    a: list[Path] = []

    # 1) Set by the user by hand: highest priority
    try:
        from . import config

        elle = config.metin("ClaudeExe").strip().strip('"')
        if elle:
            a.append(Path(elle))
    except Exception:
        pass

    # 2) npm global install
    appdata = os.environ.get("APPDATA")
    if appdata:
        a.append(Path(appdata) / "npm" / "node_modules" / "@anthropic-ai"
                 / "claude-code" / "bin" / "claude.exe")

    # 3) Typical location of the native installer
    home = os.environ.get("USERPROFILE")
    if home:
        a.append(Path(home) / ".local" / "bin" / "claude.exe")

    # 4) The shim on PATH — if it is .cmd/.ps1, try its sibling .exe
    yol = shutil.which("claude")
    if yol:
        p = Path(yol)
        if p.suffix.lower() == ".exe":
            a.append(p)
        else:
            a.append(p.with_suffix(".exe"))
            # the npm shim usually sits next to node_modules
            a.append(p.parent / "node_modules" / "@anthropic-ai"
                     / "claude-code" / "bin" / "claude.exe")

    # Drop duplicates while keeping the order
    gorulen, temiz = set(), []
    for p in a:
        k = str(p).lower()
        if k not in gorulen:
            gorulen.add(k)
            temiz.append(p)
    return temiz


def _dogrula(exe: Path) -> str | None:
    """Runs --version; returns the version text or None."""
    try:
        s = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_NO_WINDOW,
        )
    except Exception as e:
        log.ayik(f"verification failed {exe}: {e}")
        return None
    if s.returncode != 0:
        return None
    return (s.stdout or "").strip() or None


def claude_exe(yeniden: bool = False) -> Path:
    """Returns the verified claude.exe path. Raises BulunamadiHatasi if not found."""
    global _onbellek, _onbellek_denendi

    if yeniden:
        _onbellek, _onbellek_denendi = None, False
    if _onbellek is not None:
        return _onbellek
    if _onbellek_denendi:
        raise BulunamadiHatasi(_MESAJ)

    _onbellek_denendi = True
    for aday in _adaylar():
        if not aday.exists():
            continue
        surum = _dogrula(aday)
        if surum:
            log.bilgi(f"claude found: {aday}  ({surum})")
            _onbellek = aday
            return aday
        log.ayik(f"candidate ran but gave no version: {aday}")

    raise BulunamadiHatasi(_MESAJ)


_MESAJ = (
    "claude.exe not found.\n"
    "  Is Claude Code installed?  In a terminal:  claude --version\n"
    "  If it is installed but not found, set the full path in:\n"
    "  Edit > Preferences > CADdy > claude.exe path"
)


def surum() -> str:
    """Version text to show the user; an explanation if not found."""
    try:
        return _dogrula(claude_exe()) or "unknown"
    except BulunamadiHatasi:
        return "not found"
