"""Cok acili gorunum yakalama — kameranin GERI GELDIGI kanitlanir.

    "C:\\...\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_gorunum_fc.py

gorunum.py'nin docstring'i "BASSIZ TEST EDILEMEZ" diyordu ve dogruydu:
gercek bir 3B gorunum freecadcmd'de yok. Ama modul FreeCADGui'yi FONKSIYON
ICINDE import ediyor — yani sys.modules'a SAHTE bir FreeCADGui koyup CAGRI
SIRASINI sinayabiliyoruz. Sinanan sey goruntunun kendisi degil (o gercekten
bassiz olculemez), KAMERAYA NE YAPILDIGI.

Sinadigi sikayet: "3B goruntuleri aldiktan sonra sacma bir yere gidiyor,
kullanicinin ilk baktigi acida kalmiyor". Sebep: viewFront/viewTop
canlandirmali gecis yapiyor ve setCamera ile geri konan aciyi SUREN animasyon
tekrar eziyordu.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_gorunum.txt")
with open(RAPOR, "w", encoding="utf-8") as _f:
    _f.write("")

gecti = basarisiz = 0


def _yaz(m):
    try:
        print(m)
    except Exception:
        pass
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


_yaz("=" * 70)
_yaz("CADdy 3B gorunum yakalama testleri")
_yaz("=" * 70)


class SahteGorunum:
    """Gercek View3DInventorPy'nin bu modulun dokundugu yuzeyi kadari."""

    def __init__(self, patlat: str = "") -> None:
        self.gunluk: list[str] = []
        self.kamera = "KULLANICININ_ACISI"
        self.animasyon = True
        self._patlat = patlat            # bu cagri istisna firlatsin

    def _kay(self, ad):
        self.gunluk.append(ad)
        if ad == self._patlat:
            raise RuntimeError("kasten patlatildi: " + ad)

    def getCamera(self):
        self._kay("getCamera")
        return self.kamera

    def setCamera(self, k):
        self._kay("setCamera")
        self.kamera = k

    def isAnimationEnabled(self):
        return self.animasyon

    def setAnimationEnabled(self, a):
        self._kay("animasyon=%s" % ("acik" if a else "kapali"))
        self.animasyon = a

    def viewFront(self):
        self._kay("viewFront")
        self.kamera = "ON"

    def viewTop(self):
        self._kay("viewTop")
        self.kamera = "UST"

    def fitAll(self):
        self._kay("fitAll")

    def saveImage(self, yol, g, y, arka=None):
        self._kay("saveImage(%s)" % self.kamera)
        with open(yol, "wb") as f:
            f.write(b"PNG" + self.kamera.encode("ascii"))


class SahteSecim:
    """Gui.Selection'in bu modulun dokundugu yuzeyi."""

    def __init__(self, gunluk) -> None:
        self._gunluk = gunluk
        self.secili: list[str] = []

    def clearSelection(self):
        self._gunluk.append("secim=temizle")
        self.secili = []

    def addSelection(self, *a):
        ad = a[-1] if a else "?"
        self._gunluk.append("secim+%s" % getattr(ad, "Name", ad))
        self.secili.append(getattr(ad, "Name", ad))

    def getSelectionEx(self):
        return []


class SahteGui:
    def __init__(self, gorunum) -> None:
        self.ActiveDocument = type("D", (), {"ActiveView": gorunum})()
        self.guncelleme = 0
        self.Selection = SahteSecim(gorunum.gunluk)

    def updateGui(self):
        self.guncelleme += 1

    def SendMsgToActiveView(self, mesaj):
        self._gorunum_mesaji = mesaj
        # Gercekte kamera secime yaklasir; sahte tarafta ayirt edici bir
        # "kamera" degeri koyuyoruz ki karenin YAKIN oldugunu sinayabilelim.
        self.ActiveDocument.ActiveView.kamera = "YAKIN"
        self.ActiveDocument.ActiveView.gunluk.append("msg:%s" % mesaj)

    def getMainWindow(self):
        return None


def _kos(patlat: str = ""):
    """Sahte GUI ile yakala_cok'u calistirir; (gorunum, kareler) doner."""
    for ad in ("caddy.gorunum", "caddy.log", "caddy", "caddy.config"):
        sys.modules.pop(ad, None)
    g = SahteGorunum(patlat)
    eski = sys.modules.get("FreeCADGui")
    sys.modules["FreeCADGui"] = SahteGui(g)
    try:
        from caddy import gorunum as gm
        kareler = gm.yakala_cok(100, 80)
    finally:
        if eski is None:
            sys.modules.pop("FreeCADGui", None)
        else:
            sys.modules["FreeCADGui"] = eski
    return g, kareler


def _kos_yakin(adlar, patlat: str = "", cok_aci: bool = False):
    """Sahte GUI + GERCEK belge ile yakala_yakin. (gorunum, gui, kareler)."""
    import FreeCAD as App

    for ad in ("caddy.gorunum", "caddy.log", "caddy", "caddy.config"):
        sys.modules.pop(ad, None)
    doc = App.ActiveDocument or App.newDocument("YakinTest")
    if doc.getObject("Kutu1") is None:
        doc.addObject("Part::Box", "Kutu1")
        doc.addObject("Part::Box", "Kutu2")
        doc.recompute()
    g = SahteGorunum(patlat)
    gui = SahteGui(g)
    eski = sys.modules.get("FreeCADGui")
    sys.modules["FreeCADGui"] = gui
    try:
        from caddy import gorunum as gm
        kareler = gm.yakala_yakin(adlar, 100, 80, cok_aci=cok_aci)
    finally:
        if eski is None:
            sys.modules.pop("FreeCADGui", None)
        else:
            sys.modules["FreeCADGui"] = eski
    return g, gui, kareler


