"""CADdy — FreeCAD icin AI yardimcisi.

Katman kurali (bozulursa bassiz test imkani kaybolur):

    ui/          -> conversation, execution, transport, context   import EDEBILIR
    conversation -> execution, transport, context                 import EDEBILIR
    execution/   -> (FreeCAD API + stdlib)          Qt import ETMEZ
    context/     -> (FreeCAD API + stdlib)          Qt import ETMEZ

Yani `ui` disindaki hicbir yer QtWidgets gormez; cekirdek `freecadcmd` ile
bassiz calistirilabilir.
"""

__version__ = "0.1.0"
