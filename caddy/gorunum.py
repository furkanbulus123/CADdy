"""Captures the 3D view as PNG.

Why here and not under ui/: `conversation.py` has to call it (it runs the
visual-check turn), and by the LAYER RULE conversation cannot import ui/.
This module creates no widgets, it only returns images.

Why it returns PNG BYTES and not a file path: the image goes to the model
as a base64 `image` block in the stream-json input (see transport). There
is no reason to leave a file on disk - the temporary file is read and
deleted right away.

FreeCAD has two ways to capture the view and both need a GUI session;
freecadcmd has no ActiveView, so this CANNOT BE TESTED HEADLESS (not even
Gui.getMainWindow exists there). So every step is guarded individually and
returns None on failure - the chat must keep working even if the visual
check does not.
"""

from __future__ import annotations

import os
import tempfile

from . import log

# A reasonable size for the panel. Bigger raises the token cost directly
# (measured: even a 200x120 test image turned into a ~2.3k-token request),
# smaller loses detail.
GENISLIK = 900
YUKSEKLIK = 640


def yakalanabilir_mi() -> bool:
    """Is there a GUI session with an active 3D view."""
    try:
        import FreeCADGui as Gui
    except Exception:
        return False
    try:
        return (Gui.ActiveDocument is not None
                and Gui.ActiveDocument.ActiveView is not None)
    except Exception:
        return False


def yakala(genislik: int = GENISLIK, yukseklik: int = YUKSEKLIK) -> bytes | None:
    """Returns the active 3D view as PNG bytes; None on failure."""
    try:
        import FreeCADGui as Gui
    except Exception as e:
        log.uyari(f"could not capture the view (no GUI): {e}")
        return None

    try:
        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:
        log.uyari(f"no active 3D view: {e}")
        return None

    # The temporary file is closed FIRST: on Windows another process/library
    # cannot write to an open file, and saveImage fails silently.
    tut = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    yol = tut.name
    tut.close()

    try:
        try:
            # "Current" = the background the user sees on screen. The user
            # said "the current view": both should look at the same thing.
            gorunum.saveImage(yol, genislik, yukseklik, "Current")
        except TypeError:
            # Some versions have no background argument.
            gorunum.saveImage(yol, genislik, yukseklik)

        with open(yol, "rb") as f:
            veri = f.read()
        if not veri:
            log.uyari("view captured but the file is empty")
            return None
        return veri
    except Exception as e:
        log.uyari(f"saveImage failed: {e}")
        return _widget_ile_yakala()
    finally:
        try:
            os.unlink(yol)
        except Exception:
            pass


def yakala_cok(genislik: int = GENISLIK,
               yukseklik: int = YUKSEKLIK) -> list[bytes]:
    """Captures three angles: THE USER'S ANGLE + front + top.

    WHY THREE FRAMES. One frame means looking from one angle, and the logs
    measured the cost: from a single frame the model made TWO wrong
    diagnoses in a row ("the handle is floating", "there are two dark
    holes"), and the fix suggested by the second made the damage worse. In
    another session the user had to rotate the scene and say "I rotated it,
    just take the image and look" — the user became the camera operator.

    WHY THE FIRST FRAME IS STILL THE USER'S ANGLE. The "look at the same
    thing" rule (see yakala) was a deliberate decision and is kept; front
    and top are IN ADDITION to it. Together they cover the X-Y and Y-Z
    relations — exactly where "does the handle touch the body" is answered.

    WHY NOT ALWAYS. Three frames cost ~3x tokens and make the model read
    three images; overkill for a quick look. The caller decides
    (see conversation: one frame first, three if unresolved).

    The camera IS RESTORED: where the user was looking must not change
    because of us. If it cannot be restored, at least a warning is left.
    The restore is in `finally`, and animation is turned off BEFORE it —
    reason below; it was exactly the cause of the "it jumps somewhere weird"
    complaint.
    """
    try:
        import FreeCADGui as Gui

        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:
        log.uyari(f"multi-angle capture failed: {e}")
        tek = yakala(genislik, yukseklik)
        return [tek] if tek else []

    kamera = None
    try:
        kamera = gorunum.getCamera()
    except Exception as e:
        log.uyari(f"could not read the camera ({e}); angles will not be tried")

    kareler: list[bytes] = []
    ilk = yakala(genislik, yukseklik)          # the angle the user sees
    if ilk:
        kareler.append(ilk)

    if kamera is None:
        return kareler

    # ANIMATION IS TURNED OFF. Complaint: "after the 3 angles it goes
    # somewhere weird, it does not stay at the angle the user was looking
    # at". Cause: viewFront/viewTop do an ANIMATED transition in FreeCAD —
    # the camera moves for a while. Even when setCamera puts the old angle
    # back, the ONGOING animation carries it to the target (top view) again,
    # so the restore was silently overridden. A frame taken mid-animation
    # also shows a skewed angle. Turning it off is cheap: one flag, and
    # transitions become instant.
    animasyon = None
    try:
        animasyon = gorunum.isAnimationEnabled()
        gorunum.setAnimationEnabled(False)
    except Exception as e:                                       # noqa: BLE001
        # Missing in this version: carry on, the restore is still attempted.
        log.ayik(f"could not set the animation flag: {e}")

    try:
        for ad in ("viewFront", "viewTop"):
            try:
                getattr(gorunum, ad)()
                gorunum.fitAll()
                _cizimi_bitir()
                kare = yakala(genislik, yukseklik)
                if kare:
                    kareler.append(kare)
            except Exception as e:                               # noqa: BLE001
                log.uyari(f"{ad} could not be captured: {e}")
    finally:
        # RESTORE in finally: whatever fails in between, the user's view
        # comes back. Wrecking the user's view is a costlier bug than the
        # visual check itself.
        try:
            gorunum.setCamera(kamera)
            _cizimi_bitir()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not restore the camera: {e}")
        if animasyon:
            try:
                gorunum.setAnimationEnabled(True)
            except Exception:                                    # noqa: BLE001
                pass

    return kareler