bolum("kamera kullanicinin acisina GERI DONUYOR")
g, kareler = _kos()
_yaz("       cagri sirasi: %s" % " > ".join(g.gunluk))
kontrol("uc kare yakalandi", len(kareler) == 3, len(kareler))
kontrol("ILK kare kullanicinin acisi",
        kareler and kareler[0].endswith(b"KULLANICININ_ACISI"), kareler[:1])
kontrol("on ve ust de alindi",
        any(k.endswith(b"ON") for k in kareler)
        and any(k.endswith(b"UST") for k in kareler),
        [k[3:] for k in kareler])
kontrol("BITISTE kamera kullanicinin acisinda",
        g.kamera == "KULLANICININ_ACISI", g.kamera)

bolum("animasyon — geri yuklemeyi ezen sebep")
kontrol("aci degistirmeden ONCE animasyon kapatildi",
        "animasyon=kapali" in g.gunluk
        and g.gunluk.index("animasyon=kapali") < g.gunluk.index("viewFront"),
        g.gunluk)
kontrol("setCamera animasyon KAPALIYKEN cagrildi",
        g.gunluk.index("setCamera") > g.gunluk.index("animasyon=kapali")
        and (("animasyon=acik" not in g.gunluk)
             or g.gunluk.index("animasyon=acik")
             > g.gunluk.index("setCamera")),
        g.gunluk)
kontrol("kullanicinin animasyon tercihi geri verildi", g.animasyon is True,
        g.animasyon)

bolum("aci degistirme PATLASA BILE kamera geri gelir")
for _patlat in ("viewFront", "viewTop", "fitAll"):
    g2, _ = _kos(_patlat)
    kontrol("%s patlayinca bile kamera geri geldi" % _patlat,
            g2.kamera == "KULLANICININ_ACISI", g2.kamera)
    kontrol("%s patlayinca animasyon geri acildi" % _patlat,
            g2.animasyon is True, g2.animasyon)

bolum("YAKIN CEKIM — kamera nesneye yaklasiyor, sonra geri geliyor")
# Gerekcesi olculdu (MANTIK 39): tum model kadraja sigdiginda 900x640 kare
# ~4 piksel/mm veriyor; 0.6 mm'lik bir yelken 2 piksel kaliyor ve modelin
# kacirdigi cakisma orada gizleniyordu.
gy, gui, ky = _kos_yakin(["Kutu1"])
_yaz("       cagri sirasi: %s" % " > ".join(gy.gunluk))
kontrol("tek kare dondu", len(ky) == 1, len(ky))
kontrol("nesne SECILDI", "secim+Kutu1" in gy.gunluk, gy.gunluk)
kontrol("FreeCAD'in kendi 'secime yaklas' komutu cagrildi",
        "msg:ViewSelection" in gy.gunluk, gy.gunluk)
kontrol("kare YAKIN kameradan alindi",
        ky and ky[0].endswith(b"YAKIN"), ky[:1])
kontrol("BITISTE kamera kullanicinin acisinda",
        gy.kamera == "KULLANICININ_ACISI", gy.kamera)
kontrol("animasyon aci degistirmeden ONCE kapatildi",
        "animasyon=kapali" in gy.gunluk, gy.gunluk)
kontrol("animasyon tercihi geri verildi", gy.animasyon is True, gy.animasyon)
kontrol("secim kullaniciya geri birakildi (temizlendi)",
        gy.gunluk.count("secim=temizle") >= 2, gy.gunluk)

gy3, _gui3, ky3 = _kos_yakin(["Kutu1", "Kutu2"], cok_aci=True)
kontrol("YAKIN 3 -> uc kare", len(ky3) == 3, len(ky3))
kontrol("iki nesne de secildi",
        "secim+Kutu1" in gy3.gunluk and "secim+Kutu2" in gy3.gunluk,
        gy3.gunluk)
kontrol("uc acida da kamera geri geldi",
        gy3.kamera == "KULLANICININ_ACISI", gy3.kamera)

gy4, _gui4, ky4 = _kos_yakin(["OlmayanNesne"])
kontrol("olmayan ad patlatmiyor, bos donuyor", ky4 == [], ky4)
kontrol("olmayan adda kameraya DOKUNULMADI", gy4.gunluk == [], gy4.gunluk)

# Aci degistirme patlasa bile kamera geri gelmeli — 31.4'teki desen.
gy5, _gui5, _ky5 = _kos_yakin(["Kutu1", "Kutu2"], patlat="viewFront",
                              cok_aci=True)
kontrol("yakin cekimde viewFront patlayinca da kamera geri geldi",
        gy5.kamera == "KULLANICININ_ACISI", gy5.kamera)
kontrol("...ve animasyon geri acildi", gy5.animasyon is True, gy5.animasyon)

_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d" % (gecti, basarisiz))
_yaz("=" * 70)
