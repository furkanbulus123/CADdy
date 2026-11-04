# KediCAD - FreeCAD workbench registration.
#
# ================== READ THIS BEFORE TOUCHING THIS FILE ==================
#
# This file is NOT imported like a normal module. FreeCAD runs it from
# inside a FUNCTION in FreeCADGuiInit.py with
#
#     exec(compile(open(file).read(), file, "exec"))
#
# When exec() is called without arguments inside a function, globals() and
# locals() are SEPARATE dicts. As a result:
#
#   * "Module level" assignments here land in locals.
#   * Module-level CODE sees them (it looks in locals first).
#   * But a CLASS BODY or FUNCTION BODY looks names up directly in
#     globals -> it CANNOT see the names defined here.
#
# This actually bit us: writing "Icon = IKON" in the class body made
# FreeCAD silently report
#     name 'IKON' is not defined
# at startup and NOT register the workbench at all. Empty list, the error
# only on stderr.
#
# RULE: do not use this file's own names inside class or method bodies.
#   - Assign constants AFTER the class definition (Icon is set that way below).
#   - Import whatever a method needs INSIDE that method.
#
# FreeCAD's own OpenSCAD/InitGui.py sets its icon in __init__ as
# self.__class__.Icon = ... for the same reason.
#
# No logic here - only the icon path, the workbench class and command
# registration. The real work is in the kedicad/ package.
# =========================================================================

import os
import sys


def _eklenti_dizini():
    # __file__ is NOT used, because here it is not UNDEFINED but WRONG:
    # exec without arguments inherits the calling function's globals, and
    # __file__ there points to FreeCADGuiInit.py -> the icon path ends up in
    # FreeCAD's own directory. (A test caught exactly this: the path pointed
    # under tests/.)
    #
    # The name passed to compile() is always THIS file; co_filename gives it.
    yol = sys._getframe().f_code.co_filename
    if not os.path.isabs(yol) or not os.path.exists(yol):
        yol = globals().get("__file__", yol)
    return os.path.dirname(os.path.abspath(yol))


EKLENTI_DIZINI = _eklenti_dizini()
# sys.path is NOT touched: FreeCAD itself puts Mod/KediCAD on sys.path before
# running this file (measured in 1.1: both "Mod\KediCAD" and "Mod\KediCAD\."
# are there, and `import kedicad` works). The Addon Index forbids addons from
# editing sys.path, and an earlier insert here was redundant anyway.

IKON = os.path.join(EKLENTI_DIZINI, "resources", "icons", "kedicad.svg")


class KediCADWorkbench(Workbench):  # noqa: F821  (injected by FreeCAD)
    # CAREFUL: only CONSTANT values here. Do not refer to an outside name
    # (like IKON) - the class body cannot see it. Icon is assigned below.
    MenuText = "KediCAD"
    ToolTip = "AI assistant inside FreeCAD"

    def Initialize(self):
        try:
            from kedicad import commands
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[KediCAD] failed to load:\n" + traceback.format_exc() + "\n")
            return

        commands.kaydet()
        self.appendToolbar("KediCAD", list(commands.ARAC_CUBUGU))
        self.appendMenu("KediCAD", list(commands.ARAC_CUBUGU)
                        + ["Separator", "KediCAD_ShowEverywhere"])

    def Activated(self):
        # Open the panel automatically the first time the workbench is selected.
        try:
            from kedicad.ui.dock import paneli_goster
            paneli_goster()
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[KediCAD] could not open the panel:\n" + traceback.format_exc() + "\n")

    def GetClassName(self):
        # REQUIRED constant for pure-Python workbenches
        return "Gui::PythonWorkbench"


# Outside the class body: this is module level, IKON is visible.
KediCADWorkbench.Icon = IKON

Gui.addWorkbench(KediCADWorkbench())  # noqa: F821


# --- Optional: the cat button in every workbench ---------------------------
# The workbench's own appendToolbar/appendMenu are visible ONLY while that
# workbench is active. The user wanted KediCAD reachable from anywhere, so a
# permanent toolbar exists (kedicad/ui/ust_menu.py) — but the Addon Index rule
# is that an addon keeps its toolbars to its OWN workbench. So it is OFF by
# default and the user turns it on from the KediCAD menu ("Show KediCAD button
# in every workbench"); the choice is stored in user.cfg.
#
# With it off, NOTHING runs here at startup — not even a PySide import.
# Commands are registered here only when needed: Initialize() runs the first
# time the workbench is selected, but the top bar has to exist from startup.
try:
    from kedicad import config as _ayar
    if _ayar.bayrak("ShowEverywhere"):
        from kedicad import commands as _komutlar
        _komutlar.kaydet()
        from kedicad.ui import ust_menu as _ust
        _ust.yerlestir()
except Exception:
    # CAREFUL: this block must not fail ITSELF. The first version had
    # `import FreeCAD` here, and in an environment without FreeCAD (the
    # coverage test) the exception escaped and took down all of InitGui -
    # the "error handler" itself caused the error. The test caught it.
    import traceback as _tb

    _iz = _tb.format_exc()
    try:
        import FreeCAD as _App
        _App.Console.PrintWarning(
            "[KediCAD] could not add the top bar (the workbench still works):\n"
            + _iz + "\n")
    except Exception:
        import sys as _sys
        _sys.stderr.write("[KediCAD] could not add the top bar:\n" + _iz + "\n")
