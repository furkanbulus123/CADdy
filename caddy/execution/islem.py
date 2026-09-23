"""FreeCAD'in HAZIR yeteneklerini modele tek cagri olarak acan yardimcilar.

NEDEN VAR. Model, FreeCAD'de tek cagri olan isleri elle yaziyordu ve bunu
yaparken modeli bozuyordu. Gunlukte olculdu (LOG/2026-08-20_baa70fa4.txt):
flood-fill ile parca ayirma, sinir dongusu orerek delik kapatma, BFS ile
normal duzeltme — uc tur ust uste denendi, her seferinde govdede GERCEK
DELIK acildi ve kullanici geri almak zorunda kaldi. Ayni isi yapan hazir
zincir sekiz satir ve 0.024 saniye.

HIZ. Bu modul turlari yavaslatmiyor, HIZLANDIRIYOR. Gecikmeyi belirleyen
sey uretilen token: gunlugun en yavas turlari (149.6 sn, 118.5 sn) tam
olarak modelin 45-50 satir elle geometri yazdigi turlar. `mesh_onar()`
yazmak bir buyukluk mertebesi hizli.

ORTAK KURAL: YARDIMCI KENDI ETKISINI DOGRULAR.
`PartDesign::PolarPattern` olculurken cikan ders: primitif uzerinde hata
VERMIYOR, State "Up-to-date" diyor, hacim degismiyor — sessizce tek kopya
birakiyor. Model "6 delik actim" der, belgede bir delik vardir. O yuzden
buradaki her yardimci isini yaptiktan sonra sonucu OLCER ve bekledigini
bulamazsa acikca soyler. Olcum katmanindaki "YUVARLAK DEGIL" kalibinin
aynisi.

Hepsi print ediyor: cikti otomatik olarak modele donuyor.
Hicbiri istisna sizdirmiyor.

KATMAN KURALI (MANTIK 12): burada Qt YOK.
"""

from __future__ import annotations

import math
import os
import time

import FreeCAD as App

from . import olcum

# 3B baski malzemelerinin yogunluklari (g/cm3).
YOGUNLUK = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07,
    "TPU": 1.21, "NAYLON": 1.14, "PA": 1.14, "RECINE": 1.15,
    "PC": 1.20, "PP": 0.90,
}

# Mesh'ten katiya cevirmede ust sinir. Uzerinde her ucgen bir YUZ oluyor:
# olculdu, 8000 facet -> 8000 yuzlu kati, 4.64 sn. Boyle bir katida her
# boolean aci verici sekilde yavas.
AZAMI_FACET = 4000


def _hedef(nesne):
    return olcum._hedef(nesne)


def _mesh_al(nesne):
    return olcum._mesh_al(nesne)


def _sekil_al(nesne):
    return olcum._sekil_al(nesne)


def _sayi(x) -> str:
    return olcum._sayi(x)


def _mesh_durumu(m) -> dict:
    d = {}
    for ad, cagri in (("kapali", lambda: bool(m.isSolid())),
                      ("facet", lambda: int(m.CountFacets)),
                      ("parca", lambda: int(m.countComponents())),
                      ("kesisme", lambda: bool(m.hasSelfIntersections())),
                      ("manifold_disi", lambda: bool(m.hasNonManifolds()))):
        try:
            d[ad] = cagri()
        except Exception:
            d[ad] = None
    return d


def _mesh_kati(m, azami_facet: int = AZAMI_FACET):
    """Mesh -> Part katisi. BELGEYE NESNE EKLEMEZ. (kati, son_facet) doner.

    Hem `kati_yap` hem `birlestir`in mesh yolu bunu kullaniyor — donusumun
    tek bir yerde durmasi, iki yolun sessizce ayrisamamasi demek.

    Facet siniri KRITIK, olculdu (silindir+torus, katiya cevir + fuse +
    mesh'e geri don):
        2 172 facet ->  2.9 sn   kapali, kesismesiz, 1 parca
        3 784 facet ->  7.4 sn   kapali, kesismesiz, 1 parca
       32 756 facet -> 59.2 sn   gecerli kati AMA mesh'te KESISME var
    Yani sinir yalnizca hiz icin degil, SONUCUN TEMIZLIGI icin de var.
    """
    import Part

    calisilan = m
    facet = int(m.CountFacets)
    if facet > azami_facet:
        try:
            calisilan = m.copy()
            calisilan.decimate(0.01, 1.0 - (azami_facet / float(facet)))
        except Exception:
            calisilan = m

    s = Part.Shape()
    s.makeShapeFromMesh(calisilan.Topology, 0.1)
    return Part.makeSolid(s), int(calisilan.CountFacets)


def _kati_baski_gercegi(sekil, sapma: float = 0.1):
    """KATI bir sonucun BASKI gercegi. (durum, sure_sn) doner; olmazsa None.

    NEDEN BURADA. `dogrulama` kendiyle kesisme kontrolunu KATI (BRep)
    nesnelerde KOSMUYOR — OCC'de pahali ve her calistirmada her nesne icin
    odenirdi. Ama `birlestir` zaten saniyeler suren bir islem, ve kesisme
    uretmeye en yatkin yer tam da orasi.

    OLCULEN KAYIP (LOG/2026-08-24_3ad4cef1.txt, 12:08 -> 12:09): birlestir
    "hacim=5.551e+04 mm3, 1 kati" dedi, dogrulama "kati=1" dedi, sekil
    isValid() True idi. AYNI sekil 0.05 mm'de mesh'lenince kapali degil +
    kendini kesen + non-manifold cikti. Yani 108 saniyelik islem yanlis bir
    guven verdi ve hata ancak disa aktarma aninda, isin sonunda ortaya cikti.
    `isValid()` ve `Solids == 1` baskiya hazir demek DEGILDIR.

    MALIYET OLCULDU — kontrol (mesh'leme + uc soru) / islemin kendisi:
        iki kutu           0.047 sn / connect 0.285 sn
        silindir + kure    0.064 sn / connect 0.059 sn
        mesh kokenli kati  0.929 sn / fuse    1.802 sn
    En kotu durumda ~1 sn, ve riskin en yuksek oldugu mesh kokenli yolda
    islemin kucuk bir yuzdesi. Bu yuzden kosulsuz kosuyor.
    """
    import time

    import MeshPart

    t0 = time.time()
    try:
        m = MeshPart.meshFromShape(Shape=sekil, LinearDeflection=sapma,
                                   AngularDeflection=0.4)
        return _mesh_durumu(m), time.time() - t0
    except Exception:                                            # noqa: BLE001
        return None, time.time() - t0


def _baski_verdikti(d: dict) -> list:
    """Baski acisindan neyin bozuk oldugu. Bos liste = temiz."""
    sorun = []
    if d.get("kapali") is False:
        sorun.append("kapali degil (su sizdirmaz degil)")
    if d.get("kesisme"):
        sorun.append("kendiyle kesisme var — isValid() bunu YAKALAMAZ")
    if d.get("manifold_disi"):
        sorun.append("non-manifold")
    if d.get("parca") not in (None, 1):
        sorun.append(f"{d['parca']} ayri parca")
    return sorun


def _durum_metni(d: dict) -> str:
    p = [("kapali" if d.get("kapali") else "ACIK"),
         f"facet={d.get('facet')}"]
    if d.get("parca") not in (None, 1):
        p.append(f"parca={d['parca']}")
    if d.get("kesisme"):
        p.append("KESISME")
    if d.get("manifold_disi"):
        p.append("MANIFOLD-DISI")
    return " ".join(p)


# ==========================================================================
# TUR 1 — indirilen mesh'i calisilabilir hale getir
# ==========================================================================

