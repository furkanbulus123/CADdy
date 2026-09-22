"""Eklentinin FreeCAD tarafindan yuklenebilirligini arayuzsuz dogrular.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_yukleme_fc.py

Sinadigi seyler:
  * package.xml FreeCAD'in KENDI ayristiricisindan geciyor mu
  * Mod klasorundeki junction gorunuyor mu
  * Arayuz disi moduller FreeCAD'in Python 3.11'inde import edilebiliyor mu
    (3D_Models venv'i 3.12; buradaki kod ikisinde de calismali)

FreeCADGui gerektiren moduller (commands, ui.*) BILEREK sinanmiyor -
konsol modunda FreeCADGui yok.

NOT: freecadcmd icinde Qt import edilince sys.stdout yeniden yonlendiriliyor
ve print() ciktisi kayboluyor. Rapor bu yuzden DOSYAYA da yaziliyor:
tests/_son_rapor.txt
"""

import os
import sys
import traceback

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

import FreeCAD as App

gecti = basarisiz = 0
_satirlar = []
RAPOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_son_rapor.txt")


def yaz(s):
    _satirlar.append(str(s))
    try:
        print(s)
    except Exception:
        pass


def kontrol(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        yaz("  OK   %s" % ad)
    else:
        basarisiz += 1
        yaz("  HATA %s   %s" % (ad, ek))


def raporu_kaydet():
    with open(RAPOR, "w", encoding="utf-8") as f:
        f.write("\n".join(_satirlar) + "\n")


yaz("1) python surumu: %s" % sys.version.split()[0])
kontrol("FreeCAD Python 3.11", sys.version_info[:2] == (3, 11), sys.version_info[:2])

yaz("2) package.xml - FreeCAD'in kendi ayristiricisi")
try:
    m = App.Metadata(os.path.join(KOK, "package.xml"))
    kontrol("ayristi", True)
    kontrol("ad CADdy", m.Name == "CADdy", m.Name)
    kontrol("surum var", str(m.Version) != "", m.Version)
    icerik = m.Content
    kontrol("workbench icerigi var", "workbench" in icerik, list(icerik.keys()))
    wb = icerik["workbench"][0]
    kontrol("classname dogru", wb.Classname == "CADdyWorkbench", wb.Classname)
    kontrol("subdirectory kok", wb.Subdirectory in ("./", ".", "./\\", ".\\"),
            repr(wb.Subdirectory))
    kontrol("bu FreeCAD surumunu destekliyor", m.supportsCurrentFreeCAD())
except Exception:
    kontrol("ayristi", False, traceback.format_exc())

yaz("3) Mod klasorundeki junction")
mod = os.path.join(App.getUserAppDataDir(), "Mod")
hedef = os.path.join(mod, "CADdy")
kontrol("user Mod dizini var", os.path.isdir(mod), mod)
kontrol("CADdy gorunuyor", os.path.isdir(hedef), hedef)
kontrol("InitGui.py erisilebilir", os.path.isfile(os.path.join(hedef, "InitGui.py")))

yaz("4) arayuz disi modul importlari")
for ad in ("caddy", "caddy.log", "caddy.config", "caddy.locate",
           "caddy.execution.blocks", "caddy.execution.executor",
           "caddy.context.serializer", "caddy.transport.framing"):
    try:
        __import__(ad)
        kontrol(ad, True)
    except Exception:
        kontrol(ad, False, traceback.format_exc(limit=2))

yaz("5) PySide (QtCore) FreeCAD icinde")
try:
    from PySide import QtCore  # noqa: F401
    kontrol("PySide shim calisiyor", True)
    import caddy.transport.process  # noqa: F401
    import caddy.transport.transport  # noqa: F401
    kontrol("transport modulleri import edildi", True)
except Exception:
    kontrol("PySide/transport", False, traceback.format_exc(limit=3))

yaz("5b) ust serit modulu (kullanici 'ust menu yok' dedi)")
try:
    from caddy import commands as _kmd
    from caddy.ui import ust_menu as _ust
    kontrol("ust_menu import edildi", True)
    kontrol("QAction bulundu (PySide6'da QtGui'ye tasindi)",
            _ust.QAction is not None)
    # Ust serit artik komutlarin HEPSINI degil, yalnizca paneli acani
    # gosteriyor. Kullanici: "sadece logosu gozuksun", "AI ile geri al
    # falan gozukmesin". Bu yuzden kontrol "esitlik" degil "ALT KUME":
    # ust seritteki her komut kayitli olmali, ama her kayitli komut ust
    # seritte olmak zorunda degil.
    kayitli = {a for a, _ in _kmd.KOMUTLAR}
    kontrol("ust serit komutlari kayitli komutlarin alt kumesi",
            set(_ust._KOMUT_ADLARI) <= kayitli,
            (_ust._KOMUT_ADLARI, sorted(kayitli)))
    kontrol("ust seritte YALNIZCA paneli acan komut var",
            tuple(_ust._KOMUT_ADLARI) == ("CADdy_ShowPanel",),
            _ust._KOMUT_ADLARI)
    # Geri al komutu KAYBOLMADI - workbench'in kendi menusunde duruyor.
    kontrol("geri al komutu hala kayitli (workbench menusunde)",
            "CADdy_UndoLastAIChange" in kayitli, sorted(kayitli))
    # Metin degil logo gosterilecek: ikon dosyasi gercekten bulunmali,
    # yoksa ikon-only cubukta tiklanamaz bir bosluk olur.
    import os as _os
    _ikon_yolu = _os.path.join(KOK, "resources", "icons", "caddy.svg")
    kontrol("logo dosyasi var (ikon-only cubugun tek anlatimi)",
            _os.path.exists(_ikon_yolu), _ikon_yolu)
    # GUI yok: yerlestir() PATLAMADAN sessizce ertelemeli.
    _ust.yerlestir()
    kontrol("GUI yokken yerlestir() patlamiyor", True)
    kontrol("tazeleme fonksiyonu var (menu cubugu yeniden kuruluyor)",
            callable(getattr(_ust, "_tazele", None)))
except Exception:
    kontrol("ust serit modulu", False, traceback.format_exc(limit=3))

yaz("6) claude.exe bulunabiliyor mu")
try:
    from caddy import locate
    yol = locate.claude_exe()
    kontrol("bulundu", os.path.isfile(str(yol)), yol)
    yaz("     %s" % yol)
except Exception as e:
    kontrol("bulundu", False, str(e))

yaz("7) belge serilestirici")
try:
    from caddy.context import serializer
    doc = App.newDocument("SerTest")
    k = doc.addObject("Part::Box", "Kutu")
    k.Length = 12
    doc.recompute()
    metin = serializer.belge_metni(doc)
    kontrol("<document> uretti", metin.startswith("<document>"))
    kontrol("nesneyi listeledi", "Kutu" in metin and "Part::Box" in metin)
    kontrol("olcu var", "12" in metin, metin[:300])
    kontrol("butce icinde", len(metin) < serializer.BUTCE)
    App.closeDocument(doc.Name)
except Exception:
    kontrol("serilestirici", False, traceback.format_exc(limit=3))

yaz("")
yaz("%d gecti, %d basarisiz" % (gecti, basarisiz))
raporu_kaydet()
if basarisiz:
    sys.exit(1)
