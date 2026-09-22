"""Acik belgeyi metne cevirir.

Simdiden uyulan kural: **secim bolumu en degerli bayttir.** "Su yuzu 3 mm
derinlestir" ancak secili alt-eleman adi (Face7), onu ureten ozellik VE o
yuzun ne oldugu (duzlem mi silindir mi, hangi yone bakiyor, yaricapi ne)
bilindiginde calisir.

OLCUM (caddy_gelisim.txt, kayip 1): en sik tekrar eden kayip buydu. Kullanici
3B'de bir yuz secip "bunu" diyor; modele yalnizca `alt=Face7` gidiyor. Face7'in
duzlem mi silindir mi oldugunu, nereye baktigini, capinin ne oldugunu model
BILMIYOR ve tahmin ediyor. Yanlis tahmin bir tur daha yiyor.

BUTCE DAVRANISI. Eski surum metni sondan kesiyordu; bu, sinira dayanildiginda
once nesne listesinin kuyrugunu, sonra gerekirse secimi kirpiyordu — yani en
degerli bayti en once atiyordu. Yeni davranis: baslik ve secim ASLA kirpilmaz,
kirpma yalnizca nesne listesinden yapilir ve alaka sirasina gore olur
(secili nesneler > secimin komsulari > gerisi). Bu, M3'te planlanan "hop
mesafesine gore siralama"nin ucuz hali.
"""

from __future__ import annotations

import math

import FreeCAD as App

BUTCE = 12_000  # karakter

# Alt eleman ozetinde kullanilan kisa tip adlari. Part'in sinif adlari
# ('Plane', 'Cylinder', ...) zaten kisa ve net; yalnizca uzun olanlar
# kisaltiliyor.
_TIP_KISA = {
    "BSplineSurface": "bspline",
    "SurfaceOfRevolution": "revolution",
    "SurfaceOfExtrusion": "extrusion",
    "BSplineCurve": "bspline",
    "ArcOfCircle": "arc",
    "ArcOfEllipse": "arc_ellipse",
}


def _sayi(x) -> str:
    try:
        v = float(x)
        # -0.0 'i sifira cevir: OCC eksenlerde bunu sikca uretiyor ve
        # 'axis=(-0,-0,-1)' hem cirkin hem de okuyanda "eksi sifir ne
        # demek" diye bir duraklama yaratiyor.
        if v == 0:
            v = 0.0
        return f"{v:.6g}"
    except Exception:
        return str(x)


def _vek(v) -> str:
    try:
        return f"({_sayi(v.x)},{_sayi(v.y)},{_sayi(v.z)})"
    except Exception:
        return ""


def _kutu(o) -> str:
    b = None
    try:
        b = o.Shape.BoundBox
    except Exception:
        # Mesh::Feature'in Shape'i YOKTUR. Eski surumde bu except sessizce
        # bos donuyordu, yani model mesh'in olculerini HIC gormuyordu.
        # Gunlukte modelin kendi cumlesi duruyor (2026-08-20 15:22):
        # "Mesh nesnesinde cap bilgisi context'te yok" — ve bu yuzden bir
        # sayiyi ogrenmek icin belgeye olcum nesnesi uretmisti.
        try:
            b = o.Mesh.BoundBox
        except Exception:
            return ""
    try:
        # BOS sekilde OCC "-inf x -inf" ve 1.8e308 kose veriyor. Bunu
        # baglama yazmak hem gurultu hem yaniltici: model bir olcu gordugunu
        # saniyor. Bos sekil zaten dogrulamada bulgu olarak raporlaniyor.
        if not all(math.isfinite(v) for v in
                   (b.XLength, b.YLength, b.ZLength, b.XMin, b.YMin, b.ZMin)):
            return ""
        return (f"{_sayi(b.XLength)}x{_sayi(b.YLength)}x{_sayi(b.ZLength)} mm"
                f" @({_sayi(b.XMin)},{_sayi(b.YMin)},{_sayi(b.ZMin)})")
    except Exception:
        return ""