def mesh_onar(nesne=None, yaz: bool = True) -> dict:
    """Mesh'i FreeCAD'in kendi onarim zinciriyle duzeltir.

    ZINCIR (sirasi onemli): tekrarlanan noktalar -> indeksler -> dejenere
    ucgenler -> kendiyle kesisme -> non-manifold -> delikler -> normaller.

    Bu, elle yazilan "flood-fill + sinir dongusu orme" denemelerinin
    yerini alir. Olculdu: delikli bir mesh'te isSolid False -> True,
    0.024 sn.

    Zaten temiz bir mesh'e DOKUNMAZ: gereksiz yere facet degistirmek
    kullanicinin modelini sebepsiz bozmaktir.
    """
    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("mesh_onar: bu bir mesh nesnesi degil "
                  "(kati icin Shape.fix/removeSplitter'a bak)")
        return {}

    ad = getattr(nesne, "Name", "?")
    once = _mesh_durumu(m)
    if (once.get("kapali") and not once.get("kesisme")
            and not once.get("manifold_disi")):
        if yaz:
            print(f"{ad}: zaten temiz ({_durum_metni(once)}) — dokunulmadi")
        return {"degisti": False, "once": once, "sonra": once}

    t0 = time.time()
    yeni = m.copy()
    adimlar = []
    for adim, cagri in (
            ("tekrar eden noktalar", lambda: yeni.removeDuplicatedPoints()),
            ("indeksler", lambda: yeni.fixIndices()),
            ("dejenere ucgenler", lambda: yeni.fixDegenerations(0.001)),
            ("kendiyle kesisme", lambda: yeni.fixSelfIntersections()),
            ("non-manifold", lambda: yeni.removeNonManifolds()),
            ("delikler", lambda: yeni.fillupHoles(1000, 0)),
            ("normaller", lambda: yeni.harmonizeNormals())):
        try:
            cagri()
        except Exception as e:                                   # noqa: BLE001
            adimlar.append(f"{adim}(atlandi: {e})")

    try:
        nesne.Mesh = yeni
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"mesh_onar: sonuc yazilamadi ({e})")
        return {}

    sonra = _mesh_durumu(yeni)
    d = {"degisti": True, "once": once, "sonra": sonra,
         "sure": time.time() - t0}
    if yaz:
        print(f"{ad} onarildi ({d['sure']:.2f} sn): "
              f"{_durum_metni(once)}  ->  {_durum_metni(sonra)}")
        for a in adimlar:
            print(f"    {a}")
        # DURUSTLUK: zincir her seyi duzeltemez. Duzelmedigini soylemek,
        # "onardim" deyip birakmaktan iyidir.
        kalan = []
        if not sonra.get("kapali"):
            kalan.append("hala ACIK (delik cok buyuk olabilir)")
        if sonra.get("kesisme"):
            kalan.append("hala kendiyle kesisiyor")
        if sonra.get("manifold_disi"):
            kalan.append("hala non-manifold")
        if kalan:
            print("    KALAN SORUN: " + ", ".join(kalan))
    return d


def kati_yap(nesne=None, azami_facet: int = AZAMI_FACET, yaz: bool = True):
    """Mesh'i KATIYA cevirir — parametrik araclarin kapisi.

    NEDEN GEREKLI: ice aktarilan (STL/OBJ/3MF) her sey mesh. Mesh'te fillet yok,
    pocket yok, boolean zor. Katiya cevirince FreeCAD'in tum Part/PartDesign
    araclari acilir.

    IKI DURUSTLUK KURALI:
      * Mesh KAPALI DEGILSE reddeder. Acik bir mesh'ten yapilan "kati" bir
        yalandir; once mesh_onar cagrilmali.
      * Sonuc PARAMETRIK DEGILDIR ve bunu soyler. Olculdu: 8000 facet ->
        8000 YUZLU kati, 4.64 sn. Facet siniri asilirsa once decimate
        uygulanir ve kaca indigi yazilir.
    """
    import Part

    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("kati_yap: bu bir mesh nesnesi degil")
        return None

    ad = getattr(nesne, "Name", "?")
    durum = _mesh_durumu(m)
    if not durum.get("kapali"):
        if yaz:
            print(f"kati_yap: {ad} KAPALI DEGIL ({_durum_metni(durum)}). "
                  f"Acik bir mesh'ten yapilan kati yaniltir — once "
                  f"mesh_onar({ad}) calistir.")
        return None

    t0 = time.time()
    try:
        kati, facet_sonra = _mesh_kati(m, azami_facet)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"kati_yap: donusum basarisiz ({e})")
        return None

    doc = App.ActiveDocument
    yeni = doc.addObject("Part::Feature", ad + "_kati")
    yeni.Label = (getattr(nesne, "Label", ad) or ad) + " (kati)"
    yeni.Shape = kati

    try:
        nesne.Visibility = False
    except Exception:
        pass

    sure = time.time() - t0
    if yaz:
        sapma = ""
        try:
            hm = float(m.Volume)
            if hm:
                sapma = f", hacim sapmasi %{abs(kati.Volume - hm) / hm * 100:.2f}"
        except Exception:
            pass
        print(f"{ad} -> {yeni.Name}: kati, {len(kati.Faces)} yuz, "
              f"hacim={_sayi(kati.Volume)} mm3{sapma} ({sure:.2f} sn)")
        facet = durum.get("facet") or 0
        if facet_sonra != facet:
            print(f"    facet {facet} -> {facet_sonra} "
                  f"(sinir {azami_facet}, decimate uygulandi)")
        if not kati.isValid():
            print("    UYARI: kati isValid() False — boolean'lar bunun "
                  "uzerine kurulursa hata zincirin sonunda cikar")
        print("    NOT: bu PARAMETRIK bir kati degil, her ucgen bir yuz. "
              "Duzenlenebilir bir parca isteniyorsa olculeri alip sifirdan "
              "kurmak gerekir.")
    return yeni


def icini_bosalt(nesne=None, kalinlik: float = 2.0, acik_yuz=None,
                 yaz: bool = True):
    """Kati bir govdenin icini bosaltir (kabuk) — kupa, kutu, muhafaza.

    TUZAK (olculdu): `makeThickness` yuzu AYNI shape ORNEGINDEN ister.
    Sekli iki kez kurup yuzu obur ornekten vermek
    "face does not belong to the shape" hatasi veriyor. Burada yuz her
    zaman uzerinde calisilan shape'ten seciliyor.

    `acik_yuz` verilmezse en USTTEKI yuz acilir (kupa/kutu icin dogrusu).
    """
    nesne = _hedef(nesne)
    s = _sekil_al(nesne)
    if s is None:
        if yaz:
            print("icini_bosalt: kati nesne gerek (mesh icin once kati_yap)")
        return None

    ad = getattr(nesne, "Name", "?")
    try:
        yuzler = s.Faces
    except Exception:
        yuzler = []
    if not yuzler:
        if yaz:
            print(f"icini_bosalt: {ad} yuzsuz")
        return None

    if acik_yuz is None:
        yuz = max(yuzler, key=lambda f: f.CenterOfMass.z)
    elif isinstance(acik_yuz, int):
        if not 0 <= acik_yuz < len(yuzler):
            if yaz:
                print(f"icini_bosalt: yuz {acik_yuz} yok "
                      f"(0..{len(yuzler) - 1})")
            return None
        yuz = yuzler[acik_yuz]
    else:
        yuz = acik_yuz

    onceki_hacim = float(s.Volume or 0.0)
    try:
        kabuk = s.makeThickness([yuz], -abs(kalinlik), 1e-3)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"icini_bosalt: olmadi ({e}). Kalinlik govdeye gore cok "
                  f"buyuk olabilir; daha kucuk bir deger dene.")
        return None

    doc = App.ActiveDocument
    yeni = doc.addObject("Part::Feature", ad + "_kabuk")
    yeni.Label = (getattr(nesne, "Label", ad) or ad) + f" (kabuk {kalinlik}mm)"
    yeni.Shape = kabuk
    try:
        nesne.Visibility = False
    except Exception:
        pass

    if yaz:
        h = float(kabuk.Volume or 0.0)
        print(f"{ad} -> {yeni.Name}: kabuk {kalinlik} mm, "
              f"hacim {_sayi(onceki_hacim)} -> {_sayi(h)} mm3")
        # DOGRULAMA: kabuk hacmi orijinalin bir kismi olmali. Neredeyse
        # ayniysa islem GORUNMEZ kalmistir.
        if onceki_hacim and h > 0.9 * onceki_hacim:
            print("    UYARI: hacim neredeyse degismedi — kabuk olusmamis "
                  "olabilir, acik yuzu kontrol et")
        if not kabuk.isValid():
            print("    UYARI: sonuc isValid() False")
    return yeni


