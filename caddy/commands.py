"""FreeCAD commands (toolbar / menu entries)."""

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
            "MenuText": "Open CADdy panel",
            "ToolTip": "Opens the AI assistant panel",
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
            "MenuText": "Undo last AI change",
            "ToolTip": "Undoes the AI's last operation in one step",
        }

    def Activated(self):
        # If the panel is open, go through IT: it also clears the namespace
        # and notifies the chat. Stale bindings cause hard crashes
        # (see executor.namespace_temizle), so this matters.
        try:
            from PySide import QtWidgets

            from .ui.dock import NESNE_ADI

            mw = Gui.getMainWindow()
            dock = mw.findChild(QtWidgets.QDockWidget, NESNE_ADI)
            if dock is not None and dock.widget() is not None:
                dock.widget().geri_al()
                return
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not undo through the panel: {e}")

        # Panel closed: the plain path. Same rule — if the top of the stack
        # is not the AI's work, DO NOT TOUCH it. This used to say "undoing
        # anyway" and deleted the user's own last operation; with the
        # command named "Undo last AI change" that was a lie.
        doc = App.ActiveDocument
        if doc is None or not doc.UndoNames:
            log.uyari("nothing to undo")
            return
        ad = doc.UndoNames[0]
        if not ad.startswith("AI:"):
            log.uyari(f"the last operation is not the AI's ({ad}) — NOT undone. "
                      f"Use Ctrl+Z to undo your own change.")
            return
        doc.undo()
        doc.recompute()
        log.bilgi(f"undone: {ad}")

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