def _mesh_ozeti(o) -> str:
    """Mesh nesnesi icin tek satirlik durum. Mesh degilse bos.

    Neden bunlar: facet sayisi "ne kadar buyuk", kapali/parca ise
    "basilabilir mi" sorusunun cevabi. Ucu de bedava (olculdu: 12850
    facet'te toplam 0.01 sn) ve modelin en cok sordugu seyler.
    """
    try:
        m = o.Mesh
        facet = int(m.CountFacets)
    except Exception:
        return ""
    p = [f"mesh facet={facet}"]
    try:
        p.append("kapali" if m.isSolid() else "ACIK(delik var)")
    except Exception:
        pass
    try:
        n = int(m.countComponents())
        if n != 1:
            p.append(f"parca={n}")
    except Exception:
        pass
    return " ".join(p)


def _tip_adi(nesne) -> str:
    ad = type(nesne).__name__
    return _TIP_KISA.get(ad, ad.lower())


def _alt_eleman(o, ad: str):
    """'Face7' -> Part.Face. Bulunamazsa None; ASLA patlamaz."""
    try:
        return o.Shape.getElement(ad)
    except Exception:
        pass
    try:
        return getattr(o.Shape, ad)
    except Exception:
        return None


def _alt_eleman_ozeti(o, ad: str) -> str:
    """Secili yuz/kenarin GEOMETRIK ozeti — tek satir, kisa.

    Ornek ciktilar:
        plane area=1200 normal=(0,0,1)
        cylinder r=4 axis=(0,0,1) area=75.4
        line len=20
        circle r=3 center=(10,0,5)
    """
    e = _alt_eleman(o, ad)
    if e is None:
        return ""

    p: list[str] = []

    yuzey = getattr(e, "Surface", None)
    egri = getattr(e, "Curve", None)

    if yuzey is not None:                       # --- yuz ---
        p.append(_tip_adi(yuzey))
        # Yaricap: silindir/kure/torus'ta dogrudan; koninin iki yaricapi olur.
        for alan, etiket in (("Radius", "r"), ("Radius1", "r1"),
                             ("Radius2", "r2")):
            d = getattr(yuzey, alan, None)
            if d is not None:
                p.append(f"{etiket}={_sayi(d)}")
        eksen = getattr(yuzey, "Axis", None)
        if eksen is not None:
            # Duzlemde Axis normalin ta kendisi; egri yuzeylerde donme ekseni.
            p.append(("normal=" if _tip_adi(yuzey) == "plane" else "axis=")
                     + _vek(eksen))
        merkez = getattr(yuzey, "Center", None)
        if merkez is not None:
            p.append("center=" + _vek(merkez))
        try:
            p.append(f"area={_sayi(e.Area)}")
        except Exception:
            pass

    elif egri is not None:                      # --- kenar ---
        p.append(_tip_adi(egri))
        d = getattr(egri, "Radius", None)
        if d is not None:
            p.append(f"r={_sayi(d)}")
        merkez = getattr(egri, "Center", None)
        if merkez is not None:
            p.append("center=" + _vek(merkez))
        try:
            p.append(f"len={_sayi(e.Length)}")
        except Exception:
            pass

    else:                                       # --- kose ---
        nokta = getattr(e, "Point", None)
        if nokta is not None:
            p.append("vertex=" + _vek(nokta))

    return " ".join(x for x in p if x)


def _yerlesim(o) -> str:
    """Birim olmayan Placement'i yaz. Birim ise sessiz kal — bayt bosa gitmesin."""
    try:
        yer = o.Placement
        taban, donme = yer.Base, yer.Rotation
        bos_taban = taban.Length < 1e-9
        bos_donme = abs(donme.Angle) < 1e-9
        if bos_taban and bos_donme:
            return ""
        parca = []
        if not bos_taban:
            parca.append("pos=" + _vek(taban))
        if not bos_donme:
            parca.append(f"rot={_sayi(donme.Angle * 180.0 / 3.141592653589793)}"
                         f"deg@{_vek(donme.Axis)}")
        return " ".join(parca)
    except Exception:
        return ""


