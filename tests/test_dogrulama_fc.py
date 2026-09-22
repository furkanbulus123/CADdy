"""Deterministik geometri dogrulamasini FreeCAD motorunda sinar.

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_dogrulama_fc.py

DIKKAT: freecadcmd, betikten SONRAKI argumanlari sys.argv'ye koymaz.
Bu betik arguman ALMAZ.

Sinadigi asil sey su iki iddia — ikisi de burada OLCULDU, tahmin degil:

  * ters kati (negatif hacim) isValid() kontrolunu GECIYOR
  * acik kabuk da isValid() kontrolunu GECIYOR

Yani "isValid() calistirdim, temiz" demek yanlis bir guven. Dogrulama bu
ikisini ayrica ariyor; testin isi o aramanin gercekten calistigini
gostermek.

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

RAPOR = os.path.join(KOK, "tests", "_son_dogrulama.txt")
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

from caddy.execution import dogrulama as dg
from caddy.execution.executor import CodeExecutor

_yaz("=" * 70)
_yaz("CADdy dogrulama testleri")
_yaz("=" * 70)

doc = App.newDocument("DogrulamaTest")
doc.UndoMode = 1


def _koy(ad, sekil):
    """Ham sekli belgeye koyar. Test icin gerekli — normalde YASAK (olu sekil)."""
    o = doc.addObject("Part::Feature", ad)
    o.Shape = sekil
    doc.recompute()
    return o


# --------------------------------------------------------------- saglam kati
bolum("saglam kati — bulgu OLMAMALI")
iyi = _koy("Iyi", Part.makeBox(20, 20, 10))
r = dg.dogrula(doc, ["Iyi"])
_yaz("       " + r.metin().replace("\n", "\n       "))
kontrol("bulgu yok", r.temiz, [str(b) for b in r.bulgular])
kontrol("bakilan 1", r.bakilan == 1, r.bakilan)
kontrol("olcum yazildi", any("hacim=4000" in o for o in r.olcumler), r.olcumler)
kontrol("kosan kontroller listelendi", len(r.kosan) >= 4, r.kosan)
kontrol("kosMAYAN kontrol de yazildi (sessizce temiz sayilmiyor)",
        any("kesisme" in a for a in r.atlanan), r.atlanan)

# ------------------------------------------------------------------ ters kati
bolum("TERS KATI — isValid() bunu yakalamiyor")
ters_sekil = Part.makeBox(10, 10, 10).reversed()
kontrol("On kabul: isValid() ters katiya True diyor",
        ters_sekil.isValid() is True, ters_sekil.isValid())
kontrol("On kabul: hacim negatif", ters_sekil.Volume < 0, ters_sekil.Volume)

_koy("Ters", ters_sekil)
r2 = dg.dogrula(doc, ["Ters"])
_yaz("       " + r2.metin().replace("\n", "\n       "))
kontrol("ters kati YAKALANDI", any(b.tur == "ters kati" for b in r2.bulgular),
        [str(b) for b in r2.bulgular])
kontrol("bulgu isValid'e degil hacme dayaniyor",
        any("negatif" in b.ayrinti for b in r2.bulgular),
        [b.ayrinti for b in r2.bulgular])

# ------------------------------------------------------- bilesikte toplam sifir
bolum("BILESIK — toplam hacim 0, tek tek bakilmali")
a = Part.makeBox(10, 10, 10)
b = Part.makeBox(10, 10, 10, App.Vector(20, 0, 0)).reversed()
bilesik = Part.Compound([a, b])
kontrol("On kabul: bilesigin TOPLAM hacmi 0", abs(bilesik.Volume) < 1e-6,
        bilesik.Volume)
_koy("Bilesik", bilesik)
r3 = dg.dogrula(doc, ["Bilesik"])
_yaz("       " + r3.metin().replace("\n", "\n       "))
kontrol("toplama bakan bir kontrol kacirirdi — biz yakaladik",
        any(b.tur == "ters kati" for b in r3.bulgular),
        [str(b) for b in r3.bulgular])

# ----------------------------------------------------------------- acik kabuk
bolum("ACIK KABUK — isValid() bunu da yakalamiyor")
kabuk = Part.Shell(Part.makeBox(10, 10, 10).Faces[:5])
kontrol("On kabul: acik kabuk isValid() True", kabuk.isValid() is True,
        kabuk.isValid())
kontrol("On kabul: isClosed() False", kabuk.isClosed() is False,
        kabuk.isClosed())
_koy("Kabuk", kabuk)
r4 = dg.dogrula(doc, ["Kabuk"])
_yaz("       " + r4.metin().replace("\n", "\n       "))
kontrol("acik kabuk YAKALANDI", any(b.tur == "acik kabuk" for b in r4.bulgular),
        [str(b) for b in r4.bulgular])

# ------------------------------------------------------------ kurt masali yok
bolum("YANLIS ALARM OLMAMALI")
eskiz = doc.addObject("Sketcher::SketchObject", "Eskiz")
doc.recompute()
r5 = dg.dogrula(doc, ["Eskiz"])
kontrol("bos eskiz BULGU uretmiyor", r5.temiz, [str(x) for x in r5.bulgular])
_yaz("       eskiz olcumleri: %s" % r5.olcumler)

# Duzlem/origin gibi seyler de bulgu uretmemeli.
# DIKKAT: kutu BILEREK uzaga konuyor. Varsayilan yerlesim (0,0,0) bu
# belgedeki oteki kutularin TAM UZERINE denk geliyor ve cakisma taramasi
# (dogru bicimde) bunu bulgu sayiyor — testin sorusu o degil.
kutu_p = doc.addObject("Part::Box", "ParametrikKutu")
kutu_p.Placement = App.Placement(App.Vector(400, 400, 400), App.Rotation())
doc.recompute()
r6 = dg.dogrula(doc, ["ParametrikKutu"])
kontrol("parametrik kutu temiz", r6.temiz, [str(x) for x in r6.bulgular])

# -------------------------------------------------------------------- butceler
bolum("butce ve siniralar")
r7 = dg.dogrula(doc, ["Iyi", "Ters", "Kabuk"], azami_nesne=1)
kontrol("nesne siniri uygulandi", r7.bakilan == 1, r7.bakilan)
kontrol("atlanan SOYLENIYOR", any("nesne siniri" in a for a in r7.atlanan),
        r7.atlanan)

r8 = dg.dogrula(doc, ["Iyi", "Ters"], sure_butcesi=-1.0)
kontrol("sure siniri uygulandi", r8.bakilan == 0, r8.bakilan)
kontrol("sure asimi SOYLENIYOR", any("sure siniri" in a for a in r8.atlanan),
        r8.atlanan)

r9 = dg.dogrula(doc, [])
kontrol("bos listede sessiz", r9.metin() == "", repr(r9.metin()))
r10 = dg.dogrula(doc, ["OlmayanNesne"])
kontrol("olmayan nesne patlatmiyor", r10.temiz and r10.bakilan == 0,
        r10.bakilan)
r11 = dg.dogrula(None, ["Iyi"])
kontrol("belge yoksa patlatmiyor", r11.metin() == "", repr(r11.metin()))

# ------------------------------------------------------------------- izleyici
bolum("izleyici — DEGISEN nesneyi de yakaliyor mu")
ex = CodeExecutor()
ex.oturumu_ayarla("dgtest01")

s = ex.calistir('k = doc.addObject("Part::Box", "Yeni")\nk.Length = 5\n',
                "yeni kutu")
kontrol("calisti", s.basarili, s.hata_izi[-300:])
kontrol("eklenen bulundu", "Yeni" in s.eklenen, s.eklenen)
kontrol("dogrulama kostu", s.dogrulama is not None)
kontrol("dogrulama metni sonuca girdi", "dogrulama:" in s.modele_metin(),
        s.modele_metin()[:300])

# ASIL SINAV: hicbir nesne EKLEMEYEN bir tur. Eski surumde bu turda hicbir
# kontrol kosmuyordu, cunku yalnizca 'eklenen' listesine bakiliyordu.
s2 = ex.calistir('doc.getObject("Yeni").Length = 40\n', "boyut degistir")
kontrol("calisti", s2.basarili, s2.hata_izi[-300:])
kontrol("hicbir nesne EKLENMEDI", s2.eklenen == [], s2.eklenen)
_yaz("       dokunulan: %s" % s2.dokunulan)
kontrol("DEGISEN nesne yine de yakalandi", "Yeni" in s2.dokunulan,
        s2.dokunulan)
kontrol("ve kontrol edildi", s2.dogrulama is not None
        and s2.dogrulama.bakilan >= 1,
        s2.dogrulama.bakilan if s2.dogrulama else None)
kontrol("yeni olcu raporlandi",
        any("40" in o for o in (s2.dogrulama.olcumler if s2.dogrulama else [])),
        s2.dogrulama.olcumler if s2.dogrulama else [])

# Kodun KENDI icinde recompute cagirmasi izleyiciyi bozmamali
s3 = ex.calistir('k = doc.getObject("Yeni")\nk.Width = 7\ndoc.recompute()\n'
                 'k.Height = 9\n', "ara recompute")
kontrol("ara recompute'lu kod calisti", s3.basarili, s3.hata_izi[-300:])
kontrol("ara recompute izleyiciyi bozmadi", "Yeni" in s3.dokunulan,
        s3.dokunulan)

# Gozlemci SIZMAMALI — calistirma bittikten sonra kapali olmali
izl = dg.Izleyici()
izl.bagla()
kontrol("gozlemci baglandi", izl._acik is True)
izl.coz()
kontrol("gozlemci cozuldu", izl._acik is False)
izl.coz()
kontrol("iki kez cozmek patlatmiyor", izl._acik is False)

bolum("hata durumunda dogrulama kosmaz")
s4 = ex.calistir('raise RuntimeError("olsun")\n', "hatali")
kontrol("basarisiz", not s4.basarili)
kontrol("hatali turda dogrulama yok", s4.dogrulama is None)


# ==================================================== CAKISMA (MANTIK 39)
# Kullanicinin sikayeti: "bazen cakismalari anlamiyor". Olculdu
# (LOG/2026-08-26_34ac9988.txt): model UC KAREYE bakip "birbirinin icine
# girmiyor" dedi ve yanildi; ayni cakismayi olcunce buldu — 2.7 mm3.
# Goruntu bunu gosteremezdi (900x640 karede ~4 piksel/mm). O yuzden cevap
# artik OLCUMDE: cakisma_kontrol.
bolum("cakisma_kontrol — sekil turune gore DOGRU hukum")

import Part as _Part
from caddy.execution import olcum as _olcum

_V = App.Vector
_cd = App.newDocument("CakismaTest")


def _nesne(ad, sekil):
    o = _cd.addObject("Part::Feature", ad)
    o.Shape = sekil
    _cd.recompute()
    return o


def _yuzey(pts):
    return _Part.Face(_Part.makePolygon([_V(*p) for p in pts] + [_V(*pts[0])]))


_A_kati = _Part.makeBox(10, 10, 10)
_DUZLEM = _yuzey([(-10, -10, 0), (10, -10, 0), (10, 10, 0), (-10, 10, 0)])

_haller = [
    # (ad, sekil_a, sekil_b, beklenen)
    ("kati ic ice", _Part.makeBox(10, 10, 10),
     _Part.makeBox(10, 10, 10, _V(5, 0, 0)), "ICINDEN GECIYOR"),
    # DEGME KUSUR DEGIL: bu projede yelken direge bilerek deger. section()
    # burada 40 mm veriyor — yani section tek basina yaniltir, hacim yanilmaz.
    ("kati yan yana DEGEN", _Part.makeBox(10, 10, 10),
     _Part.makeBox(10, 10, 10, _V(10, 0, 0)), "degiyor"),
    ("kati uzak", _Part.makeBox(10, 10, 10),
     _Part.makeBox(10, 10, 10, _V(50, 0, 0)), "ayri"),
    # Logdaki asil vaka: KALINLIKSIZ yelken. common() hacmi 0 verir,
    # kesisme bir EGRIDIR.
    ("yuzey X gibi kesisen", _DUZLEM,
     _yuzey([(-10, 0, -10), (10, 0, -10), (10, 0, 10), (-10, 0, 10)]),
     "ICINDEN GECIYOR"),
    ("yuzey KENARI icinden gecen", _DUZLEM,
     _yuzey([(0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)]),
     "ICINDEN GECIYOR"),
    ("yuzey uc uca DEGEN", _DUZLEM,
     _yuzey([(10, -10, 0), (30, -10, 0), (30, 10, 0), (10, 10, 0)]),
     "degiyor"),
    ("kati icinden gecen yuzey", _A_kati,
     _yuzey([(-5, 5, -5), (15, 5, -5), (15, 5, 15), (-5, 5, 15)]),
     "ICINDEN GECIYOR"),
    ("katinin YUZUNE yatan yuzey", _A_kati,
     _yuzey([(0, 10, 0), (10, 10, 0), (10, 10, 10), (0, 10, 10)]),
     "degiyor"),
]

for _i, (_ad, _s1, _s2, _bek) in enumerate(_haller):
    _a = _nesne("CA%d" % _i, _s1)
    _b = _nesne("CB%d" % _i, _s2)
    _d = _olcum._cift_olc(_a, _b)
    kontrol("cakisma: %s -> %s" % (_ad, _bek), _d["hukum"] == _bek,
            "%s (hacim=%.3f alan=%.3f kesit=%.3f mesafe=%.4f)"
            % (_d["hukum"], _d["hacim"], _d.get("ortak_alan", 0),
               _d["kesit_uzunluk"], _d["mesafe"]))

# ON KABUL: section() tek basina kullanilsaydi "degen" hali de gecis
# sayilirdi. Yanlis testin dogru sonuc vermedigi burada kaniti duruyor.
# Uzakta kuruluyor: yukaridaki hal nesneleri (CA*/CB*) orijinde duruyor ve
# orada kurulan her kutu GERCEKTEN onlarin icinden gecer — tarama bunu
# dogru bicimde bulgu sayar, ama bu bolumun sorusu o degil.
_degen_a = _nesne("OnKabulA", _Part.makeBox(10, 10, 10, _V(600, 0, 0)))
_degen_b = _nesne("OnKabulB", _Part.makeBox(10, 10, 10, _V(610, 0, 0)))
_dd = _olcum._cift_olc(_degen_a, _degen_b)
kontrol("ON KABUL: degen kati ciftinde section GERCEKTEN uzunluk veriyor",
        _dd["kesit_uzunluk"] > 1.0, _dd["kesit_uzunluk"])
kontrol("...ama hukum yine de 'degiyor'", _dd["hukum"] == "degiyor",
        _dd["hukum"])

bolum("cakisma_kontrol — toplu tarama ve raporu")
_r = _olcum.cakisma_kontrol(_degen_a, _degen_b, yaz=False)
kontrol("degme raporda GECIS diye gecmiyor", not _r["gecisler"],
        _r["gecisler"])
kontrol("rapor 'ICINDEN GECEN CIFT YOK' diyor",
        "ICINDEN GECEN CIFT YOK" in _r["satir"], _r["satir"])
_gecen_a = _nesne("GecenA", _Part.makeBox(20, 20, 20, _V(200, 200, 0)))
_gecen_b = _nesne("GecenB", _Part.makeBox(20, 20, 20, _V(210, 200, 0)))
_r2 = _olcum.cakisma_kontrol(_gecen_a, _gecen_b, yaz=False)
kontrol("gecis yakalandi", len(_r2["gecisler"]) == 1, _r2["satir"])
kontrol("gecis satirinda HACIM yaziyor",
        "mm3" in _r2["satir"], _r2["satir"])
kontrol("tek nesneyle cagirinca uyariyor",
        "en az iki nesne"
        in _olcum.cakisma_kontrol(_gecen_a, yaz=False).get("satir", ""),
        _olcum.cakisma_kontrol(_gecen_a, yaz=False).get("satir", ""))

# BOOLEAN GIRDISI YANLIS ALARM URETMEMELI. Part::Cut'in Base/Tool nesneleri
# belgede durur ve sonucla tamamen ust uste biner (olculdu:
# Kesilmis.OutList = [A, B]). Bunu kusur diye raporlamak MANTIK 32'deki
# tekrarlanan yanlis alarmin aynisi olurdu.
_bk_a = _cd.addObject("Part::Box", "BoolA")
_bk_b = _cd.addObject("Part::Box", "BoolB")
_bk_a.Placement = App.Placement(App.Vector(500, 0, 0), App.Rotation())
_bk_b.Placement = App.Placement(App.Vector(505, 0, 0), App.Rotation())
_kes = _cd.addObject("Part::Cut", "Kesilmis")
_kes.Base, _kes.Tool = _bk_a, _bk_b
_cd.recompute()
kontrol("ON KABUL: boolean girdisi sonucla GERCEKTEN ust uste",
        _olcum._bbox_kesisiyor_mu(_kes, _bk_a))
kontrol("akrabalik goruluyor", dg._akraba_mi(_kes, _bk_a))
_rap_bool = dg.dogrula(_cd, ["Kesilmis"])
kontrol("boolean girdisi cakisma BULGUSU uretmiyor",
        not any("icinden geciyor" in str(b) for b in _rap_bool.bulgular),
        [str(b) for b in _rap_bool.bulgular])

# BBOX ON ELEMESI: uzak ciftler boolean'a hic girmemeli, yoksa 52 nesnelik
# bir belgede 1326 cift OCC cagrisi demek (olculdu: 0.33 sn).
_uzak = _nesne("Uzak", _Part.makeBox(10, 10, 10, _V(900, 900, 900)))
kontrol("bbox on elemesi uzak cifti eliyor",
        not _olcum._bbox_kesisiyor_mu(_gecen_a, _uzak))
kontrol("bbox on elemesi kesisen cifti ELEMIYOR",
        _olcum._bbox_kesisiyor_mu(_gecen_a, _gecen_b))

bolum("dogrulama otomatik cakisma taramasi — host soyluyor")
# Model sormayi unutsa bile host olcup raporluyor: modelin kacirdigi tek
# kusur turu buydu.
_rap = dg.dogrula(_cd, ["GecenA"])
kontrol("cakisma kontrolu KOSAN listesinde",
        any("cakisma" in k for k in _rap.kosan), _rap.kosan)
kontrol("gecis BULGU olarak raporlandi",
        any("icinden geciyor" in str(b) for b in _rap.bulgular),
        [str(b) for b in _rap.bulgular])
kontrol("bulguda karsi nesnenin adi var",
        any("GecenB" in str(b) for b in _rap.bulgular),
        [str(b) for b in _rap.bulgular])

# DEGME bulgu DEGIL — MANTIK 32'deki 31 kez tekrarlanan yanlis alarma
# donmemek icin kullanicinin verdigi karar.
_rap2 = dg.dogrula(_cd, ["OnKabulA"])
kontrol("DEGME bulgu sayilmiyor",
        not any("icinden geciyor" in str(b) for b in _rap2.bulgular),
        [str(b) for b in _rap2.bulgular])

# TEKRAR EDEN BULGU TEK SATIRDA TOPLANIYOR (MANTIK 32/33.4: ayni satirin 31
# kez tekrarlanmasi hem ciktiyi hem baglami doldurmustu). Orijinde ust uste
# duran hal nesneleri bunu dogal olarak uretiyor.
_yigin = _cd.addObject("Part::Box", "Yigin")
_yigin.Length = _yigin.Width = _yigin.Height = 30
_cd.recompute()
_rap3 = dg.dogrula(_cd, ["Yigin"])
_gecis_satirlari = [str(b) for b in _rap3.bulgular if "icinden geciyor" in str(b)]
_yaz("       yiginda bulgu satiri: %d" % len(_gecis_satirlari))
kontrol("cok sayida gecis tek satirda TOPLANIYOR",
        len(_gecis_satirlari) <= dg.CAKISMA_AZAMI_SATIR + 1,
        _gecis_satirlari)
kontrol("toplama satiri kac cift oldugunu SOYLUYOR",
        any("cift" in s for s in _gecis_satirlari), _gecis_satirlari)

# Hiz: kullanicinin sarti "yavaslatmiyorsa ekleyelim".
import time as _time

_t0 = _time.time()
dg.dogrula(_cd, ["GecenA"])
_sure = _time.time() - _t0
_yaz("       cakisma taramasi dahil dogrulama: %.3f sn (%d nesnelik belge)"
     % (_sure, len(_cd.Objects)))
kontrol("tarama turu yavaslatmiyor (< 0.3 sn)", _sure < 0.3, _sure)

bolum("katman kurali — dogrulama.py Qt gormemeli")
_kaynak = os.path.join(KOK, "caddy", "execution", "dogrulama.py")
with open(_kaynak, encoding="utf-8") as f:
    _satirlar = [x.strip() for x in f
                 if x.strip().startswith(("import ", "from "))]
kontrol("Qt/PySide import yok",
        not any("PySide" in x or "Qt" in x for x in _satirlar), _satirlar)

# ======================================================================
bolum("tuketilmis nesne — kesme tabani bulgu degildir")
# OLCULDU (LOG/2026-08-27_9564dc71.txt): cakisma raporundaki 813 bulgu
# satirinin 627'si (%77) boyle nesnelerdi. Kesme tabani sonucuyla elbette
# cakisir; bunu kusur diye raporlamak MANTIK 32'deki yanlis alarmi geri
# getiriyordu.
from caddy.execution import kesif as _ks
from caddy.execution import olcum as _ol

_td = App.newDocument("TuketilmisNS")
_dis = _td.addObject("Part::Box", "Dis")
_dis.Length = _dis.Width = _dis.Height = 20
_ic = _td.addObject("Part::Box", "Ic")
_ic.Length = _ic.Width = _ic.Height = 10
_ic.Placement.Base = App.Vector(5, 5, 5)
_kesim = _td.addObject("Part::Cut", "Kesim")
_kesim.Base = _dis
_kesim.Tool = _ic
_td.recompute()
# FreeCAD kesme tabanlarini gizler; emin olmak icin biz de kapatiyoruz
# (baska surumde varsayilan degisebilir, test surume bagli kalmasin).
_dis.Visibility = False
_ic.Visibility = False

kontrol("kesme tabani tuketilmis sayiliyor", _ks.tuketilmis_mi(_dis))
kontrol("kesme takimi tuketilmis sayiliyor", _ks.tuketilmis_mi(_ic))
kontrol("sonuc nesnesi tuketilmis DEGIL", not _ks.tuketilmis_mi(_kesim))

# GORUNUR bir ayna kaynagi tuketilmis DEGILDIR. Ilk uygulama yalnizca
# "baskasi bana referans veriyor mu" diye bakiyordu ve gercek belgede
# `KapiKolu`yu elemisti — o bir Mirroring kaynagi ama ekranda duruyor.
_kol = _td.addObject("Part::Box", "Kol")
_kol.Length = 4; _kol.Width = 2; _kol.Height = 2
_kol.Placement.Base = App.Vector(0, 30, 0)
_ayna = _td.addObject("Part::Mirroring", "KolAyna")
_ayna.Source = _kol
_ayna.Normal = App.Vector(0, 1, 0)
_td.recompute()
kontrol("GORUNUR ayna kaynagi tuketilmis DEGIL",
        not _ks.tuketilmis_mi(_kol), _kol.Visibility)
_kol.Visibility = False
kontrol("GIZLENMIS ayna kaynagi tuketilmis sayiliyor",
        _ks.tuketilmis_mi(_kol))
_kol.Visibility = True

# Yalniz duran, kimsenin hammaddesi olmayan gizli parca da elenmemeli:
# kullanici gecici olarak gizlemis olabilir.
_yalniz = _td.addObject("Part::Box", "Yalniz")
_yalniz.Visibility = False
_td.recompute()
kontrol("gizli ama kimsenin hammaddesi degil -> elenmez",
        not _ks.tuketilmis_mi(_yalniz))

bolum("cakisma_kontrol — eleme ve odak")
_td.recompute()
App.setActiveDocument(_td.Name)
_s = _ol.cakisma_kontrol(yaz=False)
_adlar = " ".join(d["satir"] for d in _s["gecisler"])
kontrol("argumansiz taramada kesme tabani GECMIYOR",
        "Dis" not in _adlar and "Ic x" not in _adlar, _adlar)
kontrol("basligi kac nesnenin elendigini SOYLUYOR",
        "listeye alinmadi" in _s["satir"], _s["satir"].splitlines()[0])

# ACIKCA sorulan cift elenmez: model neyi sorduysa cevabini alir.
_s2 = _ol.cakisma_kontrol(_kesim, _dis, yaz=False)
kontrol("acik liste verilince eleme YOK", _s2["bakilan_cift"] == 1,
        _s2["bakilan_cift"])
kontrol("acik listede tuketilmis cift de olculuyor",
        len(_s2["gecisler"]) == 1, _s2["satir"])

# ODAK: cift sayisi n(n-1)/2 degil n-1 olmali.
_c1 = _td.addObject("Part::Box", "C1")
_c2 = _td.addObject("Part::Box", "C2")
_c2.Placement.Base = App.Vector(100, 0, 0)
_c3 = _td.addObject("Part::Box", "C3")
_c3.Placement.Base = App.Vector(200, 0, 0)
_td.recompute()
_tam = _ol.cakisma_kontrol(yaz=False)
_odakli = _ol.cakisma_kontrol(odak=_kesim, yaz=False)
_yaz("       tam tarama %d cift | odakli %d cift"
     % (_tam["toplam_cift"], _odakli["toplam_cift"]))
kontrol("odak cift sayisini dusuruyor",
        _odakli["toplam_cift"] < _tam["toplam_cift"],
        (_tam["toplam_cift"], _odakli["toplam_cift"]))
kontrol("odakli ciftlerin HEPSI odagi iceriyor",
        all("Kesim" in d["satir"] for d in _odakli["ciftler"]),
        [d["satir"] for d in _odakli["ciftler"]])
kontrol("baslikta odagin adi geciyor", "odak Kesim" in _odakli["satir"],
        _odakli["satir"].splitlines()[0])

# Odak nesnesinin KENDISI tuketilmis olsa bile elenmez — sorulan odur.
_od = _ol.cakisma_kontrol(odak=_dis, yaz=False)
kontrol("tuketilmis nesne ODAK olarak sorulursa olculuyor",
        _od["toplam_cift"] > 0, _od["satir"].splitlines()[0])

bolum("otomatik tarama tuketilmisi bulgu saymiyor")
# Part::Cut yapan bir tur UC nesneye birden dokunur: sonuc, taban, takim.
# Taban sonucun "icinden geciyor" gorunur; bu bulgu degildir.
_rp = dg.dogrula(_td, ["Kesim", "Dis", "Ic"])
_bulgu = " ".join(str(b) for b in (getattr(_rp, "bulgular", []) or []))
kontrol("kesme tabani Dis bulgu olarak raporlanmiyor",
        "'Dis'" not in _bulgu and "(Dis ile)" not in _bulgu, _bulgu[:300])
kontrol("kesme takimi Ic bulgu olarak raporlanmiyor",
        "'Ic'" not in _bulgu and "(Ic ile)" not in _bulgu, _bulgu[:300])
kontrol("kosan satiri elemeyi soyluyor",
        any("kesme tabani" in s for s in _rp.kosan),
        [s for s in _rp.kosan if "cakisma" in s])


# ==========================================================================
# SAGLIK ve SIMETRI (PLAN S8 — B grubu)
# ==========================================================================
# Kisa tutuldu: kullanicinin sozu "testleri yap ama cok da yapma, elle test
# edecegim". Burada yalnizca SAYIYLA kanitlanabilen cekirdek var.

bolum("saglik — on kabul: isValid tek basina yetmiyor")
# Bu dosyanin basligindaki olcumun ta kendisi. `saglik` yalnizca isValid'e
# dayansaydi degersiz olurdu; once onun yetmedigini gosteriyoruz.
_sd = App.newDocument("SaglikNS")
_kabuk = Part.Shell(Part.makeBox(10, 10, 10).Faces[:5])   # bir yuzu eksik
kontrol("ON KABUL: acik kabuk isValid()'i GECIYOR", _kabuk.isValid(),
        (_kabuk.isValid(), len(_kabuk.Faces)))

_ak = _sd.addObject("Part::Feature", "AcikKabuk")
_ak.Shape = _kabuk
_sag = _sd.addObject("Part::Box", "Saglam")
_sag.Length, _sag.Width, _sag.Height = 40, 20, 10
_sd.recompute()

_r = _ol.saglik(_ak, yaz=False)
kontrol("saglik acik kabugu KUSUR sayiyor ('KATI YOK')",
        len(_r["kusurlu"]) == 1 and "KATI YOK" in _r["satir"], _r["satir"])
_r = _ol.saglik(_sag, yaz=False)
kontrol("saglam kutu temiz",
        not _r["kusurlu"] and "KUSUR YOK" in _r["satir"], _r["satir"])

bolum("saglik — birden cok kati KUSUR degil, BILGI")
# Model gunlukte `len(Solids) != 1` yaziyordu; oldugu gibi kusur saysaydik
# bilesik sekillerde yanlis alarm uretirdik.
_bl = _sd.addObject("Part::Feature", "IkiKati")
_bl.Shape = Part.makeCompound([Part.makeBox(5, 5, 5),
                               Part.makeBox(5, 5, 5, App.Vector(20, 0, 0))])
_sd.recompute()
_r = _ol.saglik(_bl, yaz=False)
kontrol("iki katili sekil kusurlu DEGIL ama '2 ayri kati' deniyor",
        not _r["kusurlu"] and "2 ayri kati" in _r["satir"], _r["satir"])

bolum("saglik — argumansiz cagri tum belgeyi tariyor")
_r = _ol.saglik(yaz=False)
_adlar = [k["ad"] for k in _r["nesneler"]]
kontrol("belgedeki nesneler taraniyor",
        "Saglam" in _adlar and "AcikKabuk" in _adlar, _adlar)
kontrol("acik kabuk yine kusurlu",
        any(k["ad"] == "AcikKabuk" for k in _r["kusurlu"]), _r["satir"])

bolum("saglik — YUZU OLMAYAN SEKIL kusur degil (LOG/2026-08-31_ed2bc86b)")
# Uretimde cikan gurultu: `KUSUR Origin001: KATI YOK`. O nesne bir datum
# NOKTASIYDI (App::Point, Shape=Vertex) — katisi olmamasi normal. Yuzu
# olmayan sekle kati testi uygulamak kategori hatasi, ve kusur raporunu
# gurultuyle doldurmak gercek kusurlari degersizlestirir (§32).
import Part as _Part                                             # noqa: E402

_nk = _sd.addObject("Part::Feature", "TelNokta")
_nk.Shape = _Part.Vertex(_Part.Point(App.Vector(0, 0, 0)))
_sd.recompute()
kontrol("ON KABUL: nokta seklinin YUZU ve KATISI yok",
        len(_nk.Shape.Faces) == 0 and len(_nk.Shape.Solids) == 0)
_r = _ol.saglik(_nk, yaz=False)
kontrol("yuzu olmayan sekil KUSUR sayilmiyor", not _r["kusurlu"], _r["satir"])
kontrol("neden bakilmadigi SOYLENIYOR (sessizce atlanmiyor)",
        "kati testleri uygulanmadi" in _r["satir"], _r["satir"])
_r = _ol.saglik(yaz=False)
kontrol("iskele elenirken GERCEK is elenmiyor",
        "Saglam" in [k["ad"] for k in _r["nesneler"]])
_sd.removeObject("TelNokta")
_sd.recompute()

# Kesif tarafi: datum tipleri hic listeye girmemeli. Gercek App::Point
# nesnesi bassiz ortamda uretilemiyor, tip suzgeci ise yalnizca TypeId'ye
# bakiyor — sinanan sey tam olarak o suzgec.
from caddy.execution import kesif as _kesif                      # noqa: E402


class _SahteTip:
    def __init__(self, t):
        self.TypeId = t


for _t in ("App::Point", "App::Plane", "App::Line", "App::Origin"):
    kontrol("kesif '%s' tipini eliyor" % _t,
            _kesif._atlanir_mi(_SahteTip(_t)))
kontrol("kesif gercek parcayi ELEMIYOR",
        not _kesif._atlanir_mi(_SahteTip("Part::Box")))

bolum("saglik — mesh AYRI testlerden geciyor")
import Mesh as _Mesh
_kose, _uc = Part.makeBox(10, 10, 10).tessellate(0.5)
_km = _sd.addObject("Mesh::Feature", "KapaliMesh")
_km.Mesh = _Mesh.Mesh([[_kose[i] for i in u] for u in _uc])
_delik = _Mesh.Mesh(_km.Mesh)
_delik.removeFacets([0])                      # bir ucgen eksik -> acik
_dm = _sd.addObject("Mesh::Feature", "DelikMesh")
_dm.Mesh = _delik
_sd.recompute()
kontrol("kapali mesh temiz", not _ol.saglik(_km, yaz=False)["kusurlu"])
_r = _ol.saglik(_dm, yaz=False)
kontrol("delikli mesh 'KAPALI KATI DEGIL' diyor",
        len(_r["kusurlu"]) == 1 and "KAPALI KATI DEGIL" in _r["satir"],
        _r["satir"])

bolum("simetri — bilinen cevapli kati")
# ELLE HESAP: kutudan TEK tarafta 6x6x6 ceb kesiliyor.
#   ceb 216 mm3, govde 8000-216 = 7784
#   simetrik fark = 216 (fazlalik) + 216 (eksiklik) = 432
#   oran = 432 / 7784 = %5.55
_as = _sd.addObject("Part::Feature", "Asim")
_as.Shape = Part.makeBox(40, 20, 10).cut(
    Part.makeBox(6, 6, 6, App.Vector(30, 7, 4)))
_sd.recompute()
_r = _ol.simetri(_as, "x", yaz=False)
_x = _r["eksenler"]["x"]
kontrol("x ekseninde ASIMETRIK", _x["hukum"] == "ASIMETRIK", _r["satir"])
kontrol("ayna duzlemi bbox ortasi (x=20)", abs(_x["merkez"] - 20.0) < 1e-9,
        _x["merkez"])
kontrol("fark hacmi ELLE HESAPLA ayni (432 mm3)",
        abs(_x["fark"] - 432.0) < 1.0, _x["fark"])
kontrol("fark BOLGESI asimetrinin gercek yerini gosteriyor (x 30..36)",
        "fark bolgesi" in _r["satir"]
        and any(abs(b.XMax - 36.0) < 0.5 for b in _x["kutular"]),
        [(b.XMin, b.XMax) for b in _x["kutular"]])

bolum("simetri — gercekten simetrik olan temiz cikiyor")
_sm = _sd.addObject("Part::Feature", "Sim")
_sm.Shape = Part.makeBox(40, 20, 10).cut(
    Part.makeBox(6, 6, 6, App.Vector(30, 7, 2))).cut(
    Part.makeBox(6, 6, 6, App.Vector(4, 7, 2)))
_sd.recompute()
kontrol("iki taraftan esit kesilen parca x'te simetrik",
        _ol.simetri(_sm, "x", yaz=False)["eksenler"]["x"]["hukum"]
        == "simetrik")

bolum("simetri — eksen verilmezse UCU birden, mesh nokta bulutuyla")
_r = _ol.simetri(_as, yaz=False)
kontrol("uc eksen de olculdu ve y simetrik cikti",
        set(_r["eksenler"]) == {"x", "y", "z"}
        and _r["eksenler"]["y"]["hukum"] == "simetrik", _r["satir"])
_mx = _ol.simetri(_km, "x", yaz=False)["eksenler"]["x"]
kontrol("mesh'te nokta yontemi kullanildi ve kup simetrik",
        _mx.get("yontem") == "nokta" and _mx["hukum"] == "simetrik", _mx)

# --------------------------------------------------------------------------
bolum("cakisma — blogun kendi ciktisi ile tarama TEKRARLANMIYOR")
# OLCULDU (LOG/2026-08-31_f5a6a5ac.txt): model her parcadan sonra
# `cakisma_kontrol(odak=...)` cagiriyordu; ARDINDAN tarama ayni ciftleri
# BULGU olarak bir daha yaziyordu. Tek blokta ~950 karakter, 52 blogun
# cogunda, ve baglam 788k'ya cikmisti. Ustelik ayni bulguyu iki cumleyle
# okuyan model onu iki AYRI sorun sanabiliyor.
_dd = App.newDocument("CakismaTekrar")
_da = _dd.addObject("Part::Box", "TekA")
_db = _dd.addObject("Part::Box", "TekB")
_db.Placement.Base.x = 5.0
_dd.recompute()

# 1) Kayit BOSKEN tarama bulguyu yazar — bastirma varsayilan degil.
_ol.bildirilen_gecisleri_sifirla()
_t1 = dg.dogrula(_dd, ["TekA"])
kontrol("kayit bosken gecis BULGU olarak yaziliyor",
        any("icinden geciyor" in str(b) for b in _t1.bulgular),
        [str(b) for b in _t1.bulgular])

# 2) `yaz=True` cagrisi cifti kaydeder; ayni tarama artik tekrarlamaz.
_ol.bildirilen_gecisleri_sifirla()
_ol.cakisma_kontrol(_da, _db)                      # yaz=True: modele gitti
kontrol("yazdirilan cift kayda girdi",
        _ol.gecis_bildirildi_mi("TekA", "TekB"))
kontrol("sira onemsiz — anahtar sirali",
        _ol.gecis_bildirildi_mi("TekB", "TekA"))
_t2 = dg.dogrula(_dd, ["TekA"])
kontrol("bildirilen gecis BULGU olarak tekrarlanmiyor",
        not any("icinden geciyor" in str(b) for b in _t2.bulgular),
        [str(b) for b in _t2.bulgular])
# DURUSTLUK: bastirilan sey sessiz kalmaz, yoksa model "tarama temiz cikti"
# sanar. Bu, projedeki "olcemedigini soyle" kuralinin aynisi.
kontrol("bastirma olcum satirinda soyleniyor",
        any("zaten yazili" in o for o in _t2.olcumler), _t2.olcumler)
kontrol("yanlis 'icinden gecen yok' hukmu verilmiyor",
        not any("icinden gecen yok" in o for o in _t2.olcumler), _t2.olcumler)

# 3) `yaz=False` KAYDETMEZ. O cagri hicbir sey yazdirmaz (gorsel yolu onu
#    boyle kullaniyor); bastirilirsa bulgu gercekten kaybolurdu.
_ol.bildirilen_gecisleri_sifirla()
_ol.cakisma_kontrol(_da, _db, yaz=False)
kontrol("yaz=False cifti kaydetmiyor",
        not _ol.gecis_bildirildi_mi("TekA", "TekB"))
_t3 = dg.dogrula(_dd, ["TekA"])
kontrol("yaz=False sonrasi bulgu duruyor",
        any("icinden geciyor" in str(b) for b in _t3.bulgular),
        [str(b) for b in _t3.bulgular])

# 4) BASKA bir cift bastirilmaz: kayit ciftin kendisine bagli, genel bir
#    "cakisma susturma" degil.
_dc = _dd.addObject("Part::Box", "TekC")
_dc.Placement.Base.y = 5.0
_dd.recompute()
_ol.bildirilen_gecisleri_sifirla()
_ol.cakisma_kontrol(_da, _db)
_t4 = dg.dogrula(_dd, ["TekC"])
kontrol("kaydedilmemis cift hala bulgu",
        any("TekC" in str(b) for b in _t4.bulgular),
        [str(b) for b in _t4.bulgular])
_ol.bildirilen_gecisleri_sifirla()
App.closeDocument(_dd.Name)

# ---------------------------------------------------------------------------
bolum("grup PARCA DEGILDIR — cocugunun cakismasini tekrarlamaz")
# OLCULDU (LOG/2026-09-04_92416f9e.txt, satir 2912-2914): `REF_Cihaz` bir
# App::DocumentObjectGroup'tu ve FreeCAD ona cocuklarinin BILESIGINI `.Shape`
# olarak veriyor. Uc BULGU satirinin ikisi yankiydi. Sentetik olcum: bulgu
# 2 -> 1, olcum satiri 4 -> 3, bakilan nesne 4 -> 3.
_gd = App.newDocument("GrupYanki")
_gg = _gd.addObject("App::DocumentObjectGroup", "GRUP")
_gp = _gd.addObject("Part::Box", "Panel")
_gp.Length, _gp.Width, _gp.Height = 480.0, 5.0, 126.0
_gp.Placement.Base = App.Vector(-22.5, -5.0, 0.0)
_gg.addObject(_gp)
_gw = _gd.addObject("Part::Box", "Duvar")
_gw.Length, _gw.Width, _gw.Height = 4.0, 50.0, 126.0
_gw.Placement.Base = App.Vector(-4.0, -5.0, 0.0)
_gd.recompute()

# On kabul: grubun GERCEKTEN sekli var ve cocugunun bilesigi. Bu dogru
# degilse asagidaki testler bosuna kosar.
kontrol("on kabul: grubun Shape'i var",
        _ol._sekil_al(_gg) is not None)
kontrol("on kabul: grup hacmi = cocugunun hacmi",
        abs(_gg.Shape.Volume - _gp.Shape.Volume) < 1e-6,
        (_gg.Shape.Volume, _gp.Shape.Volume))

_ol.bildirilen_gecisleri_sifirla()
_gr = dg.dogrula(_gd, ["GRUP", "Panel", "Duvar"])
_gb = [str(b) for b in _gr.bulgular]
kontrol("cakisma bulgusu TEK", len(_gb) == 1, _gb)
kontrol("bulgu cocugun adiyla", any("Panel" in b for b in _gb), _gb)
kontrol("grup adiyla bulgu YOK", not any("GRUP" in b for b in _gb), _gb)
kontrol("grup olcum satirinda da yok",
        not any(m.startswith("GRUP:") for m in _gr.olcumler), _gr.olcumler)
kontrol("cocuk olcum satirinda var",
        any(m.startswith("Panel:") for m in _gr.olcumler), _gr.olcumler)
kontrol("grup nesne kotasindan slot yemiyor", _gr.bakilan == 2, _gr.bakilan)

# Grup ELENIRKEN cocuklar elenmiyor: kapsam daralmadi.
kontrol("Duvar hala olculuyor",
        any(m.startswith("Duvar:") for m in _gr.olcumler), _gr.olcumler)

# App::Part de ayni sinifta (kesif._ATLANAN).
kontrol("App::Part de eleniyor",
        _ks._atlanir_mi(_gd.addObject("App::Part", "Kap")))
App.closeDocument(_gd.Name)

App.closeDocument(_sd.Name)
_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d" % (gecti, basarisiz))
_yaz("=" * 70)
