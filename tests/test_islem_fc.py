"""FreeCAD'in hazir yeteneklerini acan yardimcilar (islem.py).

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_islem_fc.py

Her yardimci icin UC sey siniyor:

  1. calistigi durum — is gercekten oldu mu
  2. REDDETTIGI durum — yapamayacagini soyluyor mu, yoksa sessizce
     inandirici bir sonuc mu uretiyor
  3. kendi DOGRULAMASI — bekledigini bulamayinca haber veriyor mu

Ucuncusu bu modulun varlik sebebi. Olculdu (MANTIK 23.3):
PartDesign::PolarPattern bir primitife baglanirsa hata VERMIYOR, State
"Up-to-date" diyor, hacim degismiyor — sessizce tek kopya birakiyor.

Rapor dosyaya SATIR SATIR yaziliyor (MANTIK 14.5).
"""

import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_islem.txt")
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
        _yaz("  HATA %s   %s" % (ad, str(ek)[:400]))


def bolum(ad):
    _yaz("")
    _yaz("--- %s %s" % (ad, "-" * max(0, 56 - len(ad))))


import FreeCAD as App
import Mesh
import MeshPart
import Part

from caddy.execution import dogrulama as dg
from caddy.execution import islem
from caddy.execution.executor import CodeExecutor

_yaz("=" * 70)
_yaz("CADdy islem yardimcilari")
_yaz("=" * 70)

doc = App.newDocument("IslemTest")
doc.UndoMode = 1
yurutucu = CodeExecutor()


def kos(kod, baslik="test"):
    """Kodu GERCEK calistirici ile kos — namespace baglamasi da sinanir."""
    s = yurutucu.calistir(kod, baslik)
    if not s.basarili:
        _yaz("       PATLADI: " + s.hata_izi.strip().splitlines()[-1])
    return s


# ===================================================== 1. MESH ONARIMI
bolum("mesh_onar — elle cerrahinin yerini aliyor mu")

kati = Part.makeCone(22.5, 27.7, 95).cut(
    Part.makeCone(20.5, 25.7, 92, App.Vector(0, 0, 3)))
saglam = MeshPart.meshFromShape(Shape=kati, LinearDeflection=0.2,
                                AngularDeflection=0.5)

delikli = Mesh.Mesh(saglam)
delikli.removeFacets(list(range(0, 40)))
o = doc.addObject("Mesh::Feature", "Delikli")
o.Mesh = delikli
doc.recompute()

kontrol("baslangicta ACIK", not delikli.isSolid())

s = kos("mesh_onar(doc.getObject('Delikli'))", "onarim")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("mesh_onar kostu", s.basarili, s.hata_izi)
kontrol("once/sonra ikisi de yazildi", "->" in s.cikti, s.cikti)
kontrol("mesh KAPANDI", doc.getObject("Delikli").Mesh.isSolid(),
        doc.getObject("Delikli").Mesh.isSolid())
# ONARIMIN KENDI suresi olculur, calistirmanin duvar saati DEGIL. Ilk
# calistirma surecteki tek seferlik import bedelini de odiyor: olculdu,
# ayni test arka arkaya 16.5 sn ve 1.56 sn verdi. Duvar saatine bakan esik
# bu yuzden kirilgandi ve olcmek istedigimiz seyi olcmuyordu.
_m = re.search(r"onarildi \(([\d.]+) sn\)", s.cikti)
kontrol("onarim suresi ciktida yaziyor", _m is not None, s.cikti)
if _m:
    kontrol("onarim makul surede (< 1 sn)", float(_m.group(1)) < 1.0,
            _m.group(1))
    _yaz("       onarim %.2f sn (calistirmanin tamami %.2f sn)"
         % (float(_m.group(1)), s.sure_sn))

# Zaten temiz mesh'e DOKUNMAMALI
t = doc.addObject("Mesh::Feature", "Temiz")
t.Mesh = Mesh.createBox(20, 20, 10)
doc.recompute()
onceki_facet = t.Mesh.CountFacets
s = kos("mesh_onar(doc.getObject('Temiz'))", "temiz mesh")
kontrol("temiz mesh'te 'zaten temiz' dedi", "zaten temiz" in s.cikti, s.cikti)
kontrol("temiz mesh'e DOKUNMADI",
        doc.getObject("Temiz").Mesh.CountFacets == onceki_facet,
        doc.getObject("Temiz").Mesh.CountFacets)

s = kos("mesh_onar(doc.getObject('Temiz'))\n"
        "import Part as _P\n"
        "k = doc.addObject('Part::Feature','SadeceKati')\n"
        "k.Shape = _P.makeBox(5,5,5)\n"
        "mesh_onar(k)", "kati uzerinde")
kontrol("kati nesnede mesh_onar reddediyor",
        "mesh nesnesi degil" in s.cikti, s.cikti)


# ===================================================== 2. MESH -> KATI
bolum("kati_yap — parametrik araclarin kapisi")

acik = doc.addObject("Mesh::Feature", "Acik")
am = Mesh.Mesh(saglam)
am.removeFacets(list(range(0, 40)))
acik.Mesh = am
doc.recompute()

s = kos("kati_yap(doc.getObject('Acik'))", "acik mesh")
_yaz("       " + s.cikti.strip())
kontrol("ACIK mesh'i REDDEDIYOR", "KAPALI DEGIL" in s.cikti, s.cikti)
kontrol("ne yapmasi gerektigini soyluyor", "mesh_onar" in s.cikti, s.cikti)
kontrol("nesne EKLEMEDI", doc.getObject("Acik_kati") is None)