def _secim() -> tuple[list[str], set[str]]:
    """Secili nesneler + alt elemanlar + o elemani ureten ozellik + geometri.

    Doner: (satirlar, secili nesne adlari). Adlar butce kirpmasinda
    onceligi belirlemek icin gerekiyor.
    """
    satir: list[str] = []
    adlar: set[str] = set()
    try:
        import FreeCADGui as Gui
        secimler = Gui.Selection.getSelectionEx()
    except Exception:
        return satir, adlar

    for s in secimler:
        o = s.Object
        adlar.add(o.Name)
        temel = f"  {o.Name} ({o.TypeId}) label={o.Label!r}"

        # Secili nesnenin kendi olcusu ve konumu — "bunu 3 mm buyut"
        # dendiginde neyin buyuyecegini gormek icin.
        ek = []
        k = _kutu(o)
        if k:
            ek.append("bbox=" + k)
        m = _mesh_ozeti(o)
        if m:
            ek.append(m)
        y = _yerlesim(o)
        if y:
            ek.append(y)
        nesne_satiri = temel + (("  " + " ".join(ek)) if ek else "")

        alt = list(s.SubElementNames or ())
        if not alt:
            satir.append(nesne_satiri)
            continue

        satir.append(nesne_satiri)
        for ad in alt:
            iz = ""
            try:
                # Bu yuzu/kenari HANGI ozellik uretti — "sunu degistir"in cevabi
                gecmis = o.getElementHistory(ad)
                if gecmis:
                    iz = (f"  <- {gecmis[0][0].Name}"
                          if hasattr(gecmis[0][0], "Name") else "")
            except Exception:
                pass
            nokta = ""
            try:
                p = s.PickedPoints[alt.index(ad)]
                nokta = f" tiklanan={_vek(p)}"
            except Exception:
                pass
            ozet = _alt_eleman_ozeti(o, ad)
            satir.append(f"    alt={ad}"
                         + (f" {ozet}" if ozet else "")
                         + nokta + iz)
    return satir, adlar


def _komsular(doc, secili: set[str]) -> set[str]:
    """Secimin bir hop otesi: girdileri ve onu kullananlar."""
    yakin: set[str] = set()
    for ad in secili:
        o = doc.getObject(ad)
        if o is None:
            continue
        for liste in ("OutList", "InList"):
            try:
                for x in getattr(o, liste, ()) or ():
                    yakin.add(x.Name)
            except Exception:
                pass
    return yakin - secili


def _kirpma_notu(n: int) -> str:
    return (f"  … {n} nesne butce nedeniyle kirpildi "
            f"(secim ve komsulari korundu)")


# Not satirinin butcedeki yeri. Sayinin kac hane olacagi onceden
# bilinmedigi icin en genis hal olculuyor.
_NOT_PAYI = len(_kirpma_notu(999_999)) + 1


def _nesne_satiri(o) -> str:
    girdi = [f"  {o.Name} ({o.TypeId})"]
    if o.Label and o.Label != o.Name:
        girdi.append(f"label={o.Label!r}")
    k = _kutu(o)
    if k:
        girdi.append(k)
    m = _mesh_ozeti(o)
    if m:
        girdi.append(m)
    try:
        bagli = [x.Name for x in o.OutList]
        if bagli:
            girdi.append("<- " + ",".join(bagli[:4]))
    except Exception:
        pass
    return " ".join(girdi)