# ==========================================================================
# TUR 2 — olculer TABLODA (Spreadsheet + ifade motoru)
# ==========================================================================

TABLO_ADI = "Olculer"


def olcu_tablosu(_ad: str = TABLO_ADI, yaz: bool = True, **degerler):
    """Olculeri bir TABLOYA koyar; ozellikler oraya baglanabilir.

    NEDEN: "Birak duzenlenebilir olsun" kuralinin en guclu hali. Olculer
    kodun icine gomulu sabitler oldugunda kullanici her degisiklik icin
    AI'a donmek zorunda. Tabloda olunca tek hucreyi degistirip modeli
    guncelliyor.

        olcu_tablosu(cap=55.5, yukseklik=95, duvar=2)
        bagla(govde, "Radius", "Olculer.cap / 2")

    Olculdu: setAlias + setExpression calisiyor, Radius = 27.75 mm.
    """
    doc = App.ActiveDocument
    if doc is None:
        if yaz:
            print("olcu_tablosu: acik belge yok")
        return None

    sh = doc.getObject(_ad)
    if sh is None:
        sh = doc.addObject("Spreadsheet::Sheet", _ad)
        sh.Label = "Ölçüler"

    # Var olan satirlari bul ki ayni ad iki kez yazilmasin.
    satir = 1
    mevcut = {}
    while satir < 200:
        try:
            a = sh.get(f"A{satir}")
        except Exception:
            break
        if a in (None, ""):
            break
        mevcut[str(a)] = satir
        satir += 1

    yazilan = []
    for ad, deger in degerler.items():
        r = mevcut.get(ad, satir)
        if ad not in mevcut:
            satir += 1
        try:
            sh.set(f"A{r}", str(ad))
            sh.set(f"B{r}", str(deger))
            sh.setAlias(f"B{r}", str(ad))
            yazilan.append(f"{ad}={deger}")
        except Exception as e:                                   # noqa: BLE001
            if yaz:
                print(f"    {ad} yazilamadi: {e}")

    try:
        doc.recompute()
    except Exception:
        pass

    if yaz:
        print(f"{_ad} tablosu: " + (", ".join(yazilan) or "(bos)"))
        print(f"    kullanimi: bagla(nesne, \"Radius\", \"{_ad}.<ad> / 2\")")
    return sh


def bagla(nesne, ozellik: str, ifade: str, yaz: bool = True) -> bool:
    """Bir ozelligi tablodaki degere BAGLAR ve baglandigini DOGRULAR.

    `setExpression` sessizce ise yaramayabiliyor (yanlis alias, cozulmeyen
    ifade). Burada bagladiktan sonra deger gercekten okunuyor.
    """
    if nesne is None or not ozellik:
        if yaz:
            print("bagla: nesne ve ozellik adi gerek")
        return False
    try:
        onceki = getattr(nesne, ozellik, None)
    except Exception:
        onceki = None

    # IFADEYI ONCE DENE. OLCULDU: `setExpression` COZULMEYEN bir ifadeyi
    # de kabul ediyor — istisna atmiyor, ExpressionEngine'e giriyor, ama
    # deger degismiyor. Yani "kuruldu mu" diye ExpressionEngine'e bakmak
    # YANLIS cevap veriyor. Tek guvenilir yol ifadeyi degerlendirmek.
    try:
        nesne.evalExpression(ifade)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"bagla: ifade COZULMEDI — {ifade}  ({e})")
            print(f"    {ozellik} {onceki} olarak kaldi. Tablodaki alias "
                  f"adini kontrol et (olcu_tablosu ciktisinda yaziyor).")
        return False

    try:
        nesne.setExpression(ozellik, ifade)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"bagla: {ozellik} <- {ifade} olmadi ({e})")
        return False

    try:
        sonra = getattr(nesne, ozellik, None)
    except Exception:
        sonra = None

    if yaz:
        print(f"{nesne.Name}.{ozellik} <- {ifade}  (={sonra})")
    return True


# ==========================================================================
# TUR 3 — yazi, vida disi, agirlik
# ==========================================================================

_FONT_ADAYLARI = ("arial.ttf", "segoeui.ttf", "tahoma.ttf", "verdana.ttf",
                  "calibri.ttf", "DejaVuSans.ttf")


def _font_bul(font: str = "") -> str:
    if font and os.path.isfile(font):
        return font
    dizinler = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]
    for d in dizinler:
        for ad in _FONT_ADAYLARI:
            yol = os.path.join(d, ad)
            if os.path.isfile(yol):
                return yol
    return ""


def yazi(metin: str, boyut: float = 10.0, kalinlik: float = 1.0,
         font: str = "", yaz: bool = True):
    """Parca uzerine YAZI — isim, olcu, logo. Gercek geometri uretir.

    Olculdu: Draft.make_shapestring 2.14 sn (ilk cagri modul yuklemesi),
    "CADdy" icin 97 kenarli sekil.

    `kalinlik` > 0 ise yazi kati hale getirilir (kabartma/oyma icin
    hazir). Font bulunamazsa SESSIZ KALMAZ.
    """
    yol = _font_bul(font)
    if not yol:
        if yaz:
            print(f"yazi: font bulunamadi (denenenler: "
                  f"{', '.join(_FONT_ADAYLARI)}). Tam yol ver: "
                  f"yazi('...', font=r'C:\\Windows\\Fonts\\arial.ttf')")
        return None

    try:
        import Draft
        import Part
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"yazi: Draft yuklenemedi ({e})")
        return None

    doc = App.ActiveDocument
    try:
        ss = Draft.make_shapestring(String=str(metin), FontFile=yol,
                                    Size=float(boyut))
        doc.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"yazi: olusturulamadi ({e})")
        return None

    sonuc = ss
    if kalinlik and kalinlik > 0:
        try:
            kati = ss.Shape.extrude(App.Vector(0, 0, float(kalinlik)))
            nesne = doc.addObject("Part::Feature", "Yazi")
            nesne.Label = f"Yazı: {metin}"
            nesne.Shape = kati
            doc.removeObject(ss.Name)
            doc.recompute()
            sonuc = nesne
        except Exception as e:                                   # noqa: BLE001
            if yaz:
                print(f"    kalinlastirilamadi ({e}); duz sekil birakildi")

    if yaz:
        try:
            b = sonuc.Shape.BoundBox
            print(f"{sonuc.Name}: '{metin}' {_sayi(b.XLength)}x"
                  f"{_sayi(b.YLength)}x{_sayi(b.ZLength)} mm "
                  f"(font {os.path.basename(yol)})")
            print("    XY duzleminde, (0,0)'dan basliyor. Yerlestirmek icin "
                  "Placement, gomulmek icin boolean kullan.")
        except Exception:
            pass
    return sonuc