s = kos("k = kati_yap(doc.getObject('Delikli'))\nprint('ad:', k.Name)",
        "kapali mesh")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("kapali mesh katiya cevrildi", s.basarili, s.hata_izi)
kontrol("kati nesne olustu", doc.getObject("Delikli_kati") is not None)
kontrol("yuz sayisi yazildi", "yuz" in s.cikti, s.cikti)
kontrol("hacim sapmasi raporlandi", "sapmasi" in s.cikti, s.cikti)
kontrol("PARAMETRIK OLMADIGINI soyluyor",
        "PARAMETRIK bir kati degil" in s.cikti, s.cikti)
kontrol("orijinal mesh gizlendi",
        doc.getObject("Delikli").Visibility is False)

# Facet siniri: buyuk mesh once decimate edilmeli
buyuk = doc.addObject("Mesh::Feature", "Buyuk")
buyuk.Mesh = MeshPart.meshFromShape(Shape=Part.makeSphere(30),
                                    LinearDeflection=0.05,
                                    AngularDeflection=0.1)
doc.recompute()
kontrol("buyuk mesh gercekten buyuk", buyuk.Mesh.CountFacets > 4000,
        buyuk.Mesh.CountFacets)
s = kos("kati_yap(doc.getObject('Buyuk'), azami_facet=1500)", "buyuk mesh")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("facet dususu bildirildi", "decimate uygulandi" in s.cikti, s.cikti)
kontrol("buyuk mesh'te de kati uretildi",
        doc.getObject("Buyuk_kati") is not None)


# ===================================================== 3. ICINI BOSALTMA
bolum("icini_bosalt — kabuk")

sil = doc.addObject("Part::Feature", "Silindir")
sil.Shape = Part.makeCylinder(25, 90)
doc.recompute()
dolu_hacim = sil.Shape.Volume

s = kos("icini_bosalt(doc.getObject('Silindir'), 2.5)", "kabuk")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("kabuk olustu", doc.getObject("Silindir_kabuk") is not None, s.cikti)
kabuk = doc.getObject("Silindir_kabuk")
if kabuk is not None:
    kontrol("hacim ANLAMLI olcude dustu",
            kabuk.Shape.Volume < 0.5 * dolu_hacim,
            (kabuk.Shape.Volume, dolu_hacim))
    kontrol("sonuc gecerli", kabuk.Shape.isValid())
    kontrol("ustu ACIK (kupa gibi)",
            not kabuk.Shape.isClosed() or len(kabuk.Shape.Solids) == 1)

s = kos("icini_bosalt(doc.getObject('Silindir'), 500)", "asiri kalinlik")
kontrol("asiri kalinlikta sessiz kalmiyor",
        "olmadi" in s.cikti or "UYARI" in s.cikti or "kabuk" in s.cikti,
        s.cikti)

s = kos("icini_bosalt(doc.getObject('Temiz'))", "mesh uzerinde")
kontrol("mesh nesnesinde reddediyor", "kati nesne gerek" in s.cikti, s.cikti)


# ===================================================== 4. OLCU TABLOSU
bolum("olcu_tablosu + bagla — olculer tabloda")

s = kos("olcu_tablosu(cap=55.5, yukseklik=95, duvar=2)", "tablo")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("tablo olustu", doc.getObject("Olculer") is not None)
kontrol("degerler yazildi", "cap=55.5" in s.cikti, s.cikti)
kontrol("nasil kullanilacagi soylendi", "bagla(" in s.cikti, s.cikti)

s = kos("sil2 = doc.addObject('Part::Cylinder','Bagli')\n"
        "bagla(sil2, 'Radius', 'Olculer.cap / 2')", "bagla")
_yaz("       " + s.cikti.strip())
bagli = doc.getObject("Bagli")
kontrol("ifade kuruldu", "<-" in s.cikti, s.cikti)
kontrol("deger GERCEKTEN tablodan geldi",
        bagli is not None and abs(float(bagli.Radius) - 27.75) < 0.01,
        None if bagli is None else bagli.Radius)

# Tablo degisince model de degismeli — asil kazanc bu
s = kos("olcu_tablosu(cap=40)\nprint('yeni yaricap:', doc.getObject('Bagli').Radius)",
        "tablo guncelle")
kontrol("hucre degisince model guncellendi", "20" in s.cikti, s.cikti)

s = kos("bagla(doc.getObject('Bagli'), 'Radius', 'Olculer.olmayan_ad * 2')",
        "bozuk ifade")
kontrol("bozuk ifadede COZULMEDI diyor", "COZULMEDI" in s.cikti, s.cikti)
kontrol("hangi alias'in olmadigini soyluyor", "olmayan_ad" in s.cikti, s.cikti)
kontrol("eski deger korundu", abs(float(bagli.Radius) - 20.0) < 0.01,
        bagli.Radius)


# ===================================================== 5. YAZI
bolum("yazi — parca uzerine metin")

s = kos("y = yazi('CADdy', boyut=10, kalinlik=2)", "yazi")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("yazi uretildi", s.basarili and "CADdy" in s.cikti, s.cikti)
kontrol("olculeri yazildi", "mm" in s.cikti, s.cikti)
kontrol("nereye kondugu soylendi", "XY duzleminde" in s.cikti, s.cikti)

s = kos("yazi('X', font=r'C:\\yok\\boyle\\bir\\font.ttf')", "font yolu yanlis")
kontrol("yanlis font yolunda calisir kaliyor (sistemden buluyor)",
        s.basarili, s.hata_izi)


