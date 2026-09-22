"""Gunluk — FreeCAD Report view'a yazar, FreeCAD yoksa stdout'a duser.

Neden ozel bir modul: FreeCAD.Console fonksiyonlari satir sonu EKLEMEZ ve
sadece str kabul eder. Her cagri yerinde "\\n" hatirlamak yerine tek yerde
hallediliyor. Ayrica eklenti FreeCAD disinda (dogrudan python ile) import
edilirse cokmemeli — bassiz test bunu gerektiriyor.
"""

from __future__ import annotations

ONEK = "[CADdy] "

try:
    import FreeCAD as _App
except ImportError:  # FreeCAD disinda calisiyoruz (bassiz test)
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
    """Ayrintili izleme. Tercihlerde acilmadikca susar."""
    from . import config

    if config.ayikla_acik():
        _yaz("PrintMessage", "· " + str(mesaj))
