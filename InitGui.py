# CADdy - FreeCAD workbench kaydi.
#
# ================== BURAYA DOKUNMADAN ONCE OKU ==================
#
# Bu dosya normal bir modul gibi import EDILMEZ. FreeCAD onu
# FreeCADGuiInit.py icindeki bir FONKSIYONUN icinden
#
#     exec(compile(open(dosya).read(), dosya, "exec"))
#
# ile calistirir. Argumansiz exec() bir fonksiyonun icinde cagrilinca
# globals() ve locals() AYRI sozluklerdir. Sonucu:
#
#   * Buradaki "modul seviyesi" atamalar locals'a duser.
#   * Modul seviyesindeki KOD onlari gorur (once locals'a bakar).
#   * Ama bir SINIF GOVDESI ya da FONKSIYON GOVDESI ad aramasini
#     dogrudan globals'a yapar -> buradaki adlari GOREMEZ.
#
# Fiilen carpildi: sinif govdesinde "Icon = IKON" yazinca FreeCAD
# acilista sessizce
#     name 'IKON' is not defined
# verip workbench'i HIC kaydetmedi. Liste bos, hata yalnizca stderr'de.
#
# KURAL: sinif ve metot govdelerinde bu dosyanin kendi adlarini KULLANMA.
#   - Sabitleri sinif tanimindan SONRA ata (asagida Icon boyle atanmis).
#   - Metot icinde ihtiyacin olani ORADA import et.
#
# FreeCAD'in kendi OpenSCAD/InitGui.py'si de bu yuzden ikonu __init__
# icinde self.__class__.Icon = ... diye atiyor.
#
# Burada mantik YOK - sadece yol ayari, workbench sinifi ve komut kaydi.
# Gercek is caddy/ paketinde.
# ================================================================

import os
import sys


def _eklenti_dizini():
    # __file__ KULLANILMAZ, cunku burada TANIMSIZ degil YANLIS olur:
    # argumansiz exec cagiran fonksiyonun globals'i miras alinir ve oradaki
    # __file__ FreeCADGuiInit.py'yi gosterir -> ikon yolu FreeCAD'in kendi
    # dizinine cikar. (Testte tam bunu yakaladik: yol tests/ altina cikti.)
    #
    # compile()'a gecilen ad her zaman BU dosyadir; co_filename onu verir.
    yol = sys._getframe().f_code.co_filename
    if not os.path.isabs(yol) or not os.path.exists(yol):
        yol = globals().get("__file__", yol)
    return os.path.dirname(os.path.abspath(yol))


EKLENTI_DIZINI = _eklenti_dizini()
if EKLENTI_DIZINI not in sys.path:
    sys.path.insert(0, EKLENTI_DIZINI)

IKON = os.path.join(EKLENTI_DIZINI, "resources", "icons", "caddy.svg")


class CADdyWorkbench(Workbench):  # noqa: F821  (FreeCAD enjekte ediyor)
    # DIKKAT: burada yalnizca SABIT deger olabilir. Disaridan gelen bir ada
    # (IKON gibi) basvurma - sinif govdesi onu goremez. Icon asagida atandi.
    MenuText = "CADdy"
    ToolTip = "FreeCAD icinde AI yardimcisi"

    def Initialize(self):
        try:
            from caddy import commands
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[CADdy] yuklenemedi:\n" + traceback.format_exc() + "\n")
            return

        adlar = list(commands.kaydet())
        self.appendToolbar("CADdy", adlar)
        self.appendMenu("CADdy", adlar)

    def Activated(self):
        # Workbench'e ilk gecildiginde paneli kendiliginden ac.
        try:
            from caddy.ui.dock import paneli_goster
            paneli_goster()
        except Exception:
            import traceback

            import FreeCAD
            FreeCAD.Console.PrintError(
                "[CADdy] panel acilamadi:\n" + traceback.format_exc() + "\n")

    def GetClassName(self):
        # Saf Python workbench'ler icin ZORUNLU sabit
        return "Gui::PythonWorkbench"


# Sinif govdesinin disinda: burasi modul seviyesi, IKON gorunur.
CADdyWorkbench.Icon = IKON

Gui.addWorkbench(CADdyWorkbench())  # noqa: F821


# --- Ust seride kalici yer -------------------------------------------------
# Workbench'in kendi appendToolbar/appendMenu'su YALNIZCA o workbench
# aktifken gorunur. Kullanici CADdy'nin hep ustte durmasini istedi, o yuzden
# menu cubuguna ve kalici bir arac cubuguna ayrica giriyoruz.
#
# Komutlar burada kaydediliyor: Initialize() yalnizca workbench'e ilk
# gecildiginde calisiyor, ama ust menunun acilistan itibaren dolu olmasi
# lazim.
try:
    from caddy import commands as _komutlar
    _komutlar.kaydet()
    from caddy.ui import ust_menu as _ust
    _ust.yerlestir()
except Exception:
    # DIKKAT: bu blok KENDISI patlamamali. Ilk yazimda burada
    # `import FreeCAD` vardi ve FreeCAD'in olmadigi ortamda (kapsam testi)
    # istisna disari kacip butun InitGui'yi dusurdu - yani "hata
    # yakalayici"nin kendisi hataya sebep oldu. Test bunu yakaladi.
    import traceback as _tb

    _iz = _tb.format_exc()
    try:
        import FreeCAD as _App
        _App.Console.PrintWarning(
            "[CADdy] ust serit eklenemedi (workbench yine calisir):\n"
            + _iz + "\n")
    except Exception:
        import sys as _sys
        _sys.stderr.write("[CADdy] ust serit eklenemedi:\n" + _iz + "\n")