def vida_disi(yaricap: float, hatve: float, boy: float,
              ic_mi: bool = False, yaz: bool = True):
    """VIDA DISI uretir (helis + ucgen profil).

    GUNLUK: b2938bd0 bastan sona bir BANJO CIVATASI oturumuydu ve dis hic
    acilamadi.

    `yaricap` dis capin YARISI (M8 icin 4). `hatve` bir turdaki ilerleme
    (M8 kaba dis icin 1.25). `ic_mi=True` somun/delik disi icin profil
    ice bakar.
    """
    import Part

    try:
        yaricap = float(yaricap)
        hatve = float(hatve)
        boy = float(boy)
    except Exception:
        if yaz:
            print("vida_disi: sayisal deger gerek")
        return None
    if min(yaricap, hatve, boy) <= 0:
        if yaz:
            print("vida_disi: yaricap, hatve ve boy pozitif olmali")
        return None

    # ISO metrik disin teorik derinligi 0.6134 * hatve.
    derinlik = 0.6134 * hatve
    yon = -1.0 if ic_mi else 1.0

    try:
        helis = Part.makeHelix(hatve, boy, yaricap)
        # PROFIL TABANI SILINDIRIN ICINDE OLMALI. Olculdu: taban tam
        # yaricapta iken (silindir yuzeyine TEGET) fuse gecersiz bir kati
        # uretiyor — isValid() False ve hacim silindirinkinden KUCUK
        # cikiyor. derinlik/3 kadar iceri alinca isValid() True ve hacim
        # 1155 (silindir 1005), yani dis gercekten disari cikiyor.
        taban = App.Vector(yaricap - derinlik / 3.0, 0, 0)
        p1 = taban + App.Vector(0, 0, -hatve / 2.0)
        p2 = taban + App.Vector(0, 0, hatve / 2.0)
        p3 = App.Vector(yaricap + yon * derinlik, 0, 0)
        profil = Part.Wire(Part.makePolygon([p1, p2, p3, p1]))
        boru = Part.Wire(helis).makePipeShell([profil], True, True)
        govde = Part.makeCylinder(yaricap, boy)
        kati = govde.fuse(boru) if not ic_mi else govde.cut(boru)
        kati = kati.removeSplitter()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"vida_disi: uretilemedi ({e})")
        return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Part::Feature", "VidaDisi")
    nesne.Label = f"Vida dişi M{_sayi(2 * yaricap)}x{_sayi(hatve)}"
    nesne.Shape = kati
    doc.recompute()

    if yaz:
        print(f"{nesne.Name}: {'ic' if ic_mi else 'dis'} dis, "
              f"cap={_sayi(2 * yaricap)} hatve={_sayi(hatve)} "
              f"boy={_sayi(boy)} mm, {int(boy / hatve)} tur, "
              f"hacim={_sayi(kati.Volume)} mm3")
        if not kati.isValid():
            print("    UYARI: sonuc isValid() False — hatve/derinlik "
                  "oranini gozden gecir")
        if len(kati.Solids) != 1:
            print(f"    UYARI: {len(kati.Solids)} kati ciktiı, 1 bekleniyordu")
    return nesne


