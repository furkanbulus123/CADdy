"""report.txt'teki uc ciddi bulgunun duzeltmeleri.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_koruma_fc.py

Aga CIKMAZ. Uc konu:

  1. Otomatik hata onarimi (report madde 1 / PLAN M4)
  2. Kullanicinin KENDI Ctrl+Z'sinde namespace korumasi (report madde 2)
  3. Ilk degisiklikten once saveCopy yedegi (report madde 3, MANTIK 6/2)

Ikincisinin en kritik yani su: koruma bizim KENDI calistirmamizi bozmamali.
Namespace, exec'in globals'i olarak duruyor; ortasinda bosaltmak her adi
birden NameError yapardi. Bu yuzden "kod bir nesne SILERSE ne oluyor"
senaryosu ayrica sinaniyor.

Rapor dosyaya satir satir yaziliyor (MANTIK 14.5).
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

RAPOR = os.path.join(KOK, "tests", "_son_koruma.txt")
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


import FreeCAD as App
from PySide import QtCore

from caddy import config
from caddy.conversation import ConversationController
from caddy import conversation as cv
from caddy.execution.executor import CodeExecutor

_yaz("=" * 70)
_yaz("CADdy koruma testleri")
_yaz("=" * 70)

app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(sys.argv[:1])

# =========================================================== 1) NAMESPACE
bolum("namespace korumasi — KULLANICININ Ctrl+Z'si")

doc = App.newDocument("KorumaTest")
doc.UndoMode = 1
ex = CodeExecutor()
ex.oturumu_ayarla("koruma1")

s = ex.calistir('kutu = doc.addObject("Part::Box", "Kutu")\nkutu.Length = 8\n',
                "kutu")
kontrol("kod calisti", s.basarili, s.hata_izi[-200:])
kontrol("ON KABUL: namespace'te bagli ad var", "kutu" in ex._ns,
        list(ex._ns)[:6])

# Kullanici FreeCAD'in KENDI geri almasini kullaniyor — panel devrede DEGIL.
doc.undo()
doc.recompute()
kontrol("nesne silindi", doc.getObject("Kutu") is None)
kontrol("KULLANICI Ctrl+Z'sinde namespace temizlendi (sert cokme onlendi)",
        ex._ns == {}, list(ex._ns)[:6])

bolum("nesne ELLE silindiginde de temizleniyor")
ex.calistir('k2 = doc.addObject("Part::Box", "Kutu2")\n', "kutu2")
kontrol("ON KABUL: bagli ad var", "k2" in ex._ns, list(ex._ns)[:6])
doc.removeObject("Kutu2")
doc.recompute()
kontrol("silme namespace'i temizledi", ex._ns == {}, list(ex._ns)[:6])

bolum("KENDI calistirmamizi BOZMUYOR — asil tuzak")
# Kod kendi icinde bir nesne siliyor. Koruma o anda namespace'i bosaltirsa
# exec'in globals'i gider ve sonraki satirlar NameError verir.
ex.calistir('a = doc.addObject("Part::Box", "Silinecek")\n', "hazirlik")
s2 = ex.calistir(
    'x = 5\n'
    'doc.removeObject("Silinecek")\n'
    'y = x + 1\n'                       # x hala gorunmeli
    'z = doc.addObject("Part::Box", "SilmeSonrasi")\n',
    "silme sonrasi devam")
kontrol("silme yapan kod PATLAMADI", s2.basarili, s2.hata_izi[-300:])
kontrol("silmeden sonraki nesne olustu",
        doc.getObject("SilmeSonrasi") is not None,
        [o.Name for o in doc.Objects])
kontrol("calistirma BITINCE namespace temizlendi", ex._ns == {},
        list(ex._ns)[:6])

bolum("silme YOKSA namespace korunuyor (kurt masali degil)")
ex.calistir('kalici = doc.addObject("Part::Box", "Kalici")\n', "kalici")
kontrol("bagli ad duruyor", "kalici" in ex._ns, list(ex._ns)[:6])
ex.calistir('kalici2 = 42\n', "silme yok")
kontrol("ikinci turda da duruyor",
        "kalici" in ex._ns and "kalici2" in ex._ns, list(ex._ns)[:6])

bolum("gozlemci sizmiyor")
kontrol("gozlemci acik", ex._koruma._acik is True)
ex.kapat()
kontrol("kapat() gozlemciyi cozdu", ex._koruma._acik is False)
ex.kapat()
kontrol("iki kez kapatmak patlatmiyor", ex._koruma._acik is False)

# ============================================================== 2) YEDEK
bolum("yedek — ilk degisiklikten once, belge basina BIR kez")

yedek_dizin = config.yedek_dizini()
oncekiler = set(os.listdir(yedek_dizin))

doc2 = App.newDocument("YedekTest")
doc2.UndoMode = 1
ex2 = CodeExecutor()
ex2.oturumu_ayarla("yedek1")

s3 = ex2.calistir('doc.addObject("Part::Box", "Ilk")\n', "ilk")
kontrol("kod calisti", s3.basarili, s3.hata_izi[-200:])
_yaz("       yedek: %s" % s3.yedek)
kontrol("ILK calistirmada yedek alindi", bool(s3.yedek), s3.yedek)
kontrol("yedek dosyasi gercekten var",
        bool(s3.yedek) and os.path.exists(s3.yedek), s3.yedek)
kontrol("yedek .FCStd", s3.yedek.endswith(".FCStd"), s3.yedek)

s4 = ex2.calistir('doc.addObject("Part::Box", "Ikinci")\n', "ikinci")
kontrol("IKINCI calistirmada yedek YOK (belge basina bir kez)",
        s4.yedek == "", s4.yedek)

yeniler = set(os.listdir(yedek_dizin)) - oncekiler
_yaz("       yeni yedek dosyasi: %s" % sorted(yeniler))
kontrol("tam 1 yeni dosya olustu", len(yeniler) == 1, sorted(yeniler))

bolum("yedek alinamasa bile IS DEVAM EDER")
ex3 = CodeExecutor()


def _patlat(_doc):
    raise RuntimeError("yedek alinamadi (test)")


ex3._yedek_al = _patlat
try:
    s5 = ex3.calistir('doc.addObject("Part::Box", "YedeksizAma")\n', "yedeksiz")
    kontrol("yedek patlarsa calistirma yine de olur", s5.basarili,
            s5.hata_izi[-200:])
except Exception as e:                                       # noqa: BLE001
    kontrol("yedek patlarsa calistirma yine de olur", False, repr(e))

# ================================================== 3) OTOMATIK ONARIM
bolum("otomatik hata onarimi")

App.setActiveDocument(doc.Name)
ctl = ConversationController()
mesajlar = []
gonderilen = []
ctl.mesaj.connect(lambda r, m: mesajlar.append((r, m)))
ctl.transport.tur_gonder = lambda *a, **k: gonderilen.append(a[0] if a else "")


class _Blok:
    baslik = "patlayan"
    kod = 'raise RuntimeError("birinci hata")\n'


kontrol("sinir 2", cv._ONARIM_SINIRI == 2, cv._ONARIM_SINIRI)

ctl._onarim_tur = 0
ctl._son_hata = ""
mesajlar.clear()
gonderilen.clear()
ctl.blogu_calistir(_Blok())
kontrol("hata OTOMATIK gonderildi (dugmeye basilmadan)",
        len(gonderilen) == 1, len(gonderilen))
if gonderilen:
    kontrol("gonderilen metin hata izi tasiyor",
            "execution_error" in gonderilen[0], gonderilen[0][:150])
kontrol("kullaniciya sayacla bildirildi",
        any("1/2" in m for _, m in mesajlar), mesajlar)


class _Blok2:
    baslik = "patlayan2"
    kod = 'raise ValueError("ikinci hata")\n'


mesajlar.clear()
gonderilen.clear()
ctl.blogu_calistir(_Blok2())
kontrol("ikinci FARKLI hata da gonderildi", len(gonderilen) == 1,
        len(gonderilen))
kontrol("sayac 2/2", any("2/2" in m for _, m in mesajlar), mesajlar)


class _Blok3:
    baslik = "patlayan3"
    kod = 'raise KeyError("ucuncu")\n'


mesajlar.clear()
gonderilen.clear()
ctl.blogu_calistir(_Blok3())
kontrol("BUTCE dolunca gonderilmiyor", gonderilen == [], gonderilen)
kontrol("durduruldugu SOYLENIYOR",
        any("durduruldu" in m for _, m in mesajlar), mesajlar)

bolum("AYNI hata tekrarlarsa butceyi beklemeden durur")
ctl._onarim_tur = 0
ctl._son_hata = ""
mesajlar.clear()
gonderilen.clear()
ctl.blogu_calistir(_Blok())          # birinci hata
kontrol("ilk gonderildi", len(gonderilen) == 1, len(gonderilen))
mesajlar.clear()
gonderilen.clear()
ctl.blogu_calistir(_Blok())          # AYNI hata
kontrol("ayni hata TEKRAR gonderilmedi (butce dolmadan)",
        gonderilen == [], gonderilen)
kontrol("sebep soyleniyor",
        any("Aynı hata" in m for _, m in mesajlar), mesajlar)
kontrol("butce hala dolmamisti", ctl._onarim_tur < cv._ONARIM_SINIRI,
        ctl._onarim_tur)

bolum("gercek kullanici mesaji sayaci sifirliyor")
ctl._onarim_tur = 2
ctl._son_hata = "bir sey"
gonderilen.clear()
ctl.gonder("yeni istek", kullanici_mi=True)
kontrol("onarim sayaci sifirlandi", ctl._onarim_tur == 0, ctl._onarim_tur)
kontrol("hata imzasi sifirlandi", ctl._son_hata == "", ctl._son_hata)

bolum("BASARILI kodda onarim tetiklenmiyor")


class _Iyi:
    baslik = "iyi"
    kod = 'doc.addObject("Part::Box", "IyiKutu")\n'


ctl._onarim_tur = 0
gonderilen.clear()
ctl.blogu_calistir(_Iyi())
kontrol("basarili kodda hicbir sey gonderilmedi", gonderilen == [], gonderilen)

# ============================================================ 4) OLU KOD
bolum("olu kod silindi")
kontrol("config.otomatik_calistir YOK",
        not hasattr(config, "otomatik_calistir"))
kontrol("AutoRun varsayilanlarda YOK", "AutoRun" not in config.VARSAYILAN,
        list(config.VARSAYILAN))

from caddy.transport.process import ClaudeProcess

kontrol("ClaudeProcess.girdiyi_kapat YOK",
        not hasattr(ClaudeProcess, "girdiyi_kapat"))
kontrol("ClaudeProcess.stderr_metin sinyali YOK",
        not hasattr(ClaudeProcess, "stderr_metin"))

from caddy import gorunum

import inspect

_kaynak = inspect.getsource(gorunum._widget_ile_yakala)
kontrol("gorunum iskele artigi silindi",
        "del alt, widget" not in _kaynak and "getSceneGraph" not in _kaynak,
        [x.strip() for x in _kaynak.splitlines() if "del " in x])

# =========================================================== 5) GUNLUK
bolum("gunluk artik dogrulamayi da kaydediyor")
from caddy.sohbet_log import SohbetGunlugu

kontrol("otomatik() basligi var", hasattr(SohbetGunlugu, "otomatik"))

import tempfile
from pathlib import Path

gecici = Path(tempfile.mkdtemp())
g = SohbetGunlugu(kok=gecici)
g.oturum_ac("test1234")
s6 = ex.calistir('doc.addObject("Part::Box", "GunlukKutu")\n', "gunluk")
g.calisma(s6)
g.otomatik("otomatik tur metni")
icerik = g.dosya.read_text(encoding="utf-8")
kontrol("dogrulama raporu gunlukte", "dogrulama:" in icerik,
        icerik[-300:])
kontrol("dokunulan gunlukte", "dokunulan:" in icerik, icerik[-300:])
kontrol("OTOMATIK basligi gunlukte", "--- OTOMATIK" in icerik, icerik[-300:])

# --- KONUSULMAYAN OTURUM DOSYA BIRAKMAZ ---------------------------------
# Kullanicinin sikayeti: "cok fazla log var, gereksiz bos loglar olusuyor".
# OLCULDU (2026-08-26): LOG/ altinda 106 dosyanin 43'u tam 298 bayt, yani
# yalnizca baslik. Sebep: oturum_ac diske hemen yaziyordu. Artik baslik
# ILK GERCEK KAYDA kadar bekliyor.
bolum("bos oturum dosya birakmiyor (tembel baslik)")
bos_kok = Path(tempfile.mkdtemp())
g2 = SohbetGunlugu(kok=bos_kok)
g2.oturum_ac("bosoturum", model="opus")
kontrol("oturum acmak DISKE DOKUNMUYOR",
        not any(bos_kok.iterdir()), list(bos_kok.iterdir()))
kontrol("yol yine de biliniyor", g2.dosya is not None, g2.dosya)

g2.kullanici("ilk gercek mesaj")
kontrol("ilk kayitla dosya DOGDU", g2.dosya.exists(), g2.dosya)
_ic2 = g2.dosya.read_text(encoding="utf-8")
kontrol("baslik kaybolmadi, en tepede", _ic2.startswith("=" * 72), _ic2[:40])
kontrol("oturum kimligi baslikta", "oturum : bosoturum" in _ic2, _ic2[:200])
kontrol("baslik BIR KEZ yazildi", _ic2.count("CADdy sohbet gunlugu") == 1,
        _ic2.count("CADdy sohbet gunlugu"))
kontrol("mesaj da yazildi", "ilk gercek mesaj" in _ic2, _ic2[-200:])

# Model, baslik daha diskte yokken de basliga islemeli — eskiden bu yol
# dosyayi okuyup degistiriyordu, dosya yoksa sessizce kaybolurdu.
g3 = SohbetGunlugu(kok=Path(tempfile.mkdtemp()))
g3.oturum_ac("modelsiz")
g3.ai("cevap", model="claude-opus-5")
_ic3 = g3.dosya.read_text(encoding="utf-8")
kontrol("model basliga yazildi (dosya sonradan dogsa da)",
        "model  : claude-opus-5" in _ic3, _ic3[:200])
kontrol("'(bilinmiyor)' kalmadi", "(bilinmiyor)" not in _ic3, _ic3[:200])

# Ortam degiskeni: testler gercek LOG/'a yazmasin diye eklendi.
kontrol("CADDY_LOG_DIR kok dizini belirliyor",
        SohbetGunlugu()._kok == Path(os.environ["CADDY_LOG_DIR"]),
        SohbetGunlugu()._kok)

# ================================================ KESIF ONCELIGI (MANTIK 39)
bolum("kesif butcesi ISKELEYE degil ISE harcaniyor")
# OLCULDU (LOG/2026-08-26_34ac9988.txt): 52 nesnelik belgede yalnizca 8'i
# olculdu ve o 8 slotun 3'u hacimsiz ESKIZLERE gitti (`doc.Objects` sirasi),
# ustelik sure butcesinin 3.0 sn'sinden yalnizca 0.48 sn kullanilmisti.
import time

from caddy.execution import kesif as _kesif

_kd = App.newDocument("KesifOncelik")
for _i in range(12):
    _kd.addObject("Sketcher::SketchObject", "Eskiz%d" % _i)   # ONCE eskizler
for _i in range(12):
    _k = _kd.addObject("Part::Box", "Parca%d" % _i)
    _k.Placement.Base.x = _i * 30
_kd.recompute()

_sirali = _kesif.ilgili_nesneler(_kd)
_ilk8 = [o.Name for o in _sirali[:8]]
_yaz("       ilk 8: %s" % _ilk8)
kontrol("ON KABUL: belge sirasinda eskizler ONDE",
        _kd.Objects[0].Name.startswith("Eskiz"), _kd.Objects[0].Name)
kontrol("ilk 8'de HIC eskiz yok",
        not any(a.startswith("Eskiz") for a in _ilk8), _ilk8)
kontrol("eskizler sona atildi",
        _sirali[-1].Name.startswith("Eskiz"), _sirali[-1].Name)
kontrol("ayni siniftaki nesneler belge sirasini koruyor (kararli siralama)",
        _ilk8 == ["Parca%d" % i for i in range(8)], _ilk8)
kontrol("nesne siniri sureye birakildi (8 -> 24)",
        _kesif.AZAMI_NESNE == 24, _kesif.AZAMI_NESNE)

_t0 = time.time()
_metin = _kesif.kesif_metni(_kd)
_sure = time.time() - _t0
_yaz("       kesif: %.2f sn, sure butcesi %.1f sn"
     % (_sure, _kesif.SURE_BUTCESI))
kontrol("kesif sure butcesini asmiyor", _sure <= _kesif.SURE_BUTCESI + 0.5,
        _sure)
kontrol("24 nesneye kadar olcebiliyor",
        _metin.count("hacim=") >= 12, _metin.count("hacim="))
App.closeDocument(_kd.Name)

_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d" % (gecti, basarisiz))
_yaz("=" * 70)