# ===================================================== 6. VIDA DISI
bolum("vida_disi — banjo civatasi oturumunun eksigi")

s = kos("v = vida_disi(4, 1.25, 20)", "M8 dis")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("vida disi uretildi", doc.getObject("VidaDisi") is not None, s.cikti)
vd = doc.getObject("VidaDisi")
if vd is not None:
    kontrol("tek kati", len(vd.Shape.Solids) == 1, len(vd.Shape.Solids))
    kontrol("gecerli", vd.Shape.isValid())
    kontrol("hacim silindirden BUYUK (dis disari cikiyor)",
            vd.Shape.Volume > 3.14159 * 16 * 20, vd.Shape.Volume)
    kontrol("tur sayisi yazildi", "tur" in s.cikti, s.cikti)

s = kos("vida_disi(-1, 1, 10)", "gecersiz olcu")
kontrol("gecersiz olcuyu reddediyor", "pozitif olmali" in s.cikti, s.cikti)


# ===================================================== 7. AGIRLIK
bolum("agirlik — 'kac gram gelir'")

s = kos("k = doc.addObject('Part::Box','Kup')\n"
        "k.Length = k.Width = k.Height = 50\n"
        "doc.recompute()\n"
        "agirlik(k)", "PLA agirlik")
_yaz("       " + s.cikti.strip())
kontrol("agirlik hesaplandi", "g" in s.cikti and "cm3" in s.cikti, s.cikti)
kontrol("PLA 50mm kup = ~155 g", "155" in s.cikti, s.cikti)
kontrol("filament uzunlugu da verildi", "m filament" in s.cikti, s.cikti)

s = kos("agirlik(doc.getObject('Kup'), 'PETG', doluluk=0.2)", "doluluk")
kontrol("doluluk hesaba katildi", "doluluk" in s.cikti, s.cikti)
kontrol("alt sinir oldugunu soyluyor", "alt sinir" in s.cikti, s.cikti)

s = kos("agirlik(doc.getObject('Kup'), 'ADAMANTIUM')", "bilinmeyen malzeme")
kontrol("bilinmeyen malzemede liste veriyor", "Bilinenler" in s.cikti, s.cikti)


# ===================================================== 8. BASKIYA BOLME
bolum("baskiya_bol — 'gerekirse 2 parca yapariz'")

uzun = doc.addObject("Part::Feature", "Uzun")
uzun.Shape = Part.makeBox(30, 30, 200)
doc.recompute()

s = kos("baskiya_bol(doc.getObject('Uzun'))", "ortadan bol")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("iki parca olustu",
        doc.getObject("Uzun_p1") is not None
        and doc.getObject("Uzun_p2") is not None, s.cikti)
kontrol("parca olculeri yazildi", "hacim=" in s.cikti, s.cikti)
kontrol("gecme uyarisi verildi", "gecme" in s.cikti, s.cikti)
if doc.getObject("Uzun_p1") is not None:
    kontrol("parcalarin toplami butune esit",
            abs(doc.getObject("Uzun_p1").Shape.Volume
                + doc.getObject("Uzun_p2").Shape.Volume - 180000) < 1.0,
            doc.getObject("Uzun_p1").Shape.Volume)

s = kos("baskiya_bol(doc.getObject('Uzun'), z=9999)", "govde disi")
kontrol("govde disinda z reddediliyor", "disinda" in s.cikti, s.cikti)


# ===================================================== 9. DIZILER
bolum("dizi_polar / dizi_dogrusal")

s = kos("d = doc.addObject('Part::Cylinder','Pim')\n"
        "d.Radius = 2; d.Height = 10\n"
        "d.Placement.Base = App.Vector(20, 0, 0)\n"
        "doc.recompute()\n"
        "dizi_polar(d, 6)", "polar dizi")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("polar dizi kuruldu", s.basarili and "x6" in s.cikti, s.cikti)

s = kos("dizi_dogrusal(doc.getObject('Kup'), 3, App.Vector(1,0,0), 60)",
        "dogrusal dizi")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("dogrusal dizi kuruldu", s.basarili and "x3" in s.cikti, s.cikti)

s = kos("dizi_polar(doc.getObject('Kup'), 1)", "adet 1")
kontrol("adet<2 reddediliyor", "en az 2" in s.cikti, s.cikti)


# ===================================================== 10. TABANA OTURTMA
bolum("tabana_otur — baski hazirliginin ilk sorusu")

yatik = doc.addObject("Part::Feature", "YatikKutu")
ys = Part.makeBox(40, 20, 10)
ys.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 30)
yatik.Shape = ys
doc.recompute()

s = kos("tabana_otur(doc.getObject('YatikKutu'))", "yatik kutu")
_yaz("       " + s.cikti.strip())
kontrol("dondurulup oturtuldu", s.basarili and "tablaya oturtuldu" in s.cikti,
        s.cikti)
kontrol("z tabandan basliyor",
        abs(doc.getObject("YatikKutu").Shape.BoundBox.ZMin) < 0.01,
        doc.getObject("YatikKutu").Shape.BoundBox.ZMin)

kure = doc.addObject("Part::Feature", "Kure")
kure.Shape = Part.makeSphere(20)
doc.recompute()
s = kos("tabana_otur(doc.getObject('Kure'))", "duz yuzu yok")
kontrol("duz yuzu olmayan parcada UYDURMUYOR",
        "duz bir yuz bulunamadi" in s.cikti or "duz yeri yok" in s.cikti,
        s.cikti)


# ===================================================== 11. BIRLESTIRME
bolum("birlestir — temiz kaynak")

