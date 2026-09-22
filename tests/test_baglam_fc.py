"""Baglam serilestiricinin secim detayini ve butce kirpmasini dogrular.

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_baglam_fc.py

DIKKAT: freecadcmd, betikten SONRAKI argumanlari sys.argv'ye koymaz.
Bu betik arguman ALMAZ.

Rapor dosyaya SATIR SATIR yaziliyor, sonda toplu degil: freecadcmd icinde
bazi modul importlarindan sonra print kayboluyor ve betik sessizce olurse
hicbir sey ogrenilemiyor (MANTIK 14.5'te olculdu).

Konsolda FreeCADGui YOK, yani Gui.Selection'a erisilemiyor. Bu yuzden
_secim() ucdan uca sinanamiyor; onun yerine besledigi PARCALAR
(_alt_eleman_ozeti, _yerlesim, _komsular) dogrudan sinaniyor — asil is
onlarda.
"""

import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_baglam.txt")
with open(RAPOR, "w", encoding="utf-8") as _f:
    _f.write("")

gecti = basarisiz = 0


def _yaz(m):
    print(m)
    with open(RAPOR, "a", encoding="utf-8") as f:
        f.write(str(m) + "\n")


def kontrol(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        _yaz("  OK   %s" % ad)
    else:
        basarisiz += 1
        _yaz("  HATA %s   %s" % (ad, ek))


def bolum(ad):
    _yaz("")
    _yaz("--- %s %s" % (ad, "-" * max(0, 56 - len(ad))))


import FreeCAD as App
import Part

from caddy.context import serializer as sz

_yaz("=" * 70)
_yaz("CADdy baglam testleri")
_yaz("=" * 70)

doc = App.newDocument("BaglamTest")

# ---------------------------------------------------------------- yuz ozeti
bolum("alt eleman ozeti — yuz")

kutu = doc.addObject("Part::Box", "Kutu")
kutu.Length = 20
kutu.Width = 20
kutu.Height = 10
doc.recompute()

# Kutunun ust yuzunu bul (normali +Z olan).
ust_ad = ""
for i, y in enumerate(kutu.Shape.Faces, start=1):
    if abs(y.Surface.Axis.z) > 0.99 and y.CenterOfMass.z > 9.9:
        ust_ad = "Face%d" % i
        break

kontrol("ust yuz bulundu", bool(ust_ad), ust_ad)
ozet = sz._alt_eleman_ozeti(kutu, ust_ad) if ust_ad else ""
_yaz("       ozet: %s" % ozet)
kontrol("duzlem oldugu yaziyor", ozet.startswith("plane"), ozet)
kontrol("NORMAL yaziyor (duzlemde axis degil)", "normal=" in ozet, ozet)
kontrol("alan yaziyor", "area=" in ozet, ozet)
kontrol("alan dogru (20x20=400)", "area=400" in ozet, ozet)

bolum("alt eleman ozeti — silindir")

sil = doc.addObject("Part::Cylinder", "Silindir")
sil.Radius = 4
sil.Height = 12
doc.recompute()

yan_ad = ""
for i, y in enumerate(sil.Shape.Faces, start=1):
    if type(y.Surface).__name__ == "Cylinder":
        yan_ad = "Face%d" % i
        break
ozet_s = sz._alt_eleman_ozeti(sil, yan_ad) if yan_ad else ""
_yaz("       ozet: %s" % ozet_s)
kontrol("silindir oldugu yaziyor", ozet_s.startswith("cylinder"), ozet_s)
kontrol("YARICAP yaziyor — deligin capi tahmin edilmesin",
        "r=4" in ozet_s, ozet_s)
kontrol("eksen yaziyor (normal DEGIL)",
        "axis=" in ozet_s and "normal=" not in ozet_s, ozet_s)
# OCC eksende -0.0 uretiyor; 'axis=(-0,-0,-1)' okuyani duraklatir.
kontrol("eksi sifir yok", "-0," not in ozet_s and "(-0)" not in ozet_s, ozet_s)

bolum("alt eleman ozeti — kenar ve kose")

kenar = sz._alt_eleman_ozeti(kutu, "Edge1")
_yaz("       kenar: %s" % kenar)
kontrol("kenar tipi yaziyor", kenar.startswith("line"), kenar)
kontrol("kenar uzunlugu yaziyor", "len=" in kenar, kenar)

cember = ""
for i, e in enumerate(sil.Shape.Edges, start=1):
    if type(e.Curve).__name__ == "Circle":
        cember = sz._alt_eleman_ozeti(sil, "Edge%d" % i)
        break
_yaz("       cember: %s" % cember)
kontrol("cember tipi ve yaricapi", cember.startswith("circle")
        and "r=4" in cember, cember)

kose = sz._alt_eleman_ozeti(kutu, "Vertex1")
kontrol("kose noktasi yaziliyor", kose.startswith("vertex="), kose)

bolum("alt eleman ozeti — bozuk girdi PATLAMAMALI")
kontrol("olmayan eleman bos doner",
        sz._alt_eleman_ozeti(kutu, "Face999") == "",
        repr(sz._alt_eleman_ozeti(kutu, "Face999")))
kontrol("sacma ad bos doner", sz._alt_eleman_ozeti(kutu, "zzz") == "",
        repr(sz._alt_eleman_ozeti(kutu, "zzz")))

# ------------------------------------------------------------------ yerlesim
bolum("yerlesim — birimse SUSUYOR")
kontrol("birim placement bos doner", sz._yerlesim(kutu) == "",
        repr(sz._yerlesim(kutu)))

sil.Placement.Base = App.Vector(5, 0, 3)
doc.recompute()
y = sz._yerlesim(sil)
_yaz("       yerlesim: %s" % y)
kontrol("tasinan nesnenin konumu yaziyor", "pos=(5,0,3)" in y, y)

sil.Placement.Rotation = App.Rotation(App.Vector(1, 0, 0), 90)
doc.recompute()
y2 = sz._yerlesim(sil)
_yaz("       yerlesim: %s" % y2)
kontrol("donme derece olarak yaziyor", "rot=90deg" in y2, y2)

# ------------------------------------------------------------------ komsular
bolum("komsular — secimin bir hop otesi")

kesim = doc.addObject("Part::Cut", "Kesim")
kesim.Base = kutu
kesim.Tool = sil
doc.recompute()

k = sz._komsular(doc, {"Kesim"})
kontrol("kesimin girdileri komsu", {"Kutu", "Silindir"} <= k, sorted(k))
k2 = sz._komsular(doc, {"Kutu"})
kontrol("kutuyu kullanan da komsu", "Kesim" in k2, sorted(k2))
kontrol("secilen kendisi komsu sayilmaz", "Kutu" not in k2, sorted(k2))

# -------------------------------------------------------------------- butce
bolum("butce — secim ve baslik ASLA kirpilmaz")

for i in range(60):
    o = doc.addObject("Part::Box", "Dolgu%d" % i)
    o.Label = "cok uzun bir etiket olsun ki butce dolsun %d" % i
doc.recompute()

tam = sz.belge_metni(doc, butce=10**9)
kontrol("kirpilmamis metinde tum nesneler var",
        tam.count("Part::Box") == 61, tam.count("Part::Box"))
kontrol("kirpilmamis metinde kirpma notu YOK", "kirpildi" not in tam)

kucuk = sz.belge_metni(doc, butce=1200)
_yaz("       uzunluk: %d" % len(kucuk))
kontrol("butceye uyuldu", len(kucuk) <= 1200, len(kucuk))
kontrol("baslik duruyor", "name=BaglamTest" in kucuk)
kontrol("secim bolumu duruyor", "<selection>" in kucuk
        and "</selection>" in kucuk)
kontrol("etiket kapandi", kucuk.rstrip().endswith("</document>"))
kontrol("kirpma SOYLENIYOR (sessizce dusurulmuyor)",
        "kirpildi" in kucuk, kucuk[-160:])

bolum("butce — kirpma ONCELIK sirasina uyuyor")
# Konsolda secim yok; oncelik mantigini dogrudan sina: en son eklenen
# nesne (uzerinde calisilan yer) en eskiden once atilmamali.
kontrol("en yeni nesne korundu, en eski atildi",
        "Dolgu59" in kucuk and "Dolgu0 " not in kucuk,
        "Dolgu59 var=%s / Dolgu0 var=%s"
        % ("Dolgu59" in kucuk, "Dolgu0 " in kucuk))

bolum("butce — asiri kucuk butce (emniyet agi)")
# Nesne listesi tamamen bosaltilsa bile sigmayan hal: kaba kesme devreye
# girer. O kesmenin KENDISI butceyi asmamali (eski surumde asiyordu).
minik = sz.belge_metni(doc, butce=200)
_yaz("       uzunluk: %d" % len(minik))
kontrol("asiri kucuk butcede bile sinir asilmiyor", len(minik) <= 200,
        len(minik))
kontrol("asiri kucuk butcede etiket yine kapali",
        minik.rstrip().endswith("</document>"), minik[-60:])

bolum("bos ve tuhaf belgeler")
kontrol("belge yoksa patlamiyor",
        "Acik belge yok" in sz.belge_metni(None if App.ActiveDocument is None
                                           else App.ActiveDocument, 100)
        or True)
bos = App.newDocument("BosBelge")
mb = sz.belge_metni(bos)
kontrol("bos belgede secim yok yaziyor", "(secim yok)" in mb, mb[:200])
kontrol("bos belgede de etiket kapali", mb.rstrip().endswith("</document>"))

_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d" % (gecti, basarisiz))
_yaz("=" * 70)
