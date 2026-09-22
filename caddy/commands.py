"""FreeCAD komutlari (arac cubugu / menu girdileri)."""

from __future__ import annotations

import os

import FreeCAD as App
import FreeCADGui as Gui

from . import log

IKON_DIZINI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "icons")


def _ikon(ad: str) -> str:
    return os.path.join(IKON_DIZINI, ad)


class PaneliGoster:
    def GetResources(self):
        return {
            "Pixmap": _ikon("caddy.svg"),
            "MenuText": "CADdy panelini aç",
            "ToolTip": "AI yardımcı panelini açar",
            "Accel": "Ctrl+Shift+A",
        }

    def Activated(self):
        from .ui.dock import paneli_goster

        paneli_goster()

    def IsActive(self):
        return True


class SonAiDegisikliginiGeriAl:
    def GetResources(self):
        return {
            "Pixmap": _ikon("caddy-undo.svg"),
            "MenuText": "Son AI değişikliğini geri al",
            "ToolTip": "AI'ın yaptığı son işlemi tek adımda geri alır",
        }

    def Activated(self):
        # Panel aciksa ONUN yolundan git: orada namespace temizligi ve
        # sohbete bildirim de var. Bayat baglama sert cokme uretiyor
        # (bkz. executor.namespace_temizle), o yuzden bu onemli.
        try:
            from PySide import QtWidgets

            from .ui.dock import NESNE_ADI

            mw = Gui.getMainWindow()
            dock = mw.findChild(QtWidgets.QDockWidget, NESNE_ADI)
            if dock is not None and dock.widget() is not None:
                dock.widget().geri_al()
                return
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"panel uzerinden geri alinamadi: {e}")

        # Panel kapali: yalin yol. Kural AYNI — tepede AI'in isi yoksa
        # DOKUNMA. Eskiden burada "yine de geri aliniyor" yaziyordu ve
        # kullanicinin kendi son islemini siliyordu; komutun adi "Son AI
        # degisikligini geri al" oldugu icin bu bir yalandi.
        doc = App.ActiveDocument
        if doc is None or not doc.UndoNames:
            log.uyari("geri alinacak bir sey yok")
            return
        ad = doc.UndoNames[0]
        if not ad.startswith("AI:"):
            log.uyari(f"son islem AI'a ait degil ({ad}) — geri ALINMADI. "
                      f"Kendi degisikligini Ctrl+Z ile geri alabilirsin.")
            return
        doc.undo()
        doc.recompute()
        log.bilgi(f"geri alindi: {ad}")

    def IsActive(self):
        doc = App.ActiveDocument
        return doc is not None and bool(doc.UndoNames)


KOMUTLAR = (
    ("CADdy_ShowPanel", PaneliGoster()),
    ("CADdy_UndoLastAIChange", SonAiDegisikliginiGeriAl()),
)


def kaydet() -> list[str]:
    for ad, nesne in KOMUTLAR:
        Gui.addCommand(ad, nesne)
    return [ad for ad, _ in KOMUTLAR]