s = kos("a = doc.addObject('Part::Feature','GovdeA')\n"
        "a.Shape = Part.makeBox(30, 30, 10)\n"
        "b = doc.addObject('Part::Feature','GovdeB')\n"
        "b.Shape = Part.makeCylinder(4, 30, App.Vector(15, 15, 0))\n"
        "doc.recompute()\n"
        "birlestir(a, b)", "birlestir")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("birlesik nesne olustu", doc.getObject("GovdeA_birlesik") is not None,
        s.cikti)
kontrol("tek kati oldugu dogrulandi", "1 kati" in s.cikti, s.cikti)

s = kos("c = doc.addObject('Part::Feature','UzakC')\n"
        "c.Shape = Part.makeBox(5,5,5, App.Vector(500,500,0))\n"
        "doc.recompute()\n"
        "birlestir(doc.getObject('GovdeA'), c)", "degmeyen parcalar")
kontrol("degmeyen parcalarda UYARI veriyor",
        "DEGMIYOR" in s.cikti, s.cikti)


bolum("birlestir — MESH yolu (gunlukteki 16 dakikalik cikmazin testi)")

# OLCULEN SENARYO: model `birlestir(govde_obj, kulp_obj)` cagirdi, ikisi de
# mesh'ti, yardimci "iki KATI nesne gerek" deyip durdu ve model 13
# calistirma / 16 dakika boyunca kulbu katiya cevirmeye calisti. Cagri
# dogruydu; calismasi gerekiyordu.
_mesh_kur = (
    "import MeshPart\n"
    "def _mesh(ad, sekil):\n"
    "    o = doc.addObject('Mesh::Feature', ad)\n"
    "    o.Mesh = MeshPart.meshFromShape(Shape=sekil, LinearDeflection=0.5,\n"
    "                                    AngularDeflection=0.5, Relative=False)\n"
    "    return o\n")

s = kos(_mesh_kur +
        "ma = _mesh('MeshGovde', Part.makeCylinder(20, 40))\n"
        "mb = _mesh('MeshKulp', Part.makeCylinder(5, 30, App.Vector(18, 0, 5)))\n"
        "doc.recompute()\n"
        "print('girdi kapali:', ma.Mesh.isSolid(), mb.Mesh.isSolid())\n"
        "sonuc = birlestir(ma, mb)\n"
        "print('donen:', getattr(sonuc, 'Name', None))", "mesh birlestir")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("mesh + mesh ARTIK reddedilmiyor",
        "iki KATI nesne gerek" not in s.cikti, s.cikti)
birlesik = doc.getObject("MeshGovde_birlesik")
kontrol("mesh birlesigi olustu", birlesik is not None, s.cikti)
if birlesik is not None:
    m = birlesik.Mesh
    kontrol("sonuc mesh KAPALI", m.isSolid(), m.isSolid())
    kontrol("sonuc TEK parca", m.countComponents() == 1, m.countComponents())
    ayri = (doc.getObject("MeshGovde").Mesh.Volume
            + doc.getObject("MeshKulp").Mesh.Volume)
    kontrol("hacim ayri toplamdan KUCUK (gercekten kaynasti)",
            m.Volume < ayri, "%.1f >= %.1f" % (m.Volume, ayri))
    kontrol("sure ciktida yaziyor", " sn]" in s.cikti, s.cikti)

# ACIK mesh reddedilmeli — acik mesh'ten kati cikmaz.
s = kos(_mesh_kur +
        "acik = _mesh('AcikMesh', Part.makeCylinder(10, 20))\n"
        "yz = acik.Mesh.copy()\n"
        "yz.removeFacets([0, 1, 2, 3])\n"
        "acik.Mesh = yz\n"
        "kapali = _mesh('KapaliMesh', Part.makeCylinder(10, 20, App.Vector(8,0,0)))\n"
        "doc.recompute()\n"
        "print('acik mi:', not acik.Mesh.isSolid())\n"
        "birlestir(acik, kapali)", "acik mesh")
kontrol("ACIK mesh'te reddediyor ve mesh_onar oneriyor",
        "KAPALI DEGIL" in s.cikti and "mesh_onar" in s.cikti, s.cikti)
kontrol("acik mesh'te YARIM nesne birakmiyor",
        doc.getObject("AcikMesh_birlesik") is None)

# DEGMEYEN iki mesh: bosluk soylenmeli, 7 saniyelik islem hic baslamamali.
s = kos(_mesh_kur +
        "u1 = _mesh('UzakMesh1', Part.makeBox(10,10,10))\n"
        "u2 = _mesh('UzakMesh2', Part.makeBox(10,10,10, App.Vector(400,0,0)))\n"
        "doc.recompute()\n"
        "birlestir(u1, u2)", "degmeyen mesh")
kontrol("degmeyen mesh'lerde DEGMIYOR diyor", "DEGMIYOR" in s.cikti, s.cikti)
kontrol("bosluk sayisi veriliyor", "bosluk" in s.cikti, s.cikti)
kontrol("degmeyen mesh'te YARIM nesne birakmiyor",
        doc.getObject("UzakMesh1_birlesik") is None)

# Kati + kati yolu AYNEN calismaya devam etmeli (regresyon).
kontrol("kati yolu bozulmadi (GovdeA_birlesik hala kati)",
        doc.getObject("GovdeA_birlesik") is not None
        and doc.getObject("GovdeA_birlesik").isDerivedFrom("Part::Feature"))