def yakala_yakin(adlar, genislik: int = GENISLIK, yukseklik: int = YUKSEKLIK,
                 cok_aci: bool = False) -> list[bytes]:
    """Zooms the camera to THE GIVEN OBJECTS and captures.

    WHY IT EXISTS (measured). When the whole model fits in the frame the
    image is coarse: a 201 mm ship in a 900x640 frame is ~4 pixels/mm, so a
    0.6 mm thick sail is 2 pixels. That is exactly why the model missed an
    overlap. Raising the resolution makes three frames ~4x more expensive
    and still does not show what is behind; ZOOMING THE CAMERA gives ~10x
    the detail for the same tokens.

    `adlar`: FreeCAD INTERNAL NAMES (not Labels). A name that is not found
    is not skipped silently — a warning is left so the caller knows which
    were found, and it carries on with the ones that were.

    The camera is protected with the same pattern as yakala_cok: animation
    OFF (animated transitions overrode the restore) and the restore in
    `finally`. The selection is also restored — messing with the user's
    selection is not our business.
    """
    try:
        import FreeCADGui as Gui

        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"close-up failed (no GUI): {e}")
        return []

    try:
        import FreeCAD as App

        doc = App.ActiveDocument
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"close-up: no document: {e}")
        return []

    nesneler = []
    for ad in adlar:
        o = doc.getObject(ad) if doc is not None else None
        if o is None:
            log.uyari(f"close-up: no object named '{ad}', skipped")
        else:
            nesneler.append(o)
    if not nesneler:
        return []

    kamera = None
    try:
        kamera = gorunum.getCamera()
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"could not read the camera ({e}); close-up will not be tried")
        return []

    animasyon = None
    try:
        animasyon = gorunum.isAnimationEnabled()
        gorunum.setAnimationEnabled(False)
    except Exception as e:                                       # noqa: BLE001
        log.ayik(f"could not set the animation flag: {e}")

    eski_secim = []
    kareler: list[bytes] = []
    try:
        try:
            eski_secim = Gui.Selection.getSelectionEx()
        except Exception:                                        # noqa: BLE001
            eski_secim = []
        Gui.Selection.clearSelection()
        for o in nesneler:
            Gui.Selection.addSelection(doc.Name, o.Name)

        # FreeCAD's OWN "zoom to selection" command. The fallback is not to
        # build a camera from the bbox — that varies between versions; the
        # fallback is to drop to a normal fitAll and SAY so.
        yaklasti = False
        try:
            Gui.SendMsgToActiveView("ViewSelection")
            yaklasti = True
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"ViewSelection did not work ({e}); fell back to the full frame")
            try:
                gorunum.fitAll()
            except Exception:                                    # noqa: BLE001
                pass
        _cizimi_bitir()

        aci_listesi = [None]
        if cok_aci:
            aci_listesi = [None, "viewFront", "viewTop"]
        for aci in aci_listesi:
            if aci is not None:
                try:
                    getattr(gorunum, aci)()
                    if yaklasti:
                        Gui.SendMsgToActiveView("ViewSelection")
                    _cizimi_bitir()
                except Exception as e:                           # noqa: BLE001
                    log.uyari(f"{aci} (close-up) could not be captured: {e}")
                    continue
            kare = yakala(genislik, yukseklik)
            if kare:
                kareler.append(kare)
    finally:
        try:
            Gui.Selection.clearSelection()
            for s in eski_secim:
                try:
                    Gui.Selection.addSelection(s.Object)
                except Exception:                                # noqa: BLE001
                    pass
        except Exception:                                        # noqa: BLE001
            pass
        try:
            gorunum.setCamera(kamera)
            _cizimi_bitir()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not restore the camera (close-up): {e}")
        if animasyon:
            try:
                gorunum.setAnimationEnabled(True)
            except Exception:                                    # noqa: BLE001
                pass

    return kareler


def _cizimi_bitir() -> None:
    """Flush the pending view update to the SCREEN.

    saveImage reads from the OpenGL buffer; called right after an angle
    change it can grab a frame that has not been drawn yet. Same after the
    camera restore: the user would briefly see a frame between old and new.
    """
    try:
        import FreeCADGui as Gui

        Gui.updateGui()
    except Exception:                                            # noqa: BLE001
        pass


def _widget_ile_yakala() -> bytes | None:
    """If saveImage fails: grab the 3D widget itself.

    A fallback, because saveImage reads from the OpenGL buffer and can come
    out empty with some driver / remote desktop combinations.
    QWidget.grab() takes whatever is on screen - lower quality, but better
    than nothing.
    """
    try:
        import FreeCADGui as Gui
        from PySide import QtCore

        # There is no portable way to the ActiveView's Qt widget; grabbing
        # the main window's central area is the simplest method that works.
        mw = Gui.getMainWindow()
        if mw is None:
            return None
        resim = mw.centralWidget().grab()
        tampon = QtCore.QBuffer()
        tampon.open(QtCore.QIODevice.WriteOnly)
        if not resim.save(tampon, "PNG"):
            return None
        return bytes(tampon.data())
    except Exception as e:
        log.uyari(f"widget grab failed too: {e}")
        return None