def agirlik(nesne=None, malzeme: str = "PLA", doluluk: float = 1.0,
            yaz: bool = True) -> dict:
    """Parcanin AGIRLIGI ve harcanacak filament.

    "Kac gram gelir" sorusunun cevabi ve su ana kadar hic veremiyorduk.
    `doluluk` 0..1 arasi (0.2 = %20 infill; kabaca — duvarlar ve ust/alt
    katmanlar bunu yukari ceker, bu yuzden sonuc ALT SINIRDIR).
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("agirlik: nesne bulunamadi")
        return {}

    hacim = None
    m = _mesh_al(nesne)
    if m is not None:
        try:
            hacim = float(m.Volume)
        except Exception:
            hacim = None
    if hacim is None:
        s = _sekil_al(nesne)
        try:
            hacim = float(s.Volume)
        except Exception:
            hacim = None
    if not hacim or hacim <= 0:
        if yaz:
            print(f"agirlik: {getattr(nesne, 'Name', '?')} hacmi okunamadi "
                  f"(mesh kapali degilse hacim anlamsizdir)")
        return {}

    anahtar = str(malzeme).upper().strip()
    yog = YOGUNLUK.get(anahtar)
    if yog is None:
        if yaz:
            print(f"agirlik: {malzeme} bilinmiyor. Bilinenler: "
                  f"{', '.join(sorted(YOGUNLUK))}")
        return {}

    cm3 = hacim / 1000.0 * max(0.0, min(1.0, doluluk))
    gram = cm3 * yog
    # 1.75 mm filament kesiti = pi * 0.875^2 = 2.405 mm2 -> 2.405 cm3/m
    metre = cm3 / 2.405 * 10.0 / 10.0 if False else cm3 / 0.2405 / 100.0

    d = {"hacim_mm3": hacim, "gram": gram, "malzeme": anahtar,
         "metre": metre}
    if yaz:
        ek = "" if doluluk >= 1 else f" (%{doluluk * 100:.0f} doluluk, alt sinir)"
        print(f"{getattr(nesne, 'Name', '?')}: {_sayi(hacim / 1000.0)} cm3 "
              f"{anahtar} -> {gram:.1f} g{ek}, ~{metre:.1f} m filament "
              f"(1.75 mm)")
    return d


# ==========================================================================
# TUR 4 — bolme, dizi, tabla yuzu, birlestirme
# ==========================================================================

def baskiya_bol(nesne=None, z=None, yaz: bool = True) -> list:
    """Parcayi baski icin PARCALARA boler (yatay duzlemle).

    GUNLUK: b2938bd0'da kullanici "gerekirse 2 parca yapariz birbirine
    gecen" dedi ve elle ugrasildi. BOPTools.SplitAPI tek cagri (olculdu:
    0.391 sn, 2 kati).
    """
    from BOPTools import SplitAPI
    import Part

    nesne = _hedef(nesne)
    s = _sekil_al(nesne)
    if s is None:
        if yaz:
            print("baskiya_bol: kati nesne gerek (mesh icin once kati_yap)")
        return []

    b = s.BoundBox
    if z is None:
        z = b.ZMin + b.ZLength / 2.0
    if not (b.ZMin < z < b.ZMax):
        if yaz:
            print(f"baskiya_bol: z={_sayi(z)} govdenin disinda "
                  f"({_sayi(b.ZMin)}..{_sayi(b.ZMax)})")
        return []

    try:
        pay = max(b.XLength, b.YLength) * 2 + 10
        duzlem = Part.makePlane(pay, pay,
                                App.Vector(b.Center.x - pay / 2,
                                           b.Center.y - pay / 2, z))
        bolunmus = SplitAPI.slice(s, [duzlem], "Split")
        katilar = list(bolunmus.Solids)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"baskiya_bol: olmadi ({e})")
        return []

    if len(katilar) < 2:
        if yaz:
            print(f"baskiya_bol: z={_sayi(z)} duzlemi govdeyi ayirmadi "
                  f"({len(katilar)} parca). Baska bir yukseklik dene.")
        return []

    doc = App.ActiveDocument
    ad = getattr(nesne, "Name", "Parca")
    yeniler = []
    for i, k in enumerate(katilar, start=1):
        o = doc.addObject("Part::Feature", f"{ad}_p{i}")
        o.Label = f"{getattr(nesne, 'Label', ad)} parça {i}"
        o.Shape = k
        yeniler.append(o)
    try:
        nesne.Visibility = False
    except Exception:
        pass
    doc.recompute()

    if yaz:
        print(f"{ad}: z={_sayi(z)} hizasinda {len(yeniler)} parcaya bolundu")
        for o in yeniler:
            bb = o.Shape.BoundBox
            print(f"    {o.Name}: {_sayi(bb.XLength)}x{_sayi(bb.YLength)}"
                  f"x{_sayi(bb.ZLength)} mm  hacim={_sayi(o.Shape.Volume)}")
        print("    NOT: parcalar duz kesildi; gecme/pim isteniyorsa ayrica "
              "eklenmeli.")
    return yeniler


def _dizi_dogrula(dizi, beklenen: int, yaz: bool) -> bool:
    """Dizinin gercekten `beklenen` kopya urettigini olcer.

    PartDesign desenleri sessizce TEK kopya birakabiliyor (olculdu).
    Ayni sessiz hatayi Draft dizisinde de kabul etmiyoruz.
    """
    try:
        n = len(dizi.Shape.Solids) or len(dizi.Shape.childShapes())
    except Exception:
        return True
    if n < beklenen:
        if yaz:
            print(f"    UYARI: {beklenen} kopya istendi ama sonucta {n} var. "
                  f"Kopyalar ust uste binmis ya da dizi uygulanmamis olabilir.")
        return False
    return True


def dizi_polar(nesne=None, adet: int = 6, aci: float = 360.0,
               merkez=None, yaz: bool = True):
    """Nesneyi Z ekseni etrafinda POLAR dizer. Olculdu: 0.030 sn."""
    import Draft

    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("dizi_polar: nesne bulunamadi")
        return None
    if adet < 2:
        if yaz:
            print("dizi_polar: adet en az 2 olmali")
        return None

    if merkez is None:
        merkez = App.Vector(0, 0, 0)
    try:
        d = Draft.make_polar_array(nesne, int(adet), float(aci), merkez)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"dizi_polar: olmadi ({e})")
        return None

    if yaz:
        print(f"{d.Name}: {getattr(nesne, 'Name', '?')} x{adet}, "
              f"{_sayi(aci)} derecede, merkez=({_sayi(merkez.x)},"
              f"{_sayi(merkez.y)})")
        _dizi_dogrula(d, adet, yaz)
    return d


def dizi_dogrusal(nesne=None, adet: int = 3, yon=None, aralik: float = 20.0,
                  yaz: bool = True):
    """Nesneyi bir dogrultuda dizer. Olculdu: 1.93 sn (ilk cagri)."""
    import Draft

    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("dizi_dogrusal: nesne bulunamadi")
        return None
    if adet < 2:
        if yaz:
            print("dizi_dogrusal: adet en az 2 olmali")
        return None

    if yon is None:
        yon = App.Vector(1, 0, 0)
    try:
        u = App.Vector(yon).normalize()
    except Exception:
        u = App.Vector(1, 0, 0)
    adim = App.Vector(u.x * aralik, u.y * aralik, u.z * aralik)

    try:
        d = Draft.make_ortho_array(nesne, adim, App.Vector(0, 0, 0),
                                   App.Vector(0, 0, 0), int(adet), 1, 1)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"dizi_dogrusal: olmadi ({e})")
        return None

    if yaz:
        print(f"{d.Name}: {getattr(nesne, 'Name', '?')} x{adet}, "
              f"{_sayi(aralik)} mm arayla ({_sayi(u.x)},{_sayi(u.y)},"
              f"{_sayi(u.z)}) yonunde")
        _dizi_dogrula(d, adet, yaz)
    return d


def _en_buyuk_duz_yuz(nesne):
    """(normal, nokta) — parcanin en genis duz bolgesi. Yoksa None."""
    m = _mesh_al(nesne)
    if m is not None:
        try:
            segmentler = m.getPlanarSegments(0.01)
        except Exception:
            return None
        if not segmentler:
            return None
        en = max(segmentler, key=len)
        if len(en) < 3:
            return None
        try:
            f = m.Facets[en[0]]
            n = App.Vector(*f.Normal)
            p = App.Vector(*f.Points[0])
            # Alan olarak en buyuk segmenti tercih ettik; facet sayisi
            # yeterli bir vekil (ucgenler kabaca ayni boyutta).
            return n.normalize(), p
        except Exception:
            return None

    s = _sekil_al(nesne)
    if s is None:
        return None
    duz = []
    for f in s.Faces:
        try:
            if type(f.Surface).__name__ == "Plane":
                duz.append(f)
        except Exception:
            continue
    if not duz:
        return None
    f = max(duz, key=lambda x: x.Area)
    try:
        return App.Vector(f.Surface.Axis).normalize(), f.CenterOfMass
    except Exception:
        return None


def tabana_otur(nesne=None, yaz: bool = True) -> bool:
    """Parcayi en genis DUZ yuzu asagi bakacak sekilde tablaya oturtur.

    Baski hazirliginin ilk sorusu ve su ana kadar goz karariydi.
    Olculdu: Mesh.getPlanarSegments 0.010 sn.

    Duz bolge yoksa UYDURMAZ, soyler.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("tabana_otur: nesne bulunamadi")
        return False

    bulgu = _en_buyuk_duz_yuz(nesne)
    if bulgu is None:
        if yaz:
            print(f"tabana_otur: {getattr(nesne, 'Name', '?')} icin duz bir "
                  f"yuz bulunamadi — bu parcanin tablaya oturacak duz yeri "
                  f"yok, destek ya da elle yonlendirme gerekiyor")
        return False

    normal, _nokta = bulgu
    hedef = App.Vector(0, 0, -1)
    try:
        aci = math.degrees(normal.getAngle(hedef))
    except Exception:
        aci = 0.0

    try:
        if aci > 0.5:
            eksen = normal.cross(hedef)
            if eksen.Length < 1e-9:               # tam ters yonlu
                eksen = App.Vector(1, 0, 0)
            donme = App.Rotation(eksen, aci)
            p = nesne.Placement
            nesne.Placement = App.Placement(
                donme.multVec(p.Base), donme.multiply(p.Rotation))
        App.ActiveDocument.recompute()
        b = olcum._kutu(nesne)
        if b is not None and abs(b.ZMin) > 1e-9:
            p = nesne.Placement
            p.Base = App.Vector(p.Base.x, p.Base.y, p.Base.z - b.ZMin)
            nesne.Placement = p
            App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"tabana_otur: yerlestirilemedi ({e})")
        return False

    if yaz:
        b = olcum._kutu(nesne)
        print(f"{getattr(nesne, 'Name', '?')}: {_sayi(aci)} derece "
              f"dondurulup tablaya oturtuldu, z={_sayi(b.ZMin)}.."
              f"{_sayi(b.ZMax)}")
    return True


_KABUK_ONBELLEK = {}          # (belge, nesne) -> (imza, kabuk, duz_zler)


def _yatay_yuz_zleri(m, tol: float = 1e-4) -> list:
    """Mesh'teki YATAY yuzeylerin z yukseklikleri. Kesitin yalan soyledigi yerler.

    OLCULDU — bir kesit tam yatay bir yuzeye denk gelirse sonuc sessizce
    bozuluyor, hem OCC hem mesh yolunda:

        silindir r=15 h=40   z=0  -> alan   7.2   (dogrusu 706.9)
        silindir r=15 h=40   z=40 -> alan   7.2
        kutu 20x30x10        z=0  -> alan 300.0   (dogrusu 600)
        kademeli parca       z=10 -> alan 600.0   (asagisi 1600, yukarisi 400)

    Sonuncusu en sinsisi: deger ne alttakine ne ustekine esit, ikisinin
    arasinda uydurma bir sayi. Hicbiri hata vermiyor.

    Tek gecis, facet normali +-Z olanlarin z'si toplaniyor — 4500 facet'te
    milisaniyeler. Kabukla birlikte onbellege giriyor.
    """
    zler = set()
    try:
        for facet in m.Facets:
            n = facet.Normal
            if abs(n.z) > 0.9999 and abs(n.x) < 1e-3 and abs(n.y) < 1e-3:
                p = facet.Points[0]
                zler.add(round(p[2], 4))
    except Exception:                                            # noqa: BLE001
        return []
    # Yakin degerleri tek basliga topla (facet'ler tam ayni z'de olmayabilir).
    sirali = sorted(zler)
    kumeler = []
    for z in sirali:
        if kumeler and abs(z - kumeler[-1]) <= tol * 10:
            continue
        kumeler.append(z)
    return kumeler


