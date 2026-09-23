"""Logging — writes to FreeCAD's Report view, falls back to stdout without FreeCAD.

Why a dedicated module: FreeCAD.Console functions do NOT append a newline and
only accept str. Instead of remembering "\\n" at every call site, it is
handled in one place. Also, the addon must not crash when imported outside
FreeCAD (plain python) — headless tests rely on that.
"""

from __future__ import annotations

ONEK = "[CADdy] "

try:
    import FreeCAD as _App
except ImportError:  # running outside FreeCAD (headless test)
    _App = None


def _yaz(kanal: str, mesaj: str) -> None:
    satir = ONEK + str(mesaj).rstrip() + "\n"
    if _App is None:
        print(satir, end="")
        return
    getattr(_App.Console, kanal)(satir)


def bilgi(mesaj: str) -> None:
    _yaz("PrintMessage", mesaj)


def uyari(mesaj: str) -> None:
    _yaz("PrintWarning", mesaj)


def hata(mesaj: str) -> None:
    _yaz("PrintError", mesaj)


def ayik(mesaj: str) -> None:
    """Verbose tracing. Silent unless enabled in preferences."""
    from . import config

    if config.ayikla_acik():
        _yaz("PrintMessage", "· " + str(mesaj))
