"""InitGui.py'yi FreeCAD'in calistirdigi GIBI calistirir.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe" tests\\test_initgui_kapsam.py

Sinanan sey saf Python kapsam (scope) davranisi, ama betik InitGui.py'yi
gercekten calistirdigi icin `FreeCAD` modulu YINE DE gerekiyor — sistem
python'u ile calistirilirsa ModuleNotFoundError verir. freecadcmd de olmaz:
o, betikten sonraki isi kendi yonetir ve FreeCADGui saplamasi eksiktir.
Dogru yorumlayici FreeCAD'in kendi bin\\python.exe'si.

NEDEN VAR: FreeCAD, InitGui.py'yi FreeCADGuiInit.py icindeki bir FONKSIYONUN
icinden argumansiz exec() ile calistirir. Fonksiyon icinde argumansiz exec,
globals() ve locals() olarak AYRI sozlukler kullanir. O yuzden:

    IKON = "..."                 <- locals'a duser
    class X(Workbench):
        Icon = IKON              <- sinif govdesi GLOBALS'a bakar -> NameError

Bu hata fiilen yasandi: FreeCAD acilista

    name 'IKON' is not defined

deyip workbench'i hic kaydetmedi; workbench listesi bos kaldi ve hata
yalnizca stderr'de gorundu (Report view'da bile degil).

Ilk elle denememde tek sozlukle exec(kod, g) yaptigim icin test YANLIS
gecmisti. Bu dosya o hatayi bir daha yapmamak icin var.
"""

import os
import sys
import traceback

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

gecti = basarisiz = 0


def kontrol(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("  OK   %s" % ad)
    else:
        basarisiz += 1
        print("  HATA %s   %s" % (ad, ek))


class SahteWorkbench(object):
    """Gui.Workbench yerine gecer."""

    def appendToolbar(self, ad, komutlar):
        pass

    def appendMenu(self, ad, komutlar):
        pass


class SahteGui(object):
    def __init__(self):
        self.kayitli = []
        self.komutlar = []
        self.Workbench = SahteWorkbench

    def addWorkbench(self, wb):
        self.kayitli.append(wb)

    def addCommand(self, ad, nesne):
        self.komutlar.append(ad)

    def getMainWindow(self):
        # Bassiz ortamda ana pencere yok — ust_menu bunu duzgun karsilamali.
        return None


def freecad_gibi_calistir(dosya, gui):
    """FreeCADGuiInit.py'nin RunInitGuiPy'si ile AYNI sekli.

    Kritik nokta: exec BIR FONKSIYONUN ICINDE ve argumansiz cagriliyor.
    Boylece globals() != locals() olur - hatanin dogdugu tam kosul.
    """
    Gui = gui                     # noqa: F841  (InitGui.py bunu bekliyor)
    FreeCADGui = gui              # noqa: F841
    Workbench = SahteWorkbench    # noqa: F841
    with open(dosya, "r", encoding="utf-8") as f:
        kod = f.read()
    exec(compile(kod, dosya, "exec"))


print("InitGui.py - FreeCAD'in kapsam kosullarinda")
gui = SahteGui()
hata = None
try:
    freecad_gibi_calistir(os.path.join(KOK, "InitGui.py"), gui)
except Exception:
    hata = traceback.format_exc()

kontrol("NameError/istisna yok", hata is None, (hata or "")[-500:])
kontrol("addWorkbench cagrildi", len(gui.kayitli) == 1, len(gui.kayitli))

if gui.kayitli:
    wb = gui.kayitli[0]
    kontrol("MenuText CADdy", getattr(wb, "MenuText", None) == "CADdy",
            getattr(wb, "MenuText", None))
    kontrol("GetClassName Gui::PythonWorkbench",
            wb.GetClassName() == "Gui::PythonWorkbench", wb.GetClassName())

    ikon = getattr(type(wb), "Icon", None)
    kontrol("Icon atandi", bool(ikon), ikon)
    kontrol("Icon dosyasi gercekten var", ikon and os.path.isfile(ikon), ikon)

kontrol("eklenti dizini sys.path'e eklendi",
        any(os.path.normcase(KOK) == os.path.normcase(p) for p in sys.path))

# --- ust serit blogu -------------------------------------------------------
# Kullanici "ust menu yok" dedi. Ilk saptama: bu blok InitGui'nin SONUNDA
# duruyor ve orada patlarsa sessizce kayboluyordu — ustelik hata
# yakalayicinin KENDISI (import FreeCAD) bu ortamda patliyordu ve butun
# InitGui'yi dusuruyordu. Ikisi de burada sinaniyor.
# Bu ortamda caddy.commands "import FreeCAD" yaptigi icin blok zaten
# patlar — beklenen. Sinanacak sey blogun patlamasi degil, patlarken
# BUTUN InitGui'yi goturmemesi: workbench yine kayitli kalmali.
# (Komutlarin gercekten kaydedildigi FreeCAD'li testte sinaniyor.)
kontrol("ust serit hatasi workbench'i goturmuyor", len(gui.kayitli) == 1,
        len(gui.kayitli))
kontrol("hata yakalayici KENDISI patlamiyor", hata is None,
        (hata or "")[-300:])

print("")
print("%d gecti, %d basarisiz" % (gecti, basarisiz))
sys.exit(1 if basarisiz else 0)