def _mesh_on_kontrol(m, yaz: bool) -> str:
    """Kabuga CEVIRMEDEN once mesh'in sagligi. Bozuksa sebep metni doner.

    NEDEN VAR — OLCULDU (LOG/2026-09-01_361c792d.txt): indirilen bir ucak
    mesh'inde (34350 facet) `kesit_konturu(ucak, [3,8,15,25,35,43])`
    **22.66 saniye** surdu ve alti satir "kontur yok" yazdi. Maliyetin
    tamami `makeShapeFromMesh` donusumunde; kesitlerin kendisi 0.01 sn.

    Oysa cevabin bos cikacagi ONCEDEN, 0.05 saniyede biliniyordu:

        isSolid              False   0.016 sn
        hasNonManifolds      True    0.001 sn
        hasSelfIntersections True    0.016 sn
        countComponents      494     0.000 sn

    Yani 700 kat ucuz bir bakis 22.66 saniyenin bosa gidecegini soyluyordu.
    Ustelik ayni blokta `kesif()` zaten "baskiya hazir = HAYIR (kapali
    degil, kendiyle kesisme, non-manifold, cok parca)" yazmisti; teshis
    vardi, bu fonksiyon ona bakmiyordu.

    REDDETMIYORUZ, UYARIYORUZ. Olculdu (dort mesh, ayni gun):

        temiz kutu      kapali,  tek parca, 12 facet  -> 0.00 sn, 1 kontur
        ACIK kutu       ACIK,    tek parca, 10 facet  -> 0.01 sn, 1 kontur
        3 ayrik kure    kapali, 3 PARCA,   912 facet  -> 0.13 sn, 3 kontur
        indirilen ucak  acik+non-manifold+kesisen, 494 parca, 34350 facet
                                                    -> 24.87 sn, 0 kontur

    Yani "kapali degil" TEK BASINA ret sebebi DEGIL (acik kutu dogru kontur
    verdi) ve "cok parca" da degil (uc kure uc kontur verdi). Tek ornekten
    kural yazmak bu projede yasak; o yuzden hukum vermiyoruz, maliyeti
    ODEMEDEN once ne aldigimizi soyluyoruz ve bos cikarsa SEBEBINI yaziyoruz.
    """
    try:
        facet = int(m.CountFacets)
        kusurlar = []
        if not m.isSolid():
            kusurlar.append("not closed")
        if m.hasNonManifolds():
            kusurlar.append("non-manifold")
        if m.hasSelfIntersections():
            kusurlar.append("self-intersecting")
        parca = int(m.countComponents())
        if parca > 1:
            kusurlar.append(f"{parca} separate components")
    except Exception:                                            # noqa: BLE001
        return ""
    if not kusurlar:
        return ""
    metin = ", ".join(kusurlar)
    if yaz:
        print(f"section_contour: the mesh is not sound ({metin}); {facet} facets "
              f"will be converted to a shell — this may take long and no "
              f"section may come out")
    return metin


def _kabuk_ve_duzler(hedef, m):
    """Mesh -> (kabuk, yatay yuz z'leri). Ayni nesne icin BIR KEZ hesaplanir.

    OLCULDU: `makeShapeFromMesh` 4512 facet'te 1.84 sn, `slice` ise cagri
    basina 2.76 sn. Gunlukte model alti farkli yukseklikte kesit istedi ve
    donusum ALTI KEZ odendi: 27.8 sn yerine 18.6 sn olmaliydi (1.5 kat).
    Asil maliyet slice'ta ve o OCC'nin isi, ama donusumu tekrar tekrar
    odemek bedava bir kayipti.
    """
    import Part

    doc = App.ActiveDocument
    anahtar = (getattr(doc, "Name", ""), getattr(hedef, "Name", id(hedef)))
    imza = (int(m.CountFacets), round(float(m.Area), 6))
    onbellek = _KABUK_ONBELLEK.get(anahtar)
    if onbellek is not None and onbellek[0] == imza:
        return onbellek[1], onbellek[2]

    kabuk = Part.Shape()
    kabuk.makeShapeFromMesh(m.Topology, 0.1)
    duzler = _yatay_yuz_zleri(m)
    _KABUK_ONBELLEK[anahtar] = (imza, kabuk, duzler)
    # Onbellek sinirsiz buyumesin; bu bir oturum icinde birkac nesne olur.
    if len(_KABUK_ONBELLEK) > 8:
        for k in list(_KABUK_ONBELLEK)[:-8]:
            _KABUK_ONBELLEK.pop(k, None)
    return kabuk, duzler


def kesit_konturu(nesne=None, z=None, sik: float = 0.8, yaz: bool = True):
    """Bir yukseklikteki KESIT KONTURLARINI nokta listesi olarak verir.

    Doner: konturlarin listesi, en uzundan kisaya sirali. Her kontur bir
    [(x, y), ...] listesi. Hicbir sey bulunamazsa BOS LISTE.

    NEDEN VAR — iki ayri oturumda iki ayri model ayni on satiri elle yazdi:

      LOG/2026-08-24_67cd3efb (Sonnet): `sekil.slice` dongusuyle genislik
        profili -> 68.9 sn; ayrica 49.0 sn'lik bir isInside nokta taramasi.
      LOG/2026-08-24_3ad4cef1 (Opus): `makeShapeFromMesh -> slice -> sort ->
        discretize` kalibini BES ayri blokta bastan yazdi. Her tekrar, hem
        token hem de "bu sefer yanlis yazarsam" riski demek.

    Mesh de kati da kabul eder; mesh ise once kabuga cevrilir (kati_yap'in
    aksine BELGEYE HICBIR NESNE EKLEMEZ, sadece okur). `z` verilmezse
    parcanin tam ortasindan keser. `z` bir LISTE de olabilir — o zaman
    {z: konturlar} doner ve donusum bir kez odenir.

    KONTUR SIRASI onemli: [0] her zaman en uzun (dis hat), sonrakiler
    delikler/ayrik adalar. Opus'un "kesit tel sayisi: 2" ciktisinda ikinci
    tel tavsanin gozuydu.

    YATAY YUZEYE DENK GELEN KESIT SESSIZCE YANLIS CIKAR — bu yardimcinin ilk
    surumunde acik bir hataydi, olculdu: silindir r=15 h=40, z=0'da kesit
    alani 7.2 mm2 (dogrusu 706.9), kutu z=0'da 300 (dogrusu 600), kademeli
    parcada omuz hizasinda 600 (asagisi 1600, yukarisi 400). Hicbiri hata
    vermiyordu. Artik:
      * ucta (bbox sinirinda) istenen z ICERI kaydiriliyor ve soyleniyor,
      * ic bir yatay yuzeye denk gelirse UYARI veriliyor ve guvenli iki
        komsu z yaziliyor — hangisinin istendigi cagirana ait bir karar.

    Mesh.crossSections REDDEDILDI: 673 kat hizli ama kure ekvatorunda yolu
    iki kez dolasip alani sifirliyor, kutu z=0'da yine 300 veriyor. Hizin
    dogruluk pahasina alinmasi bu projede yasak.
    """
    import Part

    hedef = _hedef(nesne)
    if hedef is None:
        if yaz:
            print("section_contour: no object")
        return {} if isinstance(z, (list, tuple)) else []

    coklu = isinstance(z, (list, tuple))
    duz_zler = []
    mesh_kusuru = ""          # bos kesitin SEBEBI, mesh bozuksa
    sekil = _sekil_al(hedef)
    if sekil is None:
        m = _mesh_al(hedef)
        if m is None:
            if yaz:
                print("section_contour: the object has neither a shape nor a mesh")
            return {} if coklu else []
        # Pahali donusumden ONCE 0.05 saniyelik bakis (bkz. _mesh_on_kontrol).
        mesh_kusuru = _mesh_on_kontrol(m, yaz)
        sekil, duz_zler = _kabuk_ve_duzler(hedef, m)

    try:
        bb = sekil.BoundBox
    except Exception:                                            # noqa: BLE001
        if yaz:
            print("section_contour: could not read the bounding box")
        return {} if coklu else []

    if z is None:
        istenen = [(bb.ZMin + bb.ZMax) / 2.0]
    elif coklu:
        istenen = [float(v) for v in z]
    else:
        istenen = [float(z)]

    # Ucta kesmek her zaman bozuk cikiyor (olculdu). Icerinin kalinligina
    # gore kucuk ama anlamli bir pay: cok ince parcada 0.001 yetmiyordu.
    pay = max(bb.ZLength * 1e-4, 1e-4)
    sonuc = {}
    for ham_z in istenen:
        # UCTA olmak ile DISARIDA olmak ayri seyler. Ucta kaydiriyoruz
        # (istenen kesit odur, sadece tam sinirda OCC bozuluyor); disarida
        # KAYDIRMIYORUZ — sorulmayan soruyu cevaplamak olurdu.
        if ham_z < bb.ZMin - pay or ham_z > bb.ZMax + pay:
            if yaz:
                print(f"section_contour: z={_sayi(ham_z)} is outside the part "
                      f"(z {_sayi(bb.ZMin)}..{_sayi(bb.ZMax)}) — no section")
            sonuc[ham_z] = []
            continue

        kz = ham_z
        if kz < bb.ZMin + pay:
            kz = bb.ZMin + pay
        elif kz > bb.ZMax - pay:
            kz = bb.ZMax - pay
        if yaz and abs(kz - ham_z) > 1e-12:
            print(f"section_contour: z={_sayi(ham_z)} is exactly at the end — moved "
                  f"to {_sayi(kz)} (a section at the very end comes out broken)")
        elif yaz and duz_zler:
            yakin = [d for d in duz_zler if abs(d - kz) <= pay * 10]
            if yakin:
                print(f"section_contour: WARNING z={_sayi(kz)} lies on a horizontal "
                      f"face — the section is ambiguous at this height. "
                      f"Ask below/above separately: {_sayi(kz - pay * 20)} and "
                      f"{_sayi(kz + pay * 20)}")

        konturlar, teller = _bir_kesit(sekil, kz, sik)
        sonuc[ham_z] = konturlar
        if yaz:
            _kesit_yaz(kz, konturlar, teller)

    # HICBIRINDEN kontur cikmadiysa ve mesh bozuksa, sebebi SOYLE. Gunlukte
    # alti ozdes "kontur yok" satiri vardi ve hicbiri neden oldugunu
    # anlatmiyordu; model dogru sonuca kendi akil yurutmesiyle vardi.
    # §35.2'nin dersi: genel ogut tetiklenmez, ADI KONMUS emir tetiklenir —
    # o yuzden "dikkat et" degil, "bu yolu birak, baska olcum kullan".
    if yaz and mesh_kusuru and not any(sonuc.values()):
        print(f"section_contour: no contour at any of the {len(sonuc)} heights — "
              f"the cause is NOT the height choice but the mesh ({mesh_kusuru}); "
              f"the shell did not come out sound. Sections will not work on "
              f"this object, use another measurement (bbox scan, measure(), distance()).")

    if coklu:
        return sonuc
    return sonuc[istenen[0]]


