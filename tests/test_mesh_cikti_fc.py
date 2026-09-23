"""Mesh dogrulamasi, print geri kanali ve tekrar korumasi.

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_mesh_cikti_fc.py

Uc iddiayi siniyor — ucu de 2026-08-21 gunluk incelemesinden geliyor:

  * MESH GORUNMEZDI. dogrulama._bir_nesne `Shape is None` diye donuyordu;
    Mesh::Feature'in Shape'i yok. Son dort gercek oturumun ana nesnesi
    mesh'ti ve o oturumlarda tek bir kontrol kosmadi.
  * CIKTI KAYBOLUYORDU. print() iceren 8 blogun 8'inin de ciktisi modele
    ulasmamisti; CalismaSonucu.cikti doluyor ama gonderilmiyordu.
  * AYNI KOD IKI KEZ KOSUYORDU. 8 kez olculdu, ikisi onay penceresi
    VARKEN oldu — koruma kartta degil, calisticida olmali.

Rapor dosyaya SATIR SATIR yaziliyor (MANTIK 14.5).
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

RAPOR = os.path.join(KOK, "tests", "_son_mesh_cikti.txt")
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


import time

import FreeCAD as App
import Mesh
import Part

from caddy.context import serializer
from caddy.execution import dogrulama as dg
from caddy.execution import executor as ex
from caddy.execution.executor import CodeExecutor

_yaz("=" * 70)
_yaz("CADdy mesh dogrulamasi + cikti kanali + tekrar korumasi")
_yaz("=" * 70)

doc = App.newDocument("MeshCiktiTest")
doc.UndoMode = 1


def _mesh_koy(ad, m):
    o = doc.addObject("Mesh::Feature", ad)
    o.Mesh = m
    doc.recompute()
    return o


# ===================================================== 1. SAGLAM MESH
bolum("saglam kapali mesh — bulgu OLMAMALI")

kutu = Mesh.createBox(20, 20, 10)
iyi = _mesh_koy("Iyi", kutu)

kontrol("mesh_al mesh'i buluyor", dg._mesh_al(iyi) is not None)
kontrol("mesh_al kati nesnede None dondurur",
        dg._mesh_al(doc.addObject("Part::Feature", "Bos")) is None)

r = dg.dogrula(doc, ["Iyi"])
_yaz("       " + r.metin().replace("\n", "\n       "))
kontrol("bulgu yok", r.temiz, [str(b) for b in r.bulgular])
kontrol("bakilan 1", r.bakilan == 1, r.bakilan)
kontrol("facet olcumu yazildi", any("facet=" in o for o in r.olcumler),
        r.olcumler)
kontrol("bbox olcumu yazildi", any("bbox=" in o for o in r.olcumler),
        r.olcumler)
kontrol("baskiya hazir EVET", any("print-ready = YES" in o
                                  for o in r.olcumler), r.olcumler)
kontrol("mesh kontrolu KOSAN listesinde",
        any("mesh" in k for k in r.kosan), r.kosan)
kontrol("kendiyle kesisme artik KATI icin atlaniyor (mesh'te kosuyor)",
        any("SOLID" in a for a in r.atlanan), r.atlanan)

hazir, engeller, olcumler = dg.baskiya_hazir_mesh(iyi.Mesh)
kontrol("baskiya_hazir_mesh: hazir", hazir, engeller)
kontrol("baskiya_hazir_mesh: engel yok", not engeller, engeller)
kontrol("hacim olculdu", any("volume=" in o for o in olcumler), olcumler)


# ===================================================== 2. ACIK MESH
bolum("delikli mesh — 'kapali degil' YAKALANMALI")

delikli = Mesh.Mesh(kutu)
delikli.removeFacets([0, 1])
acik = _mesh_koy("Acik", delikli)

kontrol("isSolid False", not delikli.isSolid())
r = dg.dogrula(doc, ["Acik"])
_yaz("       " + r.metin().replace("\n", "\n       "))
kontrol("bulgu uretildi", not r.temiz, r.metin())
kontrol("bulgu 'kapali degil'",
        any(b.tur == "not closed" for b in r.bulgular),
        [str(b) for b in r.bulgular])
kontrol("baskiya hazir HAYIR",
        any("print-ready = NO" in o for o in r.olcumler), r.olcumler)


# ===================================================== 3. KESISEN MESH
bolum("kendiyle kesisen mesh — isSolid() YALAN SOYLUYOR")

k1 = Mesh.createBox(10, 10, 10)
k2 = Mesh.createBox(10, 10, 10)
k2.translate(5, 5, 5)
kesisen_mesh = Mesh.Mesh(k1)
kesisen_mesh.addMesh(k2)
kesisen = _mesh_koy("Kesisen", kesisen_mesh)

# Asil iddia: kapali gorunuyor ama basilamaz.
kontrol("isSolid() True diyor (yalan)", kesisen_mesh.isSolid(),
        kesisen_mesh.isSolid())
kontrol("hasSelfIntersections True", kesisen_mesh.hasSelfIntersections())

r = dg.dogrula(doc, ["Kesisen"])
_yaz("       " + r.metin().replace("\n", "\n       "))
kontrol("kesisme bulgusu var",
        any(b.tur == "self-intersection" for b in r.bulgular),
        [str(b) for b in r.bulgular])
kontrol("cok parca bulgusu var",
        any(b.tur == "multiple components" for b in r.bulgular),
        [str(b) for b in r.bulgular])
kontrol("isSolid True olmasina RAGMEN hazir degil",
        any("print-ready = NO" in o for o in r.olcumler), r.olcumler)


# ===================================================== 4. MALIYET
bolum("mesh kontrollerinin maliyeti — sure butcesinin altinda")

t0 = time.time()
dg.baskiya_hazir_mesh(iyi.Mesh)
sure = time.time() - t0
kontrol("tek mesh kontrolu < 0.5 sn", sure < 0.5, "%.3f sn" % sure)

r = dg.dogrula(doc, ["Iyi", "Acik", "Kesisen"])
kontrol("uc mesh birlikte sure butcesini asmadi",
        r.sure_sn < dg.SURE_BUTCESI, "%.3f sn" % r.sure_sn)
kontrol("uc nesneye de bakildi", r.bakilan == 3, r.bakilan)


# ===================================================== 5. BAGLAM
bolum("baglam metni mesh'i gosteriyor mu")

metin = serializer.belge_metni(doc, butce=8000)
_yaz("       " + metin.replace("\n", "\n       ")[:900])
kontrol("mesh nesnesi bbox aliyor (Shape yokken Mesh.BoundBox)",
        "20x20x10 mm" in metin, metin[:400])
kontrol("facet sayisi baglamda", "facet=" in metin, metin[:400])
kontrol("acik mesh 'ACIK(delik var)' diye isaretli",
        "OPEN(has holes)" in metin, metin[:600])
kontrol("kapali mesh 'kapali' diye isaretli", "closed" in metin, metin[:600])
kontrol("cok parcali mesh parca sayisi ile geliyor",
        "components=2" in metin, metin[:800])


# ===================================================== 6. CIKTI KANALI
bolum("print ciktisi sonuca ve modele giden metne giriyor mu")

yurutucu = CodeExecutor()
s = yurutucu.calistir("print('olculen deger:', 42)", "olcum")
kontrol("kod basarili", s.basarili, s.hata_izi)
kontrol("cikti yakalandi", "olculen deger: 42" in s.cikti, repr(s.cikti))
kontrol("cikti MODELE giden metinde var",
        "olculen deger: 42" in s.modele_metin(), s.modele_metin()[:300])
kontrol("cikti hata olarak isaretlenmedi", s.basarili and not s.engellendi)

# baski_kontrol namespace'te mi ve calisiyor mu
s = yurutucu.calistir(
    "n = doc.getObject('Iyi')\nprint('donen:', baski_kontrol(n))",
    "baski kontrol saglam")
kontrol("baski_kontrol namespace'te", s.basarili, s.hata_izi)
kontrol("baski_kontrol EVET dedi", "print-ready = YES" in s.cikti, s.cikti)
kontrol("baski_kontrol True dondu", "donen: True" in s.cikti, s.cikti)

s = yurutucu.calistir(
    "n = doc.getObject('Acik')\nprint('donen:', baski_kontrol(n))",
    "baski kontrol delikli")
kontrol("delikli meshte HAYIR", "print-ready = NO" in s.cikti, s.cikti)
kontrol("sebep de yazildi", "not closed" in s.cikti, s.cikti)
kontrol("baski_kontrol False dondu", "donen: False" in s.cikti, s.cikti)

s = yurutucu.calistir("print(baski_kontrol())", "tum mesh'ler")
kontrol("argumansiz baski_kontrol tum mesh'lere bakti",
        s.cikti.count("print-ready") >= 3, s.cikti)


# ===================================================== 6b. OLCUM
bolum("olcum yardimcilari — gunlukteki 'agiz capi' senaryosu")

# LOG 2026-08-20 baa70fa4: kullanici "agiz capi ne kadar bu kupanin" dedi.
# Model dogru hesapladi ama sayiyi geri getirmek icin belgeye cember ekleyip
# BIR SONRAKI turda okudu. Ayni olcum simdi tek cagri olmali.
import MeshPart as _MP

# Z ekseninde duran silindir: r=27.7335 -> cap 55.467 (gunlukteki olcunun ayni)
silindir = _MP.meshFromShape(Shape=Part.makeCylinder(27.7335, 60),
                             LinearDeflection=0.05, AngularDeflection=0.1)
kupa = _mesh_koy("Kupa", silindir)

s = yurutucu.calistir(
    "d = kesit_capi(doc.getObject('Kupa'))\nprint('cap:', round(d['ort_cap'], 2))",
    "agiz capi")
_yaz("       " + s.cikti.replace("\n", "\n       "))
kontrol("kesit_capi kostu", s.basarili, s.hata_izi)
kontrol("dairesel oldugunu anladi", "circular" in s.cikti, s.cikti)
kontrol("cap dogru olculdu (~55.47)",
        "diameter=55.4" in s.cikti or "diameter=55.5" in s.cikti, s.cikti)
kontrol("TEK turda geri geldi (cikti modele giden metinde)",
        "cap:" in s.modele_metin(), s.modele_metin()[:200])

# Oval: tek bir "cap" yok — kisa ve uzun ayri ayri gelmeli
oval_mesh = Mesh.Mesh(silindir)
mat = App.Matrix()
mat.scale(60.0 / 55.467, 50.0 / 55.467, 1.0)
oval_mesh.transform(mat)
_mesh_koy("Oval", oval_mesh)

s = yurutucu.calistir("kesit_capi(doc.getObject('Oval'))", "oval kesit")
_yaz("       " + s.cikti.strip())
kontrol("oval 'dairesel' DEMEDI", "circular" not in s.cikti, s.cikti)
kontrol("kisa cap ~50", "minor dia=50" in s.cikti or "minor dia=49.9" in s.cikti,
        s.cikti)
kontrol("uzun cap ~60", "major dia=60" in s.cikti or "major dia=59.9" in s.cikti,
        s.cikti)

# Belirli yukseklikte kesit
s = yurutucu.calistir("kesit_capi(doc.getObject('Kupa'), z=30)", "z=30 kesiti")
kontrol("verilen z'de olcum yapildi", "z=30" in s.cikti, s.cikti)

# olc: tek cagrida temel olculer
s = yurutucu.calistir("olc(doc.getObject('Iyi'))", "olc")
_yaz("       " + s.cikti.strip())
kontrol("olc boy yazdi", "size=20x20x10" in s.cikti, s.cikti)
kontrol("olc hacim yazdi", "volume=" in s.cikti, s.cikti)
kontrol("olc kapali/acik durumunu yazdi", "closed" in s.cikti, s.cikti)

s = yurutucu.calistir("olc(doc.getObject('TekrarKutuYok'))", "olc bos")
kontrol("olmayan nesnede olc patlamiyor", s.basarili, s.hata_izi)
kontrol("olc bulunamadi dedi", "no object" in s.cikti, s.cikti)

# Kati (BRep) nesnede de calismali
_kati = doc.addObject("Part::Box", "Kutu")
_kati.Length = 30
doc.recompute()
s = yurutucu.calistir("olc(doc.getObject('Kutu'))", "olc kati")
_yaz("       " + s.cikti.strip())
kontrol("kati nesnede de olcuyor", "volume=" in s.cikti and "faces=6" in s.cikti,
        s.cikti)

# Yetersiz nokta: sessizce yanlis sayi UYDURMAMALI
s = yurutucu.calistir(
    "kesit_capi(doc.getObject('Kupa'), z=1000, band=0.01)", "bos kesit")
kontrol("bos kesitte uyarip duruyor", "no section found" in s.cikti, s.cikti)

# YATIK NESNE: kesit bir halka degil. Testin ilk kosusunda buradan
# "kisa cap=7.25e-11" gibi inandirici ama YANLIS bir sayi geliyordu.
yatik = Mesh.createCylinder(20, 60, 1, 0.5, 48)      # ekseni X'te
_mesh_koy("Yatik", yatik)
s = yurutucu.calistir("d = kesit_capi(doc.getObject('Yatik'))\n"
                      "print('guvenilir:', d.get('guvenilir'))", "yatik kesit")
_yaz("       " + s.cikti.strip())
kontrol("yatik nesnede 'YUVARLAK DEGIL' dedi", "NOT ROUND" in s.cikti,
        s.cikti)
kontrol("guvenilir=False isaretledi", "guvenilir: False" in s.cikti, s.cikti)
kontrol("'cap' diye bir sayi UYDURMADI", "minor dia=" not in s.cikti, s.cikti)


# ===================================================== 6c. KESIF
bolum("kesif() — mevcut isin uzerine calisirken ilk adim")

# Ici bos, hafif konik bir kupa: gercek bir mevcut-is senaryosu.
_govde = Part.makeCone(22.5, 27.7, 95).cut(
    Part.makeCone(20.5, 25.7, 92, App.Vector(0, 0, 3)))
_kupa_mesh = _MP.meshFromShape(Shape=_govde, LinearDeflection=0.1,
                               AngularDeflection=0.3)
_mesh_koy("Bardak", _kupa_mesh)

# Delikli plaka: silindirik yuz dokumu
_plaka = Part.makeBox(40, 40, 5)
for _x in (10, 30):
    _plaka = _plaka.cut(Part.makeCylinder(1.7, 10, App.Vector(_x, 10, -1)))
_p = doc.addObject("Part::Feature", "Plaka")
_p.Shape = _plaka
doc.recompute()

s = yurutucu.calistir("kesif(doc.getObject('Bardak'))", "bardak kesfi")
_yaz("       " + s.cikti.replace("\n", "\n       "))
kontrol("kesif kostu", s.basarili, s.hata_izi)
kontrol("taban kesiti var", "bottom:" in s.cikti, s.cikti)
kontrol("orta kesiti var (uzun ucgenlere ragmen)", "middle:" in s.cikti, s.cikti)
kontrol("agiz kesiti var", "rim/top:" in s.cikti, s.cikti)
kontrol("DUVAR kalinligi olculdu", "wall=" in s.cikti, s.cikti)
kontrol("duvar ~2 mm", "wall=2." in s.cikti, s.cikti)
kontrol("konikligi gorebilecek veri var (taban != agiz)",
        s.cikti.count("outer dia=") >= 3, s.cikti)
kontrol("baskiya hazir bilgisi var", "print-ready" in s.cikti, s.cikti)

s = yurutucu.calistir("kesif(doc.getObject('Plaka'))", "plaka kesfi")
_yaz("       " + s.cikti.replace("\n", "\n       "))
kontrol("delik dokumu cikti", "cylindrical faces" in s.cikti, s.cikti)
kontrol("M3 gecme deligi Ø3.4 olarak goruldu", "Ø3.4x2" in s.cikti, s.cikti)

s = yurutucu.calistir("kesif()", "tum belge kesfi")
kontrol("argumansiz kesif tum belgeyi olctu", "SURVEY —" in s.cikti, s.cikti[:200])
kontrol("nesne sayisi yazildi", "objects measured" in s.cikti, s.cikti[:200])
kontrol("olcum suresi yazildi", "measurement time" in s.cikti, s.cikti[-200:])
kontrol("kesif sure butcesi icinde", s.sure_sn < 3.0, s.sure_sn)

# Iskele nesneleri (Origin, duzlemler) kesfe girmemeli
_body = doc.addObject("PartDesign::Body", "Govde")
doc.recompute()
s = yurutucu.calistir("kesif()", "iskele haric")
kontrol("Origin/duzlemler kesfe girmiyor",
        "XY_Plane" not in s.cikti and "Origin" not in s.cikti, s.cikti[:400])

# Bos belgede dogru sey soylenmeli
s = yurutucu.calistir(
    "from caddy.execution import kesif as _k\n"
    "import FreeCAD\n"
    "b = FreeCAD.newDocument('BosBelge')\n"
    "print(_k.kesif_metni(b) or 'BOS')\n"
    "FreeCAD.closeDocument('BosBelge')", "bos belge kesfi")
kontrol("bos belgede kesif bos donuyor", "BOS" in s.cikti, s.cikti)
# newDocument aktif belgeyi DEGISTIRIR ve kapatinca eskisi geri gelmez;
# geri kurulmazsa sonraki her calistirma "acik belge yok" der.
App.setActiveDocument(doc.Name)


# ===================================================== 6bb. HAZIR KOD
bolum("hazir olcum altyapisi — elle geometri yerine var olan kod")

s = yurutucu.calistir(
    "import numpy, scipy\n"
    "from scipy.spatial import cKDTree\n"
    "import Measure\n"
    "print('numpy', numpy.__version__, 'scipy', scipy.__version__)", "kutuphane")
kontrol("numpy + scipy + Measure FreeCAD icinde var", s.basarili, s.hata_izi)
kontrol("surumler okundu", "numpy 1." in s.cikti, s.cikti)

# YATIK nesne: eksene hizali bbox YALAN soyler, kendi ekseni dogruyu.
_yatik_kati = Part.makeBox(30, 10, 5)
_yatik_kati.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 30)
_yk = doc.addObject("Part::Feature", "YatikKutu")
_yk.Shape = _yatik_kati
_duz = doc.addObject("Part::Feature", "DuzKutu")
_duz.Shape = Part.makeBox(30, 10, 5)
doc.recompute()

s = yurutucu.calistir("olc(doc.getObject('YatikKutu'))", "yatik olcu")
_yaz("       " + s.cikti.strip())
kontrol("yatik nesne YATIK diye isaretlendi", "TILTED" in s.cikti, s.cikti)
kontrol("kendi ekseninde GERCEK olcu verildi (30x10x5)",
        "30x10x5" in s.cikti, s.cikti)
kontrol("eksene hizali bbox da duruyor (19.33)", "19.33" in s.cikti, s.cikti)

s = yurutucu.calistir("olc(doc.getObject('DuzKutu'))", "duz olcu")
kontrol("duz nesnede YATIK uyarisi YOK", "TILTED" not in s.cikti, s.cikti)

# MESAFE — "degiyorlar mi" sorusu
_ka = doc.addObject("Mesh::Feature", "KureA")
_ka.Mesh = Mesh.createSphere(10, 40)
_kb_mesh = Mesh.createSphere(10, 40)
_kb_mesh.translate(24, 0, 0)
_kb = doc.addObject("Mesh::Feature", "KureB")
_kb.Mesh = _kb_mesh
doc.recompute()

s = yurutucu.calistir(
    "d = mesafe(doc.getObject('KureA'), doc.getObject('KureB'))\n"
    "print('deger:', round(d['mesafe'], 3))", "mesh mesafe")
_yaz("       " + s.cikti.strip())
kontrol("mesh-mesh mesafe olculdu", s.basarili, s.hata_izi)
kontrol("mesafe dogru (~4 mm)", "deger: 4.0" in s.cikti or "deger: 3.9" in s.cikti,
        s.cikti)
kontrol("mesh yonteminin sinirini SOYLUYOR", "mesh points" in s.cikti, s.cikti)
kontrol("cKDTree ile hizli", s.sure_sn < 2.0, s.sure_sn)

s = yurutucu.calistir(
    "mesafe(doc.getObject('DuzKutu'), doc.getObject('YatikKutu'))", "kati mesafe")
_yaz("       " + s.cikti.strip())
kontrol("kati-kati distToShape kullanildi", "closest points" in s.cikti,
        s.cikti)
kontrol("degdiklerini soyledi", "they touch" in s.cikti, s.cikti)

# OLCU — FreeCAD'in KENDI olcum motoru (Measure.Measurement)
s = yurutucu.calistir("olcu(doc.getObject('Plaka2'), 'Face7')", "delik capi")
kontrol("olmayan nesnede patlamiyor", s.basarili, s.hata_izi)

_pl = doc.addObject("Part::Feature", "Delikli")
_pl.Shape = Part.makeBox(40, 40, 5).cut(
    Part.makeCylinder(1.7, 10, App.Vector(10, 10, -1)))
doc.recompute()
s = yurutucu.calistir("olcu(doc.getObject('Delikli'), 'Face7')", "delik capi")
_yaz("       " + s.cikti.strip())
kontrol("Measure.Measurement yaricapi verdi", "radius=1.7" in s.cikti, s.cikti)
kontrol("cap da yazildi", "diameter=3.4" in s.cikti, s.cikti)

# DUVAR KALINLIGI — isin atma
s = yurutucu.calistir(
    "d = duvar_kalinligi(doc.getObject('Bardak'))\n"
    "print('en ince:', round(d['en_ince'], 2))", "duvar")
_yaz("       " + s.cikti.strip())
kontrol("duvar kalinligi olculdu", s.basarili, s.hata_izi)
kontrol("~2 mm buldu (gercek duvar 2.0)",
        "en ince: 1.9" in s.cikti or "en ince: 2.0" in s.cikti, s.cikti)
kontrol("kac olcum yaptigini soyluyor", "measurements" in s.cikti, s.cikti)

s = yurutucu.calistir("duvar_kalinligi(doc.getObject('KureA'))", "dolu govde")
kontrol("dolu govdede yanlis sayi UYDURMUYOR",
        "no wall found" in s.cikti, s.cikti)


# ===================================================== 7. TEKRAR KORUMASI
bolum("ayni kod ikinci kez — BIR KEZ engellenmeli")

kod = "kutu = doc.addObject('Part::Box', 'TekrarKutu')\nkutu.Length = 5"
onceki_sayi = len(doc.Objects)

a = yurutucu.calistir(kod, "tekrar denemesi")
kontrol("1. kosu calisti", a.basarili and not a.engellendi, a.ozet)

b = yurutucu.calistir(kod, "tekrar denemesi")
kontrol("2. kosu ENGELLENDI", b.engellendi, b.ozet)
kontrol("engellenen kosu basarili degil", not b.basarili)
kontrol("engellenen kosu nesne EKLEMEDI",
        len(doc.Objects) == onceki_sayi + 1, len(doc.Objects))
kontrol("ozet 'BLOCKED' diyor", "BLOCKED" in b.ozet, b.ozet)
kontrol("sebep aciklamasi kullaniciya donuk",
        "press Run once" in b.hata_izi, b.hata_izi[:200])

c = yurutucu.calistir(kod, "tekrar denemesi")
kontrol("3. kosu (kullanici israr etti) CALISTI",
        c.basarili and not c.engellendi, c.ozet)
kontrol("simdi ikinci kopya olustu", len(doc.Objects) == onceki_sayi + 2,
        len(doc.Objects))

d = yurutucu.calistir(kod, "tekrar denemesi")
kontrol("4. kosu yine engellendi (onay bir seferlik)", d.engellendi, d.ozet)

# Farkli kod engellenmemeli
e = yurutucu.calistir("x = 1", "baska kod")
kontrol("farkli kod engellenmiyor", not e.engellendi, e.ozet)

# Patlayan kod tekrar korumasina sayilmamali: belgeye bir sey yazmadi
p1 = yurutucu.calistir("raise RuntimeError('bilerek')", "patlayan")
p2 = yurutucu.calistir("raise RuntimeError('bilerek')", "patlayan")
kontrol("patlayan kod 1. sefer hata", not p1.basarili and not p1.engellendi)
kontrol("patlayan kod 2. sefer ENGELLENMEDI (hata yolu tikanmamali)",
        not p2.engellendi, p2.ozet)

# Pencere disi: eski kayit engellememeli
yurutucu._son_kosan["eski kod"] = time.time() - ex.TEKRAR_PENCERESI - 5
kontrol("pencere disindaki ayni kod engellenmiyor",
        yurutucu._tekrar_engeli("eski kod") == "")

# Kayit defteri sinirsiz buyumemeli
for i in range(60):
    yurutucu._tekrar_kaydet("kod %d" % i)
kontrol("kayit defteri sinirli", len(yurutucu._son_kosan) <= 45,
        len(yurutucu._son_kosan))


# ===================================================== 8. GUNLUK
bolum("gunluk engellenen kosuyu hatadan ayiriyor mu")

from caddy import sohbet_log

g = sohbet_log.SohbetGunlugu()
g._kapali = True                      # dosyaya yazmasin, cagri patlamasin
try:
    g.calisma(b)
    g.calisma(a)
    kontrol("gunluk engellenen sonucu patlamadan isledi", True)
except Exception as hata:
    kontrol("gunluk engellenen sonucu patlamadan isledi", False, hata)


# ===================================================== SONUC
_yaz("")
_yaz("=" * 70)
_yaz("gecti: %d   basarisiz: %d" % (gecti, basarisiz))
_yaz("=" * 70)

try:
    App.closeDocument(doc.Name)
except Exception:
    pass

sys.exit(1 if basarisiz else 0)
