# CADdy - FreeCAD workbench registration.
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
# No logic here - only path setup, the workbench class and command
# registration. The real work is in the caddy/ package.
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
if EKLENTI_DIZINI not in sys.path:
    sys.path.insert(0, EKLENTI_DIZINI)

IKON = os.path.join(EKLENTI_DIZINI, "resources", "icons", "caddy.svg")


class CADdyWorkbench(Workbench):  # noqa: F821  (injected by FreeCAD)
    # CAREFUL: only CONSTANT values here. Do not refer to an outside name
    # (like IKON) - the class body cannot see it. Icon is assigned below.
    MenuText = "CADdy"
    ToolTip = "AI assistant inside FreeCAD"

    def Initialize(self):
        try:
            from caddy import commands
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[CADdy] failed to load:\n" + traceback.format_exc() + "\n")
            return

        adlar = list(commands.kaydet())
        self.appendToolbar("CADdy", adlar)
        self.appendMenu("CADdy", adlar)

    def Activated(self):
        # Open the panel automatically the first time the workbench is selected.
        try:
            from caddy.ui.dock import paneli_goster
            paneli_goster()
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[CADdy] could not open the panel:\n" + traceback.format_exc() + "\n")

    def GetClassName(self):
        # REQUIRED constant for pure-Python workbenches
        return "Gui::PythonWorkbench"


# Outside the class body: this is module level, IKON is visible.
CADdyWorkbench.Icon = IKON

Gui.addWorkbench(CADdyWorkbench())  # noqa: F821


# --- Permanent place in the top bar ----------------------------------------
# The workbench's own appendToolbar/appendMenu are visible ONLY while that
# workbench is active. The user wanted CADdy always at the top, so we also
# add it to the menu bar and a permanent toolbar.
#
# Commands are registered here: Initialize() only runs the first time the
# workbench is selected, but the top menu has to be populated from startup.
try:
    from caddy import commands as _komutlar
    _komutlar.kaydet()
    from caddy.ui import ust_menu as _ust
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
            "[CADdy] could not add the top bar (the workbench still works):\n"
            + _iz + "\n")
    except Exception:
        import sys as _sys
        _sys.stderr.write("[CADdy] could not add the top bar:\n" + _iz + "\n")