# Biri kati biri mesh: karistirmiyor, ne yapilacagini soyluyor.
s = kos(_mesh_kur +
        "km = _mesh('KarisikMesh', Part.makeBox(10,10,10))\n"
        "kk = doc.addObject('Part::Feature','KarisikKati')\n"
        "kk.Shape = Part.makeBox(10,10,10, App.Vector(5,0,0))\n"
        "doc.recompute()\n"
        "birlestir(km, kk)", "karisik tur")
kontrol("kati+mesh karisiminda kati_yap oneriyor",
        "kati_yap" in s.cikti, s.cikti)


# ===================================================== 12. SESSIZ DESEN HATASI
bolum("dogrulama: desen tek kopya biraktiysa yakalaniyor mu")

# OLCULEN SENARYO: primitife baglanan PolarPattern hata vermez, State
# "Up-to-date" der, hacim degismez.
b = doc.addObject("PartDesign::Body", "Govde")
taban = doc.addObject("PartDesign::AdditiveCylinder", "Taban")
taban.Radius = 30
taban.Height = 5
b.addObject(taban)
doc.recompute()
delik = doc.addObject("PartDesign::SubtractiveCylinder", "Oyuk")
delik.Radius = 2
delik.Height = 10
delik.AttachmentOffset = App.Placement(App.Vector(20, 0, -1), App.Rotation())
b.addObject(delik)
doc.recompute()
pol = doc.addObject("PartDesign::PolarPattern", "Desen")
b.addObject(pol)
pol.Originals = [delik]
pol.Axis = (b.Origin.OriginFeatures[2], [""])
pol.Angle = 360
pol.Occurrences = 6
b.Tip = pol
doc.recompute()

kontrol("desen HATA VERMIYOR (sessiz)", "Up-to-date" in list(pol.State),
        list(pol.State))
kontrol("hacim BaseFeature ile ayni (tek kopya)",
        abs(pol.Shape.Volume - delik.Shape.Volume) < 1e-6,
        (pol.Shape.Volume, delik.Shape.Volume))

r = dg.dogrula(doc, ["Desen"])
_yaz("       " + r.metin().replace("\n", "\n       "))
kontrol("DOGRULAMA bunu yakaliyor",
        any(b.tur == "desen tek kopya birakti" for b in r.bulgular),
        [str(x) for x in r.bulgular])
kontrol("sebebi de yaziyor",
        any("PRIMITIFE" in b.ayrinti for b in r.bulgular),
        [str(x) for x in r.bulgular])
kontrol("kontrol KOSAN listesinde",
        any("desen" in k for k in r.kosan), r.kosan)

# Eskiz tabanli desen DOGRU calisiyor -> bulgu OLMAMALI
import Sketcher  # noqa: F401

b2 = doc.addObject("PartDesign::Body", "Govde2")
t2 = doc.addObject("PartDesign::AdditiveCylinder", "Taban2")
t2.Radius = 30
t2.Height = 5
b2.addObject(t2)
doc.recompute()
sk = doc.addObject("Sketcher::SketchObject", "SkDelik")
b2.addObject(sk)
sk.AttachmentSupport = (b2.Origin.OriginFeatures[3], [""])
sk.MapMode = "FlatFace"
sk.addGeometry(Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 2),
               False)
doc.recompute()
po = doc.addObject("PartDesign::Pocket", "Cep")
po.Profile = sk
po.Length = 10
po.Reversed = True
b2.addObject(po)
doc.recompute()
pol2 = doc.addObject("PartDesign::PolarPattern", "Desen2")
b2.addObject(pol2)
pol2.Originals = [po]
pol2.Axis = (b2.Origin.OriginFeatures[2], [""])
pol2.Angle = 360
pol2.Occurrences = 6
b2.Tip = pol2
doc.recompute()

kontrol("eskiz tabanli desen GERCEKTEN cogaltti",
        abs(pol2.Shape.Volume - 13760.2) < 5.0, pol2.Shape.Volume)
r = dg.dogrula(doc, ["Desen2"])
kontrol("dogru desende YANLIS ALARM yok",
        not any(b.tur == "desen tek kopya birakti" for b in r.bulgular),
        [str(x) for x in r.bulgular])


# ===================================================== 13. NAMESPACE
bolum("yardimcilarin hepsi namespace'te mi")

s = kos("adlar = ['mesh_onar','kati_yap','icini_bosalt','olcu_tablosu',"
        "'bagla','yazi','vida_disi','agirlik','baskiya_bol','dizi_polar',"
        "'dizi_dogrusal','tabana_otur','birlestir','kesit_konturu',"
        "'olc','kesit_capi','duvar_kalinligi','mesafe','olcu',"
        "'baski_kontrol','kesif']\n"
        # DIKKAT: liste kavrayisi kendi kapsamini acar; icinde dir() modul
        # genelini DEGIL kavrayisin yerelini verir. globals() dogrusu.
        "g = globals()\n"
        "eksik = [a for a in adlar if a not in g]\n"
        "print('eksik:', eksik)", "namespace")
kontrol("21 yardimcinin hepsi bagli", "eksik: []" in s.cikti, s.cikti)


# ============================================ 14. kesit_konturu
# NEDEN VAR: iki ayri oturumda iki ayri model ayni on satiri elle yazdi.
# LOG/2026-08-24_67cd3efb (Sonnet) slice dongusuyle 68.9 sn harcadi;
# LOG/2026-08-24_3ad4cef1 (Opus) makeShapeFromMesh->slice->discretize
# kalibini BES ayri blokta bastan yazdi.
bolum("kesit_konturu — kesit hatti artik yardimci")

