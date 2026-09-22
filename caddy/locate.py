"""claude.exe'yi bulur.

Neden bu kadar ugras: PATH'teki `claude` Windows'ta genelde bir `.cmd` ya da
`.ps1` shim'idir. Onu QProcess'e vermek `shell=True`/COMSPEC/tirnak isaretleri
gibi bir dizi sorun aciyor. Ayni klasorde ya da npm paketinin icinde duran
GERCEK `claude.exe`'yi bulup dogrudan onu calistiriyoruz.

Bulunan yol surec basina bir kez dogrulanip onbellege alinir (--version 1-2 sn
suruyor, her tur odemeye degmez).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import log

# Windows'ta konsol penceresi acilmasin
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_onbellek: Path | None = None
_onbellek_denendi = False


class BulunamadiHatasi(RuntimeError):
    pass


def _adaylar() -> list[Path]:
    a: list[Path] = []

    # 1) Kullanici elle verdiyse en oncelikli
    try:
        from . import config

        elle = config.metin("ClaudeExe").strip().strip('"')
        if elle:
            a.append(Path(elle))
    except Exception:
        pass

    # 2) npm global kurulumu — bu makinede buradan geliyor
    appdata = os.environ.get("APPDATA")
    if appdata:
        a.append(Path(appdata) / "npm" / "node_modules" / "@anthropic-ai"
                 / "claude-code" / "bin" / "claude.exe")

    # 3) Native installer'in tipik yeri
    home = os.environ.get("USERPROFILE")
    if home:
        a.append(Path(home) / ".local" / "bin" / "claude.exe")

    # 4) PATH'teki shim — .cmd/.ps1 ise kardesi .exe'yi dene
    yol = shutil.which("claude")
    if yol:
        p = Path(yol)
        if p.suffix.lower() == ".exe":
            a.append(p)
        else:
            a.append(p.with_suffix(".exe"))
            # npm shim'i genelde node_modules'un yanindadir
            a.append(p.parent / "node_modules" / "@anthropic-ai"
                     / "claude-code" / "bin" / "claude.exe")

    # Tekrarlari sirayi bozmadan at
    gorulen, temiz = set(), []
    for p in a:
        k = str(p).lower()
        if k not in gorulen:
            gorulen.add(k)
            temiz.append(p)
    return temiz


def _dogrula(exe: Path) -> str | None:
    """--version calistirir; surum metnini ya da None dondurur."""
    try:
        s = subprocess.run(
            [str(exe), "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=_NO_WINDOW,
        )
    except Exception as e:
        log.ayik(f"dogrulama basarisiz {exe}: {e}")
        return None
    if s.returncode != 0:
        return None
    return (s.stdout or "").strip() or None


def claude_exe(yeniden: bool = False) -> Path:
    """Dogrulanmis claude.exe yolunu dondurur. Bulunamazsa BulunamadiHatasi."""
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
            log.bilgi(f"claude bulundu: {aday}  ({surum})")
            _onbellek = aday
            return aday
        log.ayik(f"aday calisti ama surum vermedi: {aday}")

    raise BulunamadiHatasi(_MESAJ)


_MESAJ = (
    "claude.exe bulunamadi.\n"
    "  Claude Code kurulu mu?  Terminalde:  claude --version\n"
    "  Kuruluysa ama bulunamiyorsa, tam yolu ayarlara yaz:\n"
    "  Edit > Preferences > CADdy > claude.exe yolu"
)


def surum() -> str:
    """Kullaniciya gosterilecek surum metni; bulunamazsa aciklama."""
    try:
        return _dogrula(claude_exe()) or "bilinmiyor"
    except BulunamadiHatasi:
        return "bulunamadi"