def _bir_kesit(sekil, z: float, sik: float):
    """Tek yukseklikte kesit. (konturlar, teller) doner."""
    try:
        teller = sekil.slice(App.Vector(0, 0, 1), float(z))
    except Exception:                                            # noqa: BLE001
        return [], []
    teller = sorted(teller, key=lambda w: -w.Length)
    konturlar = []
    kalan_teller = []
    for tel in teller:
        try:
            noktalar = [(v.x, v.y) for v in tel.discretize(Distance=sik)]
        except Exception:                                        # noqa: BLE001
            continue
        # Kapali telde ilk ve son nokta ayni gelir; tekrari atiyoruz ki
        # cagiran "n nokta" derken gercek sayiyi kullansin.
        if len(noktalar) > 1 and _yakin(noktalar[0], noktalar[-1]):
            noktalar = noktalar[:-1]
        if len(noktalar) >= 3:
            konturlar.append(noktalar)
            kalan_teller.append(tel)
    return konturlar, kalan_teller


def _kesit_yaz(z: float, konturlar: list, teller: list) -> None:
    if not konturlar:
        print(f"section_contour: no contour in the z={_sayi(z)} section")
        return
    print(f"section_contour: z={_sayi(z)} — {len(konturlar)} contour(s) "
          f"(longest first)")
    for i, k in enumerate(konturlar):
        xs = [p[0] for p in k]
        ys = [p[1] for p in k]
        cevre = _sayi(teller[i].Length) if i < len(teller) else "?"
        print(f"    [{i}] {len(k)} points  x={_sayi(min(xs))}.."
              f"{_sayi(max(xs))}  y={_sayi(min(ys))}..{_sayi(max(ys))}"
              f"  perimeter={cevre} mm")


def _yakin(p, q, tol: float = 1e-7) -> bool:
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def _bbox_ortusme(ma, mb):
    """Iki mesh'in bbox'lari ic ice mi. (ortusuyor_mu, en_kucuk_ortusme).

    Ortusmuyorsa ikinci deger NEGATIF: eksenler arasindaki en buyuk bosluk,
    yani gercek mesafenin ALT SINIRI. Alt sinir oldugunu soylemek, uydurma
    bir mesafe vermekten iyi.
    """
    try:
        ba, bb = ma.BoundBox, mb.BoundBox
    except Exception:
        return None, 0.0
    ortak = []
    for (a0, a1), (b0, b1) in (((ba.XMin, ba.XMax), (bb.XMin, bb.XMax)),
                               ((ba.YMin, ba.YMax), (bb.YMin, bb.YMax)),
                               ((ba.ZMin, ba.ZMax), (bb.ZMin, bb.ZMax))):
        ortak.append(min(a1, b1) - max(a0, b0))
    en_kucuk = min(ortak)
    return (en_kucuk > 0), en_kucuk