s = kos("import Part\n"
        "o = doc.addObject('Part::Feature', 'KesitKutu')\n"
        "o.Shape = Part.makeBox(20, 30, 10)\n"
        "doc.recompute()\n"
        "k = kesit_konturu(o, 5.0)\n"
        "print('kontur sayisi:', len(k))\n"
        "print('nokta sayisi:', len(k[0]) if k else 0)\n"
        "print('ilk nokta tipi:', type(k[0][0]).__name__, len(k[0][0]))\n"
        "xs = [p[0] for p in k[0]]\n"
        "print('x araligi:', round(min(xs), 1), round(max(xs), 1))",
        "kesit kati")
kontrol("katida kontur veriyor", "kontur sayisi: 1" in s.cikti, s.cikti)
kontrol("nokta listesi (x, y) ciftlerinden",
        "ilk nokta tipi: tuple 2" in s.cikti, s.cikti)
kontrol("koordinatlar GERCEK olculer", "x araligi: 0.0 20.0" in s.cikti,
        s.cikti)

s = kos("import Part\n"
        "o = doc.addObject('Part::Feature', 'KesitBoru')\n"
        "o.Shape = Part.makeCylinder(20, 10).cut(Part.makeCylinder(12, 10))\n"
        "doc.recompute()\n"
        "k = kesit_konturu(o, 5.0)\n"
        "print('kontur sayisi:', len(k))\n"
        "uz = [len(c) for c in k]\n"
        "print('sirali mi:', uz == sorted(uz, reverse=True), uz)",
        "kesit delikli")
kontrol("delikte IKI kontur cikiyor (dis + delik)",
        "kontur sayisi: 2" in s.cikti, s.cikti)
kontrol("EN UZUN once — [0] her zaman dis hat",
        "sirali mi: True" in s.cikti, s.cikti)

s = kos("import Mesh\n"
        "onceki = len(doc.Objects)\n"
        "m = doc.addObject('Mesh::Feature', 'KesitKure')\n"
        "m.Mesh = Mesh.createSphere(15.0, 30)\n"
        "doc.recompute()\n"
        "k = kesit_konturu(m)\n"        # z verilmedi -> ortadan kessin
        "print('kontur sayisi:', len(k))\n"
        "print('yeni nesne sayisi:', len(doc.Objects) - onceki)",
        "kesit mesh")
kontrol("MESH uzerinde de calisiyor", "kontur sayisi: 1" in s.cikti, s.cikti)
kontrol("BELGEYE nesne EKLEMIYOR (kati_yap'in aksine)",
        "yeni nesne sayisi: 1" in s.cikti, s.cikti)   # yalnizca mesh'in kendisi

# ---- DUZ YUZEYE DENK GELEN KESIT: eski surumde SESSIZCE YANLISTI ----
# OLCULDU: silindir r=15 h=40 z=0'da alan 7.2 mm2 (dogrusu 706.9), kutu
# z=0'da 300 (dogrusu 600), kademeli parcada omuz hizasinda 600 — ne
# asagisi (1600) ne yukarisi (400). Hicbiri hata vermiyordu.
bolum("kesit_konturu — duz yuzeye denk gelen kesit artik yalan soylemiyor")

_ALAN = ("def _alan(p):\n"
         "    a = 0.0\n"
         "    for i in range(len(p)):\n"
         "        x1, y1 = p[i]; x2, y2 = p[(i + 1) % len(p)]\n"
         "        a += x1 * y2 - x2 * y1\n"
         "    return abs(a) / 2\n")

s = kos("import MeshPart, Part\n" + _ALAN +
        "m = MeshPart.meshFromShape(Shape=Part.makeCylinder(15, 40),\n"
        "                           LinearDeflection=0.2)\n"
        "o = doc.addObject('Mesh::Feature', 'SilUc')\n"
        "o.Mesh = m\ndoc.recompute()\n"
        "for z in (0.0, 40.0, 20.0):\n"
        "    k = kesit_konturu(o, z, yaz=False)\n"
        "    print('z=%g alan=%.1f' % (z, _alan(k[0]) if k else -1))",
        "kesit uc silindir")
kontrol("silindir z=0 artik dogru (eskiden 7.2)",
        "z=0 alan=700.6" in s.cikti, s.cikti)
kontrol("silindir z=40 artik dogru (eskiden 7.2)",
        "z=40 alan=700.6" in s.cikti, s.cikti)
kontrol("normal yukseklik bozulmadi", "z=20 alan=700.6" in s.cikti, s.cikti)

s = kos("import MeshPart, Part\n" + _ALAN +
        "m = MeshPart.meshFromShape(Shape=Part.makeBox(20, 30, 10),\n"
        "                           LinearDeflection=0.2)\n"
        "o = doc.addObject('Mesh::Feature', 'KutuUc')\n"
        "o.Mesh = m\ndoc.recompute()\n"
        "k = kesit_konturu(o, 0.0)\n"
        "print('alan=%.1f' % _alan(k[0]))", "kesit uc kutu")
kontrol("kutu z=0 artik dogru (eskiden 300)", "alan=599.8" in s.cikti, s.cikti)
kontrol("kaydirdigini SOYLUYOR (sessizce duzeltmiyor)",
        "tam ucta" in s.cikti and "kaydirildi" in s.cikti, s.cikti)

