"""Places CADdy PERMANENTLY in FreeCAD's top bar.

Problem: CADdy is a *workbench*, so it does not exist unless picked from the
drop-down at the top. The user asked "can we add it directly as a tab at
the top".

The workbench's own appendToolbar/appendMenu do NOT solve this: they are
only visible while that workbench is active.

WHAT IS SHOWN — narrowed on the user's request
----------------------------------------------
The first version had a "CADdy" MENU (text) and a two-command toolbar in
the top bar. The user: *"CADdy looks bad in FreeCAD, only show the logo"*
and *"don't show the AI undo and such."*

So the top bar now holds ONE THING: the logo button that opens the panel.
  - The menu bar entry was REMOVED (the text came from there)
  - "Undo last AI change" was TAKEN OUT of the top bar

Neither is LOST: the workbench's own menu and toolbar (Initialize in
InitGui) show both. The top bar is just the "reachable from anywhere"
shortcut; putting every command there made the clutter the user
complained about.

THE REAL TRAP — on the first try the menu NEVER APPEARED, and this is why:
FreeCAD's menu bar is MANAGED by the workbench system. On every workbench
switch MenuManager rebuilds the menu bar and DELETES menus added from
outside. So adding once is not enough; it has to be added AGAIN on every
workbench switch. The toolbar is not subject to MenuManager, so it is more
robust — but the refresh stays, because the user can also hide the toolbar
itself.

Three layers of defence:
  1. connect to the workbenchActivated signal (if present) -> refresh on every switch
  2. periodic refresh (first minute, every 3 s) -> covers the startup race
     and versions without the signal
  3. existence check by objectName -> prevents adding it again and again

WHERE QAction LIVES: in PySide6 QAction moved from QtWidgets to QtGui.
FreeCAD's PySide shim gives one or the other depending on the version, so
both are tried.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtGui, QtWidgets

from .. import log

ARAC_CUBUGU_ADI = "CADdy"
_ARAC_NESNE = "CADdyUstAracCubugu"

# ONLY the command that opens the panel goes in the top bar. See the module header.
_KOMUT_ADLARI = ("CADdy_ShowPanel",)

_ILK_DENEME_MS = 1200
_EN_FAZLA_DENEME = 10
_TAZELEME_MS = 3000
_TAZELEME_SAYISI = 20        # ~1 minute

# Which module has QAction? PySide6 = QtGui, PySide2 = QtWidgets.
QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction")

_durum = {"kuruldu": False, "tazeleme": 0, "zamanlayici": None}


def yerlestir() -> None:
    """Adds the logo button to the top bar and keeps it there."""
    _dene(0)


# --------------------------------------------------------------------------
# setup
# --------------------------------------------------------------------------

def _ana_pencere():
    try:
        import FreeCADGui as Gui
        return Gui.getMainWindow()
    except Exception:
        return None


def _logo():
    """The CADdy logo as a QIcon; None if it cannot be loaded.

    If None comes back the caller falls back to TEXT — a button with neither
    icon nor text would be an unclickable gap.
    """
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    yol = os.path.join(kok, "resources", "icons", "caddy.svg")
    if not os.path.exists(yol):
        return None
    ikon = QtGui.QIcon(yol)
    return None if ikon.isNull() else ikon


def _dene(sayac: int) -> None:
    mw = _ana_pencere()
    if mw is None:
        if sayac < _EN_FAZLA_DENEME:
            QtCore.QTimer.singleShot(_ILK_DENEME_MS,
                                     lambda: _dene(sayac + 1))
        else:
            log.uyari("main window not found, top bar not added")
        return

    _tazele()

    if not _durum["kuruldu"]:
        _durum["kuruldu"] = True
        _sinyale_bagla(mw)
        _tazelemeyi_baslat()
        log.bilgi("top bar installed (logo button)")


def _sinyale_bagla(mw) -> None:
    """Refresh on workbench switch.

    The signal name can change between versions, so a few candidates are tried.
    """
    for ad in ("workbenchActivated", "workbenchActivated_"):
        sinyal = getattr(mw, ad, None)
        if sinyal is None:
            continue
        try:
            sinyal.connect(lambda *a: _tazele())
            log.ayik(f"top bar: connected to the {ad} signal")
            return
        except Exception:
            continue
    log.ayik("top bar: no workbench signal, periodic refresh will be used")


def _tazelemeyi_baslat() -> None:
    """Periodic refresh during the first minute.

    A safety belt in case there is no signal or the startup order did not
    line up. We do not run it forever: after a minute everything has
    settled, an endless timer would just waste work.
    """
    z = QtCore.QTimer()
    z.setInterval(_TAZELEME_MS)

    def tik():
        _durum["tazeleme"] += 1
        _tazele()
        if _durum["tazeleme"] >= _TAZELEME_SAYISI:
            z.stop()

    z.timeout.connect(tik)
    z.start()
    _durum["zamanlayici"] = z      # without a reference the GC collects it


def _tazele() -> None:
    """Adds the toolbar if missing; leaves it alone if present."""
    mw = _ana_pencere()
    if mw is None:
        return
    try:
        _eski_menuyu_kaldir(mw)
    except Exception as e:
        log.ayik(f"could not remove the old menu: {e}")
    try:
        _arac_cubugunu_ekle(mw)
    except Exception as e:
        log.uyari(f"could not add the top bar: {e}")


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------

def _eylemler(ebeveyn) -> list:
    """Actions that go on the toolbar.

    A FreeCAD command's QAction is only created once it is added to a menu,
    and there is no portable API to reach it; the main window's QActions are
    scanned by objectName (Gui.addCommand names the object after the
    command). If not found, we build our own action that runs the command
    via Gui.runCommand - so the toolbar is never empty.
    """
    import FreeCADGui as Gui

    mw = Gui.getMainWindow()
    mevcut = {}
    if mw is not None:
        for e in mw.findChildren(QAction):
            ad = e.objectName()
            if ad in _KOMUT_ADLARI:
                mevcut.setdefault(ad, e)

    logo = _logo()
    cikti = []
    for ad in _KOMUT_ADLARI:
        e = mevcut.get(ad)
        if e is None:
            e = _kendi_eylemimiz(ad, ebeveyn, logo)
        elif logo is not None and e.icon().isNull():
            # The command is registered but came without an icon: on an
            # icon-only toolbar it would be an invisible button.
            e.setIcon(logo)
        cikti.append(e)
    return cikti


def _kendi_eylemimiz(komut_adi: str, ebeveyn, logo):
    baslik = {
        "CADdy_ShowPanel": "Open CADdy panel",
    }.get(komut_adi, komut_adi)

    e = QAction(baslik, ebeveyn)
    e.setObjectName(komut_adi + "_yedek")
    if logo is not None:
        e.setIcon(logo)
    if komut_adi == "CADdy_ShowPanel":
        e.setShortcut("Ctrl+Shift+A")
    # Even with the text hidden, hovering should say what it is.
    e.setToolTip(baslik)

    def calistir():
        try:
            import FreeCADGui as Gui
            Gui.runCommand(komut_adi, 0)
        except Exception:
            # If the command is not registered, open the panel directly.
            if komut_adi == "CADdy_ShowPanel":
                from .dock import paneli_goster
                paneli_goster()

    e.triggered.connect(calistir)
    return e


# --------------------------------------------------------------------------
# toolbar
# --------------------------------------------------------------------------

def _arac_cubugunu_ekle(mw) -> None:
    for c in mw.findChildren(QtWidgets.QToolBar):
        if c.objectName() == _ARAC_NESNE:
            if not c.isVisible():
                c.setVisible(True)
            return

    cubuk = QtWidgets.QToolBar(ARAC_CUBUGU_ADI, mw)
    cubuk.setObjectName(_ARAC_NESNE)

    eylemler = _eylemler(cubuk)

    # LOGO ONLY. User request (see module header). With the text hidden the
    # icon is the button's only description, so _eylemler() never returns
    # an action without an icon.
    cubuk.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)

    for e in eylemler:
        cubuk.addAction(e)
    mw.addToolBar(QtCore.Qt.TopToolBarArea, cubuk)
    cubuk.setVisible(True)


# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------

def _eski_menuyu_kaldir(mw) -> None:
    """Removes the "CADdy" MENU left behind by the previous version.

    Why: the menu bar entry is not stored in FreeCAD's user.cfg, it is built
    at runtime — so once the new version stops adding it, it disappears on
    its own. BUT if the old version ran in the same session the menu stays
    on screen. This prevents "two CADdys on screen after upgrading".
    """
    try:
        cubuk = mw.menuBar()
    except Exception:
        return
    for eylem in list(cubuk.actions()):
        m = eylem.menu()
        if m is not None and m.objectName() == "CADdyUstMenu":
            cubuk.removeAction(eylem)
            log.ayik("old top menu removed")