def _mesh_birlestir(a, b, ma, mb, azami_facet: int, yaz: bool):
    """birlestir()'in MESH yolu — katiya cevir, fuse et, mesh'e geri don.

    NEDEN `Mesh.Mesh.unite()` DEGIL: olculdu, FreeCAD 1.1.1'de unite hizli
    (0.003-0.05 sn) ve hacmi dogru hesapliyor (iki kutu: tam 15000 mm3) ama
    HICBIR yapilandirmada KAPALI mesh uretmedi:
        iki kutu       -> kapali=False              onarim sonrasi hala False
        iki kure       -> kapali=False, kesisme     onarim parcayi 1->3 yapti
        silindir+torus -> kapali=False, kesisme     onarim parcayi 1->7 yapti
    Yani unite uzerine kurulmus bir yardimci "birlestirdim" derken acik mesh
    birakirdi. Kati yolu ayni olcumde temiz sonuc verdi (bkz. _mesh_kati).

    TUTMAZSA UYDURMAZ: yarim nesneleri siler ve baski icin DOGRU olan cevabi
    verir — ic ice gecmis iki KAPALI parcayi dilimleyici zaten tek parca
    basar. Bu teselli degil, gunlukte modelin 16 dakika sonra kendi buldugu
    ve kullanicinin kabul ettigi cozum; fark, ilk cagride soylenmesi.
    """
    import MeshPart

    ad_a = getattr(a, "Name", "A")
    ad_b = getattr(b, "Name", "B")
    da, db = _mesh_durumu(ma), _mesh_durumu(mb)

    # 1) Ikisi de kapali olmali. Acik mesh'ten kati cikmaz.
    acik = [ad for ad, d in ((ad_a, da), (ad_b, db)) if not d.get("kapali")]
    if acik:
        if yaz:
            print(f"birlestir: {', '.join(acik)} KAPALI DEGIL "
                  f"({_durum_metni(da)} / {_durum_metni(db)}). "
                  f"Once mesh_onar calistir.")
        return None

    # 2) Gercekten degiyorlar mi. 7 saniyelik islemi bosuna baslatma.
    ortusuyor, olcu = _bbox_ortusme(ma, mb)
    if ortusuyor is False:
        if yaz:
            print(f"birlestir: {ad_a} ile {ad_b} DEGMIYOR — bbox'lar "
                  f"arasinda en az {_sayi(abs(olcu))} mm bosluk var. "
                  f"Birlestirmeden once parcalari ust uste getir "
                  f"(kesin mesafe icin mesafe({ad_a}, {ad_b})).")
        return None

    t0 = time.time()
    hacim_ayri = 0.0
    try:
        hacim_ayri = float(ma.Volume) + float(mb.Volume)
    except Exception:
        pass

    # 3+4) Katiya cevir -> fuse -> mesh'e geri don. Facet butcesi IKISINE
    # birden: olcumde sinir toplam facet uzerinden anlam kazaniyor.
    pay = max(1, int(azami_facet / 2))
    sorun = ""
    yeni_mesh = None
    try:
        ka, _ = _mesh_kati(ma, pay)
        kb, _ = _mesh_kati(mb, pay)
        kaynak = ka.fuse(kb)
        if len(kaynak.Solids) != 1:
            sorun = f"fuse {len(kaynak.Solids)} ayri kati birakti"
        elif hacim_ayri and kaynak.Volume >= hacim_ayri - 1e-9:
            sorun = "hacim toplamdan kuculmedi (gercekten kaynasmadilar)"
        else:
            yeni_mesh = MeshPart.meshFromShape(
                Shape=kaynak, LinearDeflection=0.1,
                AngularDeflection=0.3, Relative=False)
            ds = _mesh_durumu(yeni_mesh)
            if not ds.get("kapali"):
                sorun = "sonuc mesh KAPALI degil"
            elif ds.get("parca") not in (None, 1):
                sorun = f"sonuc {ds['parca']} parca"
    except Exception as e:                                       # noqa: BLE001
        sorun = str(e)[:120]

    sure = time.time() - t0

    # 5) Tutmadiysa: hicbir sey birakma, dogrusunu soyle.
    if sorun or yeni_mesh is None:
        if yaz:
            print(f"birlestir: tek parcaya kaynastirilamadi ({sorun}) "
                  f"[{sure:.1f} sn]")
            print(f"    AMA BASKI ICIN SORUN DEGIL: {ad_a} ve {ad_b} "
                  f"ikisi de KAPALI ve bbox'lari {_sayi(olcu)} mm ic ice. "
                  f"Dilimleyici ust uste binen kapali parcalari tek parca "
                  f"basar — birlestirmeye gerek yok, oldugu gibi birak.")
        return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Mesh::Feature", f"{ad_a}_birlesik")
    nesne.Mesh = yeni_mesh
    for o in (a, b):
        try:
            o.Visibility = False
        except Exception:
            pass
    doc.recompute()

    if yaz:
        ds = _mesh_durumu(yeni_mesh)
        print(f"{nesne.Name}: {ad_a} + {ad_b} -> mesh, "
              f"{_durum_metni(ds)}, hacim={_sayi(yeni_mesh.Volume)} mm3 "
              f"(ayri toplam {_sayi(hacim_ayri)}) [{sure:.1f} sn]")
        if ds.get("kesisme"):
            print("    UYARI: sonucta kendiyle kesisme var — "
                  f"mesh_onar({nesne.Name}) dene.")
    return nesne


def birlestir(a, b, azami_facet: int = AZAMI_FACET, yaz: bool = True):
    """Iki parcayi TEMIZ birlestirir.

    IKI KATI ise: `BOPTools.JoinAPI.connect`. Duz `fuse` kesisen govdelerde
    ic yuzey artigi birakabiliyor; connect bunu temizliyor. Olculdu 0.134 sn.

    IKI MESH ise: katiya cevir -> fuse -> mesh'e geri don (~7 sn, bkz.
    `_mesh_birlestir`). Eskiden bu durumda "iki KATI nesne gerek" deyip
    duruyordu; gunlukte model bunu mesh birlestirici sanip 13 calistirma /
    16 dakika cikmazda dondu. Cagrinin kendisi dogruydu, calismasi gerekiyordu.
    """
    from BOPTools import JoinAPI

    sa, sb = _sekil_al(a), _sekil_al(b)
    if sa is None or sb is None:
        ma, mb = _mesh_al(a), _mesh_al(b)
        if ma is not None and mb is not None:
            return _mesh_birlestir(a, b, ma, mb, azami_facet, yaz)
        if yaz:
            print("birlestir: iki KATI ya da iki MESH nesne gerek "
                  "(biri kati biri mesh ise once kati_yap ile esitle)")
        return None

    # IKI KADEME. connect tercih edilir (ic yuzey artigi birakmaz) ama
    # OLCULDU: mesh kokenli katilarda "There is more than one largest piece!"
    # diye patlayabiliyor — 1740 yuzlu bir kure katisi + kutu denendi,
    # connect patladi, duz fuse ayni isi yapti. Eskiden bu durumda None
    # donuyorduk, yani calisan bir yol dururken model cikmaza giriyordu.
    yol = "connect"
    try:
        sonuc = JoinAPI.connect([sa, sb]).removeSplitter()
    except Exception as e:                                       # noqa: BLE001
        try:
            sonuc = sa.fuse(sb).removeSplitter()
            yol = "fuse"
            if yaz:
                print(f"birlestir: connect olmadi ({e}); duz fuse ile devam")
        except Exception as e2:                                  # noqa: BLE001
            if yaz:
                print(f"birlestir: olmadi (connect: {e} | fuse: {e2})")
            return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Part::Feature",
                          f"{getattr(a, 'Name', 'A')}_birlesik")
    nesne.Shape = sonuc
    for o in (a, b):
        try:
            o.Visibility = False
        except Exception:
            pass
    doc.recompute()

    # BASKI GERCEGI. "1 kati + isValid()" yeterli kanit degil — olculdu,
    # bkz. _kati_baski_gercegi. Sonuc yaz=False iken de hesaplanmiyor:
    # cagiran ciktiyi istemiyorsa maliyeti de odemesin.
    if yaz:
        n = len(sonuc.Solids)
        print(f"{nesne.Name}: {getattr(a, 'Name', '?')} + "
              f"{getattr(b, 'Name', '?')} -> hacim={_sayi(sonuc.Volume)} mm3, "
              f"{n} kati ({yol})")
        if n != 1:
            print(f"    UYARI: {n} ayri kati kaldi — parcalar birbirine "
                  f"DEGMIYOR olabilir. mesafe(a, b) ile bak.")
        if not sonuc.isValid():
            print("    UYARI: sonuc isValid() False")

        durum, sure = _kati_baski_gercegi(sonuc)
        if durum is None:
            print(f"    baski kontrolu KOSAMADI ({sure:.1f} sn) — sonucun "
                  f"basilabilir oldugu DOGRULANMADI")
        else:
            sorunlar = _baski_verdikti(durum)
            if sorunlar:
                print(f"    BASKIYA HAZIR DEGIL ({sure:.1f} sn, "
                      f"{durum.get('facet')} facet):")
                for s in sorunlar:
                    print(f"      - {s}")
                print("      Sekil KATI olarak gecerli ama dilimleyiciye "
                      "giden mesh bozuk. Once bunu duzeltmeden disa aktarma.")
            else:
                print(f"    baskiya hazir: kapali, kesismesiz, tek parca "
                      f"({sure:.1f} sn, {durum.get('facet')} facet)")
    return nesne