# IC yatay yuzey: kaydirilamaz (hangi tarafi istedigi cagirana ait),
# ama uyarilmali ve guvenli komsular yazilmali.
s = kos("import MeshPart, Part\n"
        "sekil = Part.makeBox(40, 40, 10).fuse(\n"
        "    Part.makeBox(20, 20, 10, Vector(10, 10, 10)))\n"
        "m = MeshPart.meshFromShape(Shape=sekil, LinearDeflection=0.2)\n"
        "o = doc.addObject('Mesh::Feature', 'Kademe')\n"
        "o.Mesh = m\ndoc.recompute()\n"
        "kesit_konturu(o, 10.0)\n"
        "print('---')\n"
        "kesit_konturu(o, 5.0)", "kesit ic omuz")
_ust, _alt = s.cikti.split("---", 1) if "---" in s.cikti else (s.cikti, "")
kontrol("IC yatay yuzeyde UYARI veriyor", "UYARI" in _ust, _ust)
kontrol("uyari guvenli komsu z'leri soyluyor",
        "9.96" in _ust and "10.04" in _ust, _ust)
kontrol("normal yukseklikte YANLIS ALARM yok", "UYARI" not in _alt, _alt)

bolum("kesit_konturu — coklu z tek donusum")
s = kos("import Mesh\n"
        "o = doc.addObject('Mesh::Feature', 'CokluKure')\n"
        "o.Mesh = Mesh.createSphere(30.0, 32)\ndoc.recompute()\n"
        "d = kesit_konturu(o, [-10.0, 0.0, 10.0], yaz=False)\n"
        "print('tip:', type(d).__name__)\n"
        "print('anahtar:', sorted(d.keys()))\n"
        "print('hepsi dolu:', all(len(v) >= 1 for v in d.values()))",
        "kesit coklu")
kontrol("liste verilince SOZLUK doner", "tip: dict" in s.cikti, s.cikti)
kontrol("anahtarlar istenen z'ler",
        "anahtar: [-10.0, 0.0, 10.0]" in s.cikti, s.cikti)
kontrol("her yukseklikte kontur var", "hepsi dolu: True" in s.cikti, s.cikti)

s = kos("import Part\n"
        "o = doc.addObject('Part::Feature', 'KesitDis')\n"
        "o.Shape = Part.makeBox(10, 10, 10)\n"
        "doc.recompute()\n"
        "k = kesit_konturu(o, 500.0)\n"
        "print('sonuc:', k)", "kesit disarida")
kontrol("parcanin cok disinda BOS liste doner", "sonuc: []" in s.cikti,
        s.cikti)
kontrol("disaridaki z KAYDIRILMIYOR — sorulmayan soru cevaplanmaz",
        "kaydirildi" not in s.cikti, s.cikti)
kontrol("ve nedenini soyluyor", "disinda" in s.cikti, s.cikti)


# --------------------------------------------------------------------------
bolum("kesit_konturu — BOZUK mesh'i pahali donusumden ONCE soyluyor")
# OLCULDU (LOG/2026-09-01_361c792d.txt): indirilen ucak mesh'inde (34350
# facet) alti yukseklikli tek cagri 22.66 sn surdu ve alti ozdes "kontur
# yok" satiri yazdi. Cevabin bos cikacagi 0.05 saniyede biliniyordu
# (isSolid/hasNonManifolds/hasSelfIntersections/countComponents).
s = kos("import Mesh, FreeCAD\n"
        "o = doc.addObject('Mesh::Feature', 'BozukMesh')\n"
        # Birbirine degmeyen UC ucgen: kapali degil, uc ayrik parca.
        "mm = Mesh.Mesh()\n"
        "V = FreeCAD.Vector\n"
        "for i in range(3):\n"
        "    d = i * 50.0\n"
        "    mm.addFacet(V(d, 0, 0), V(d + 10, 0, 0), V(d, 10, 5))\n"
        "o.Mesh = mm\ndoc.recompute()\n"
        "k = kesit_konturu(o, [1.0, 2.0, 3.0])", "bozuk mesh kesiti")
kontrol("donusumden ONCE uyari veriliyor",
        "mesh saglam degil" in s.cikti, s.cikti)
kontrol("uyari kusurlari ADIYLA sayiyor",
        "kapali degil" in s.cikti and "ayrik parca" in s.cikti, s.cikti)
kontrol("facet sayisi da yaziliyor (maliyetin kaynagi)",
        "facet" in s.cikti, s.cikti)
# Hepsi bos cikan durum: butun ucgenler YATAY (z=0 ve z=10). Arada hicbir
# yuzey yok, yani z=5 kesiti bosluga denk gelir; ama bbox 0..10 oldugu icin
# bu "parcanin disinda" DEGIL. Mesh acik ve cok parcali -> uyari da verilir.
s = kos("import Mesh, FreeCAD\n"
        "o = doc.addObject('Mesh::Feature', 'YatayKatlar')\n"
        "mm = Mesh.Mesh()\n"
        "V = FreeCAD.Vector\n"
        "for zz in (0.0, 10.0):\n"
        "    mm.addFacet(V(0, 0, zz), V(10, 0, zz), V(0, 10, zz))\n"
        "o.Mesh = mm\ndoc.recompute()\n"
        "k = kesit_konturu(o, [4.0, 5.0, 6.0])", "bos kesit sebebi")
kontrol("hepsi bos cikinca SEBEP soyleniyor",
        "YUKSEKLIK SECIMI DEGIL" in s.cikti, s.cikti)
kontrol("sebep mesh kusurunu ADIYLA tekrar ediyor",
        "kapali degil" in s.cikti.split("YUKSEKLIK SECIMI DEGIL")[-1], s.cikti)
kontrol("ve baska bir olcum ADIYLA oneriliyor (genel ogut degil)",
        "olc()" in s.cikti and "bbox" in s.cikti, s.cikti)