def belge_metni(doc=None, butce: int = BUTCE) -> str:
    doc = doc or App.ActiveDocument
    if doc is None:
        return "<document>Acik belge yok.</document>"

    bas: list[str] = ["<document>"]
    basi = f"name={doc.Name} label={doc.Label!r} objects={len(doc.Objects)}"
    # App.Document'ta 'Modified' YOK (1.1'de denendi, AttributeError).
    # Kaydedilmemis degisiklik olup olmadigini isTouched() soyluyor.
    try:
        basi += f" touched={bool(doc.isTouched())}"
    except Exception:
        pass
    bas.append(basi)
    if getattr(doc, "FileName", ""):
        bas.append(f"file={doc.FileName}")

    # GERI ALMA YIGININ TEPESI. Model GERI-AL isteyebiliyor ama yalnizca
    # kendi isini geri alabiliyor; neyin tepede oldugunu gormeden istemek
    # korlemesine olurdu. Ilk uc kayit yetiyor, satir kisa.
    try:
        adlar = list(getattr(doc, "UndoNames", ()) or ())
        if adlar:
            bas.append("undo_stack=" + " | ".join(adlar[:3]))
    except Exception:
        pass

    # Aktif Body — PartDesign'da yeni ozelliklerin nereye gidecegini belirler
    try:
        import FreeCADGui as Gui
        gorunum = Gui.ActiveDocument.ActiveView
        body = gorunum.getActiveObject("pdbody")
        if body is not None:
            bas.append(f"active_body={body.Name}")
    except Exception:
        pass

    sec, secili = _secim()
    bas.append("<selection>")
    bas.extend(sec if sec else ["  (secim yok)"])
    bas.append("</selection>")

    # --- nesne listesi ---------------------------------------------------
    # TopologicalSortedObjects BOS belgede FreeCAD konsoluna
    # "cyclic dependency detected (no root object)" uyarisi basiyor —
    # zararsiz ama her turda Report view'i kirletir. 2'den az nesnede
    # siralamanin zaten anlami yok.
    sirali = doc.Objects
    if len(doc.Objects) > 1:
        try:
            sirali = doc.TopologicalSortedObjects
        except Exception:
            pass

    yakin = _komsular(doc, secili) if secili else set()
    # (oncelik, sira, metin) — oncelik 0 en degerli.
    kayit = []
    for i, o in enumerate(sirali):
        if o.Name in secili:
            oncelik = 0
        elif o.Name in yakin:
            oncelik = 1
        else:
            oncelik = 2
        kayit.append([oncelik, i, _nesne_satiri(o)])

    # Uzunluk TAM hesaplaniyor, tahminen degil: satirlar "\n" ile birlestigi
    # icin her satir kendi uzunlugu + 1, kapanis satiri haric.
    sabit_uzunluk = (sum(len(x) + 1 for x in bas)
                     + len("<objects>") + 1
                     + len("</objects>") + 1
                     + len("</document>"))
    toplam = sabit_uzunluk + sum(len(x[2]) + 1 for x in kayit)

    # Kirpma sirasi: once en dusuk oncelik, o grup icinde EN ESKI nesne.
    # Eskiden basla, cunku belgenin sonu genelde uzerinde calisilan yerdir
    # (PartDesign'da tip, Part'ta son boolean); baslangicta ise origin
    # duzlemleri ve taban eskizler durur — onlarin adlari zaten CLAUDE.md'de
    # yaziyor, baglama tekrar konmalari sart degil.
    atilacak = sorted(range(len(kayit)), key=lambda i: (-kayit[i][0], kayit[i][1]))
    dusen = 0
    for i in atilacak:
        if toplam <= butce:
            break
        if kayit[i][0] == 0:
            break                      # secili nesne ASLA atilmaz
        if dusen == 0:
            # Kirpma notunun KENDISI de butceden yiyor. Ilk olcumde
            # unutuldu ve 1200 istenen yerde 1232 karakter uretildi.
            toplam += _NOT_PAYI
        toplam -= len(kayit[i][2]) + 1
        kayit[i] = None
        dusen += 1

    p = bas + ["<objects>"]
    p.extend(k[2] for k in kayit if k is not None)
    if dusen:
        p.append(_kirpma_notu(dusen))
    p.append("</objects>")
    p.append("</document>")

    metin = "\n".join(p)
    if len(metin) > butce:
        # Buraya ancak SECIM tek basina butceyi asarsa gelinir — nesne
        # listesi bosaltilsa bile sigmiyorsa. Kaba kesme, ama etiketi
        # kapatarak: yarim kalan bir <document> modeli sasirtir.
        kuyruk = "\n… (baglam kirpildi)\n</document>"
        metin = metin[:max(0, butce - len(kuyruk))] + kuyruk
    return metin
