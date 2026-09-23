"""CADdy — an AI assistant for FreeCAD.

Layer rule (breaking it loses headless testing):

    ui/          -> conversation, execution, transport, context   MAY import
    conversation -> execution, transport, context                 MAY import
    execution/   -> (FreeCAD API + stdlib)          does NOT import Qt
    context/     -> (FreeCAD API + stdlib)          does NOT import Qt

So nothing outside `ui` ever sees QtWidgets, and the core can run headless
under `freecadcmd`.
"""

__version__ = "0.1.0"