# SAGLAM mesh'te tek satir bile gurultu olmamali.
s = kos("import Mesh\n"
        "o = doc.addObject('Mesh::Feature', 'SaglamKure')\n"
        "o.Mesh = Mesh.createSphere(20.0, 32)\ndoc.recompute()\n"
        "k = kesit_konturu(o, [0.0, 5.0])", "saglam mesh kesiti")
kontrol("saglam mesh'te uyari YOK", "mesh saglam degil" not in s.cikti,
        s.cikti)
kontrol("saglam mesh'te kontur var", "kontur yok" not in s.cikti, s.cikti)

# KATI nesnede on kontrol hic kosmaz (mesh dali degil).
s = kos("import Part\n"
        "o = doc.addObject('Part::Feature', 'OnKontrolKati')\n"
        "o.Shape = Part.makeBox(10, 10, 10)\ndoc.recompute()\n"
        "k = kesit_konturu(o, 5.0)", "kati on kontrol")
kontrol("katida mesh on kontrolu kosmuyor",
        "mesh saglam degil" not in s.cikti, s.cikti)

# Mesh SAGLAMKEN bos sonuca mesh sucu ATILMAMALI.
s = kos("import Mesh\n"
        "o = doc.addObject('Mesh::Feature', 'SaglamKure2')\n"
        "o.Mesh = Mesh.createSphere(20.0, 32)\ndoc.recompute()\n"
        "k = kesit_konturu(o, 500.0)", "saglam mesh disarida")
kontrol("saglam mesh'te bos sonuca mesh sucu atilmiyor",
        "YUKSEKLIK SECIMI DEGIL" not in s.cikti, s.cikti)


# ============================ 15. birlestir BASKI GERCEGINI soyluyor
# OLCULEN KAYIP (LOG/2026-08-24_3ad4cef1, 12:08 -> 12:09): birlestir
# "hacim=5.551e+04 mm3, 1 kati" dedi, isValid() True idi. Ayni sekil disa
# aktarma icin mesh'lenince kapali degil + kendini kesen + non-manifold
# cikti. 108 saniyelik islem yanlis guven verdi, hata isin SONUNDA patladi.
bolum("birlestir — 'gecerli kati' ile 'basilabilir' ayni sey degil")

s = kos("import Part\n"
        "a = doc.addObject('Part::Feature', 'BirA')\n"
        "a.Shape = Part.makeBox(10, 10, 10)\n"
        "b = doc.addObject('Part::Feature', 'BirB')\n"
        "b.Shape = Part.makeBox(10, 10, 10, Vector(5, 5, 0))\n"
        "doc.recompute()\n"
        "r = birlestir(a, b)\n"
        "print('nesne dondu:', r is not None)", "birlestir temiz")
kontrol("temiz birlesme oluyor", "nesne dondu: True" in s.cikti, s.cikti)
kontrol("BASKI verdikti veriliyor — hacim tek basina yetmez",
        "baskiya hazir" in s.cikti, s.cikti)
kontrol("hangi yolun kullanildigi yaziliyor", "(connect)" in s.cikti, s.cikti)
kontrol("facet sayisi da yaziliyor (kanit)", "facet" in s.cikti, s.cikti)

# connect MESH KOKENLI katida patliyor — olculdu: "There is more than one
# largest piece!". Eskiden bu durumda None donuyorduk, yani calisan bir yol
# (duz fuse) dururken model cikmaza giriyordu.
s = kos("import Mesh, Part\n"
        "kure = Mesh.createSphere(12.0, 30)\n"
        "sh = Part.Shape(); sh.makeShapeFromMesh(kure.Topology, 0.1)\n"
        "mk = doc.addObject('Part::Feature', 'MeshKati')\n"
        "mk.Shape = Part.makeSolid(sh)\n"
        "kt = doc.addObject('Part::Feature', 'Kesen')\n"
        "kt.Shape = Part.makeBox(20, 20, 10, Vector(-10, -10, -5))\n"
        "doc.recompute()\n"
        "r = birlestir(mk, kt)\n"
        "print('nesne dondu:', r is not None)\n"
        "print('kati sayisi:', len(r.Shape.Solids) if r else 0)",
        "birlestir mesh kokenli")
kontrol("connect patlayinca None DONMUYOR", "nesne dondu: True" in s.cikti,
        s.cikti)
kontrol("duz fuse'a dustugu SOYLENIYOR",
        "fuse ile devam" in s.cikti and "(fuse)" in s.cikti, s.cikti)
kontrol("sonuc tek kati", "kati sayisi: 1" in s.cikti, s.cikti)
kontrol("bu yolda da baski verdikti var", "baskiya hazir" in s.cikti, s.cikti)

# yaz=False cagiran ciktiyi istemiyorsa MALIYETI de odememeli.
s = kos("import time, Part\n"
        "c = doc.addObject('Part::Feature', 'BirC')\n"
        "c.Shape = Part.makeBox(10, 10, 10)\n"
        "d = doc.addObject('Part::Feature', 'BirD')\n"
        "d.Shape = Part.makeBox(10, 10, 10, Vector(5, 5, 0))\n"
        "doc.recompute()\n"
        "t = time.time(); birlestir(c, d, yaz=False)\n"
        "print('sessiz sure: %.3f' % (time.time() - t))\n"
        "print('hic cikti var mi: HAYIR')", "birlestir sessiz")
kontrol("yaz=False hicbir sey yazdirmiyor",
        "baskiya hazir" not in s.cikti, s.cikti)


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
