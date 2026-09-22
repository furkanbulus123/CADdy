"""Modelin kod icinden cagirabildigi OLCUM yardimcilari.

NEDEN VAR. Kullanicinin sozu: "olcmesi cok kritik, kullanici surekli
olcemez" ve "caddy direkt olcse daha iyi olur". Gunluk incelemesi
(2026-08-21) iki ayri sorunu ayirmisti:

  1. GERI OKUMA — model olcuyu zaten hesapliyor, geri getiremiyordu.
     print kanaliyla kapandi.
  2. GERCEK OLCME — mesh'te yuz/kenar YOKTUR, yalnizca ucgen vardir.
     "Agiz capi ne kadar" mesh'te HESAPLANMAK zorunda.

HAZIR KOD KULLANILIYOR, ELLE GEOMETRI YAZILMIYOR.
Kullanicinin ikinci uyarisi: "olcum cok zor bir sey, arastir, var olan
kodlar varsa ekle". Arastirildi ve OLCULDU — hepsi zaten elimizde:

  * `Measure.Measurement` (FreeCAD'in KENDI olcum motoru) ARAYUZSUZ
    calisiyor: radius/area/length/angle/delta/lineLineDistance/
    planePlaneDistance. Olculdu: bir delik yuzunde radius() -> 1.7 tam.
    (App.MeasureManager ise konsolda BOS — tipleri GUI kaydediyor,
    o yol kullanilamiyor.)
  * `Shape.distToShape` — iki kati arasi EN KISA mesafe, temas noktalariyla.
  * `Mesh.foraminate(taban, yon)` — bir isinin mesh'i deldigi TUM noktalar.
    Duvar kalinliginin sanayi standardi yontemi (trimesh'in 'ray' yontemi
    de budur). Olculdu: 24 acida tarama 0.010 sn.
  * `Mesh.crossSections` / `Shape.slice` — gercek kesit. Koselere BAGLI
    DEGIL (bkz. _kesit_noktalari, testte yakalanan hata).
  * `Mesh.getEigenSystem` / `Shape.optimalBoundingBox` — nesnenin KENDI
    eksenleri. Yatik bir nesne icin "yukseklik" ancak boyle dogru olcuyor.
  * numpy 1.26 + scipy 1.16 FreeCAD'in icinde VAR (olculdu). scipy'nin
    cKDTree'si mesh-mesh mesafeyi 3542x3542 nokta icin 0.032 sn'de
    veriyor; kaba kuvvet ayni is icin 3.9 sn suruyordu (120 kat).
  * Taubin cember uydurma (numpy, 15 satir) — noktadan cap cikarmanin
    literaturdeki standart yolu. Merkezi ortalamayla bulmak KULPLU bir
    kesitte kayiyor: olculdu, dogru merkez (5,-3) iken ortalama (6.30,-3),
    Taubin (5.80,-3), aykiri nokta atildiktan sonra tam.

Hepsi print ediyor: cikti otomatik olarak modele donuyor.

KATMAN KURALI (MANTIK 12): burada Qt YOK.
"""

from __future__ import annotations

import math

import FreeCAD as App


def _np():
    """numpy — yoksa None. Olcumun tamami buna bagli olmamali."""
    try:
        import numpy
        return numpy
    except Exception:
        return None


def _sayi(x) -> str:
    """Insanin okuyacagi sayi. BILIMSEL GOSTERIM URETMEZ.

    OLCULDU (LOG/2026-08-28_c503a8a4.txt): bulgu satiri "ortak hacim
    5.791e+04 mm3" diye ciktı ve model onu "kasitli baglanti gecmesi"
    diye gecti. Ayni sayi "57906 mm3" yazilsaydi ampulun tamaminin
    gomulu oldugu daha gorunur olurdu. `%.4g` 10 000'den sonra ussel
    gosterime geciyordu; CAD'de mm3 degerleri rutin olarak orada.
    """
    try:
        v = float(x)
        if v == 0:
            v = 0.0
        if abs(v) >= 10000:
            return f"{v:.0f}"
        return f"{v:.4g}"
    except Exception:
        return str(x)


def _mesh_al(nesne):
    try:
        m = nesne.Mesh
        return m if hasattr(m, "CountFacets") else None
    except Exception:
        return None


def _sekil_al(nesne):
    try:
        s = nesne.Shape
        return s if hasattr(s, "BoundBox") else None
    except Exception:
        return None


def _hedef(nesne):
    """Verilen nesne, yoksa secili, o da yoksa belgedeki tek nesne."""
    if nesne is not None:
        return nesne
    try:
        import FreeCADGui as Gui

        secili = Gui.Selection.getSelection()
        if secili:
            return secili[0]
    except Exception:
        pass
    doc = App.ActiveDocument
    if doc is None:
        return None
    adaylar = [o for o in doc.Objects
               if _mesh_al(o) is not None or _sekil_al(o) is not None]
    return adaylar[0] if len(adaylar) == 1 else None


def _kutu(nesne):
    for al in (lambda: nesne.Mesh.BoundBox, lambda: nesne.Shape.BoundBox):
        try:
            return al()
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# 1. TEMEL OLCU
# --------------------------------------------------------------------------

def _kendi_boyu(nesne):
    """Nesnenin KENDI eksenlerindeki boyu (uc sayi) ya da None.

    NEDEN GEREKLI. Eksene hizali bbox yatik bir parcayi oldugundan buyuk
    gosterir: 30x10x5 bir kutu 30 derece dondurulunce bbox 28.5x10x19.3
    olur ve "kalinligi 19 mm" demek yanlistir.

    YONTEM. Mesh'te `getEigenSystem()` bunu HAZIR veriyor (FreeCAD'in
    kendi kodu; olculdu, kupada 55.35x95x55.38).
    Katida `optimalBoundingBox()` DENENDI ve ELENDI: 30 derece
    dondurulmus kutu icin 28.48x10x19.33 dondu, yani hala EKSENE HIZALI.
    Onun yerine `PrincipalProperties`in atalet eksenlerine (bunlar
    prizmatik bir parcada parcanin kendi eksenleridir — olculdu, donuk
    kutuda FirstAxisOfInertia = (0.5, 0, 0.866)) koseler izdusuruluyor.
    """
    m = _mesh_al(nesne)
    if m is not None:
        try:
            _, boy = m.getEigenSystem()
            return (boy.x, boy.y, boy.z)
        except Exception:
            return None

    s = _sekil_al(nesne)
    if s is None:
        return None
    try:
        p = s.PrincipalProperties
        eksenler = [p["FirstAxisOfInertia"], p["SecondAxisOfInertia"],
                    p["ThirdAxisOfInertia"]]
        noktalar = [v.Point for v in s.Vertexes]
        if len(noktalar) < 2:
            kose, _ = s.tessellate(0.5)
            noktalar = list(kose)
        if not noktalar:
            return None
        boy = []
        for e in eksenler:
            izd = [n.x * e.x + n.y * e.y + n.z * e.z for n in noktalar]
            boy.append(max(izd) - min(izd))
        return tuple(boy)
    except Exception:
        return None


def olc(nesne=None, yaz: bool = True) -> dict:
    """Nesnenin temel olculeri: boy, merkez, hacim, alan, mesh durumu.

    `nesne` verilmezse secili nesne, o da yoksa belgedeki tek nesne.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("olc: olculecek nesne bulunamadi "
                  "(ad ver: olc(doc.getObject('kupa')))")
        return {}

    d: dict = {"ad": getattr(nesne, "Name", "?")}
    satir = [f"{d['ad']}:"]

    b = _kutu(nesne)
    if b is not None:
        d.update(boy=(b.XLength, b.YLength, b.ZLength),
                 merkez=(b.Center.x, b.Center.y, b.Center.z),
                 z_alt=b.ZMin, z_ust=b.ZMax)
        satir.append(f"boy={_sayi(b.XLength)}x{_sayi(b.YLength)}"
                     f"x{_sayi(b.ZLength)} mm")
        satir.append(f"merkez=({_sayi(b.Center.x)},{_sayi(b.Center.y)},"
                     f"{_sayi(b.Center.z)})")
        satir.append(f"z={_sayi(b.ZMin)}..{_sayi(b.ZMax)}")

    # Eksene hizali bbox ile kendi ekseni FARKLIYSA soyle: nesne yatik
    # demektir ve bu, sonraki her olcumu etkiler.
    kendi = _kendi_boyu(nesne)
    if kendi and b is not None:
        hizali = sorted([b.XLength, b.YLength, b.ZLength])
        oz = sorted(kendi)
        d["kendi_boy"] = tuple(kendi)
        if any(abs(x - y) > max(0.02 * max(x, y, 1e-9), 0.1)
               for x, y in zip(hizali, oz)):
            d["yatik"] = True
            satir.append(f"(YATIK — kendi ekseninde {_sayi(oz[2])}x"
                         f"{_sayi(oz[1])}x{_sayi(oz[0])} mm)")

    m = _mesh_al(nesne)
    if m is not None:
        for ad, cagri in (("hacim", lambda: m.Volume),
                          ("alan", lambda: m.Area),
                          ("facet", lambda: m.CountFacets),
                          ("parca", lambda: m.countComponents())):
            try:
                v = cagri()
                d[ad] = v
                satir.append(f"{ad}={_sayi(v)}")
            except Exception:
                pass
        try:
            d["kapali"] = bool(m.isSolid())
            satir.append("kapali" if d["kapali"] else "ACIK")
        except Exception:
            pass
    else:
        s = _sekil_al(nesne)
        if s is not None:
            try:
                d["hacim"] = s.Volume
                d["alan"] = s.Area
                satir.append(f"hacim={_sayi(s.Volume)} mm3")
                satir.append(f"alan={_sayi(s.Area)} mm2")
                satir.append(f"kati={len(s.Solids)} yuz={len(s.Faces)} "
                             f"kenar={len(s.Edges)}")
            except Exception:
                pass

    d["satir"] = " ".join(satir)
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 2. KESIT / CAP
# --------------------------------------------------------------------------

def _kesit_noktalari(nesne, z: float) -> list:
    """z duzlemindeki GERCEK kesit noktalari.

    NEDEN NOKTA BANDI DEGIL. Ilk surum "z'ye yakin mesh koselerini topla"
    diyordu ve TEST BUNU YAKALADI: koni gibi bir govdede mesh tabandan
    tepeye uzanan uzun ucgenlerden olusuyor, ara yuksekliklerde HIC kose
    yok, olcum sessizce bos donuyordu. Yani yontem mesh'in nasil
    ucgenlendigine bagliydi; olcum buna bagli olamaz.

    Dogrusu duzlemle gercek kesisim: mesh'te `crossSections` (olculdu:
    1558 facet'te 0.033 sn), katida `Shape.slice`.
    """
    from FreeCAD import Vector

    m = _mesh_al(nesne)
    if m is not None:
        try:
            kesitler = m.crossSections([((0, 0, z), (0, 0, 1))], 0.0)
            noktalar = [p for kesit in kesitler for pl in kesit for p in pl]
            if noktalar:
                return noktalar
        except Exception:
            pass

    s = _sekil_al(nesne)
    if s is not None:
        try:
            noktalar = []
            for t in s.slice(Vector(0, 0, 1), z):
                try:
                    noktalar.extend(t.discretize(Distance=0.5))
                except Exception:
                    noktalar.extend(v.Point for v in t.Vertexes)
            return noktalar
        except Exception:
            return []
    return []


def _taubin(xs, ys):
    """Taubin cember uydurma — noktalardan merkez ve yaricap.

    Literaturun standart cebirsel yontemi (Taubin 1991); Kasa'nin kucuk
    yaricaba kayma egilimini duzeltir. numpy yoksa None doner ve cagiran
    ortalamaya duser.

    NEDEN ORTALAMA YETMIYOR: kesitte kulp gibi bir cikinti varsa merkez
    ona dogru kayar. OLCULDU — gercek merkez (5,-3), ortalama (6.30,-3),
    Taubin (5.80,-3), aykiri nokta atildiktan sonra tam.
    """
    np = _np()
    if np is None:
        return None
    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    if len(x) < 5:
        return None
    mx, my = x.mean(), y.mean()
    u, v = x - mx, y - my
    z = u * u + v * v
    zm = z.mean()
    if zm <= 0:
        return None
    kok = math.sqrt(zm)
    A = np.column_stack([(z - zm) / (2 * kok), u, v])
    try:
        _, _, V = np.linalg.svd(A, full_matrices=False)
    except Exception:
        return None
    a = V[-1]
    A0 = a[0] / (2 * kok)
    B, C = a[1], a[2]
    D = -zm * a[0] / (2 * kok)
    if abs(A0) < 1e-12:
        return None
    kok2 = B * B + C * C - 4 * A0 * D
    if kok2 <= 0:
        return None
    return (-B / (2 * A0) + mx, -C / (2 * A0) + my,
            math.sqrt(kok2) / (2 * abs(A0)))


def _merkez_bul(noktalar):
    """Kesitin merkezi — Taubin + bir aykiri-atma turu, olmazsa ortalama."""
    np = _np()
    xs = [p.x for p in noktalar]
    ys = [p.y for p in noktalar]
    ortalama = (sum(xs) / len(xs), sum(ys) / len(ys))
    uygun = _taubin(xs, ys)
    if uygun is None or np is None:
        return ortalama

    cx, cy, r = uygun

    # DEJENERE UYDURMA KORUMASI. Noktalar neredeyse DOGRUSALSA (yatik bir
    # silindirin yatay kesiti iki paralel cizgidir) cembersel uydurma
    # kocaman bir cember bulur ve merkezi cok uzaga atar. TESTTE OLDU:
    # yaricap 7.8e8, merkez (1.2e6, 3.9e8) — ve bu, kesiti "dairesel"
    # gosterdigi icin sessizce yanlis bir cap raporlaniyordu.
    # Uydurulan yaricap nokta bulutunun kendi buyuklugunden cok buyukse
    # uydurma anlamsizdir; ortalamaya donuyoruz ve yuvarlaklik kontrolu
    # (bkz. kesit_capi) devreye girip "YUVARLAK DEGIL" diyor.
    yayilim = max(max(xs) - min(xs), max(ys) - min(ys))
    if not (r == r) or r > 3 * max(yayilim, 1e-9):
        return ortalama
    x = np.asarray(xs)
    y = np.asarray(ys)
    sapma = np.abs(np.hypot(x - cx, y - cy) - r)
    esik = 2.0 * sapma.std() if sapma.std() > 0 else None
    if esik:
        kalan = sapma <= esik
        if kalan.sum() >= max(8, 0.5 * len(xs)):
            ikinci = _taubin(x[kalan], y[kalan])
            if ikinci is not None:
                return ikinci[0], ikinci[1]
    return cx, cy


def kesit_capi(nesne=None, z=None, band=None, yaz: bool = True) -> dict:
    """Verilen yukseklikte KESIT olcusu.

    UC DURUMU AYIRT EDER, cunku ucune ayni sayiyi vermek yanlis olur:

      * TEK HALKA, dairesel       -> tek cap
      * TEK HALKA, oval           -> KISA ve UZUN cap ayri ayri. Ovalin
                                     tek capi yoktur; ortalama ovali daire
                                     sanar.
      * IKI HALKA (ici bos govde) -> DIS cap, IC cap, DUVAR kalinligi.
                                     Kupa/boru kesitinde olan budur.
      * YUVARLAK DEGIL            -> "cap" demeyi REDDEDER, en genis/en dar
                                     olcuyu verir. Yatik nesnede olan budur.

    z verilmezse nesnenin USTU olculur (agiz). `band` artik kullanilmiyor
    (gercek kesit aliniyor); geriye donuk uyum icin kabul ediliyor.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("kesit_capi: nesne bulunamadi")
        return {}

    kutu = _kutu(nesne)
    if kutu is None:
        if yaz:
            print(f"kesit_capi: {getattr(nesne, 'Name', '?')} olculemiyor "
                  f"(ne mesh ne kati)")
        return {}

    if z is None:
        # Tam tepede kesit BOS cikar (duzlem govdeye tegettir); bir tik
        # asagisi "agiz" olcusunu verir.
        z = kutu.ZMax - max(kutu.ZLength * 0.02, 0.01)

    noktalar = _kesit_noktalari(nesne, z)
    ad = getattr(nesne, "Name", "?")
    if len(noktalar) < 8:
        if yaz:
            print(f"kesit_capi: z={_sayi(z)} duzleminde kesit bulunamadi "
                  f"({len(noktalar)} nokta). Nesne bu yukseklikte yok ya da "
                  f"z araligi {_sayi(kutu.ZMin)}..{_sayi(kutu.ZMax)} disinda.")
        return {}

    cx, cy = _merkez_bul(noktalar)

    # ACIYA GORE KOVALAMA: her acida kac ayri yaricap var? Bir tane ise
    # tek halka, iki ise duvar.
    KOVA = 72                                    # 5 derecelik dilimler
    kovalar: dict[int, list[float]] = {}
    for p in noktalar:
        dx, dy = p.x - cx, p.y - cy
        r = math.hypot(dx, dy)
        i = int((math.atan2(dy, dx) + math.pi) / (2 * math.pi) * KOVA) % KOVA
        kovalar.setdefault(i, []).append(r)

    dis_r = [max(v) for v in kovalar.values()]
    ic_r = [min(v) for v in kovalar.values()]
    if not dis_r:
        return {}

    en_dis = max(dis_r)
    kalinliklar = sorted(d - i for d, i in zip(dis_r, ic_r))
    orta_kalinlik = kalinliklar[len(kalinliklar) // 2]

    d = {"z": z, "merkez": (cx, cy), "nokta": len(noktalar),
         "dis_cap": 2 * en_dis}

    if orta_kalinlik > max(0.02 * en_dis, 0.05):
        d["duvar"] = orta_kalinlik
        d["ic_cap"] = 2 * (en_dis - orta_kalinlik)
        d["tur"] = "duvar"
        d["guvenilir"] = True
        d["satir"] = (f"{ad} kesit z={_sayi(z)}: dis cap={_sayi(2 * en_dis)} "
                      f"ic cap={_sayi(d['ic_cap'])} "
                      f"duvar={_sayi(orta_kalinlik)} mm "
                      f"merkez=({_sayi(cx)},{_sayi(cy)})")
        if yaz:
            print(d["satir"])
        return d

    kucuk, buyuk = min(dis_r), max(dis_r)
    ort = sum(dis_r) / len(dis_r)
    d.update(kisa_cap=2 * kucuk, uzun_cap=2 * buyuk, ort_cap=2 * ort)

    # YUVARLAK MI? "Cap" ancak kesit Z ekseni etrafinda yuvarlaksa anlamli.
    # Nesne YATIKSA yatay dilim halka degil iki paralel cizgidir; sayilar
    # yine cikar ama "cap" demek yalan olur. Ilk surumde tam bu oldu ve
    # test yakaladi: "kisa cap = 0.0000000001".
    if kucuk > 0 and buyuk / kucuk > 2.5:
        d["guvenilir"] = False
        d["tur"] = "yuvarlak degil"
        d["satir"] = (f"{ad} kesit z={_sayi(z)}: bu kesit YUVARLAK DEGIL "
                      f"(en/boy orani {_sayi(buyuk / kucuk)}), 'cap' anlamli "
                      f"bir olcu degil. En genis {_sayi(2 * buyuk)}, en dar "
                      f"{_sayi(2 * kucuk)} mm. Nesne Z'de durmuyor olabilir; "
                      f"olc() ile kendi eksenine bak.")
        if yaz:
            print(d["satir"])
        return d

    d["guvenilir"] = True
    if buyuk - kucuk <= max(0.02 * buyuk, 0.05):
        d["tur"] = "daire"
        d["satir"] = (f"{ad} kesit z={_sayi(z)}: cap={_sayi(2 * ort)} mm "
                      f"(dairesel) merkez=({_sayi(cx)},{_sayi(cy)})")
    else:
        d["tur"] = "oval"
        d["satir"] = (f"{ad} kesit z={_sayi(z)}: kisa cap={_sayi(2 * kucuk)} "
                      f"uzun cap={_sayi(2 * buyuk)} ortalama={_sayi(2 * ort)} "
                      f"mm merkez=({_sayi(cx)},{_sayi(cy)})")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 3. DUVAR KALINLIGI (isin atma — sanayi standardi)
# --------------------------------------------------------------------------

def duvar_kalinligi(nesne=None, z=None, yaz: bool = True) -> dict:
    """Isin atarak duvar kalinligi. Baskiya uygunlugun asil sorusu.

    YONTEM: mesh'in `foraminate(taban, yon)` metodu bir isinin deldigi TUM
    noktalari veriyor. Eksenden disari dogru bir isin, once IC yuzeyi sonra
    DIS yuzeyi deler; ikisinin farki o noktadaki duvardir. trimesh'in
    'ray' yontemi de aynen budur; burada FreeCAD'in kendi kodu kullaniliyor
    (olculdu: 24 acida tarama 0.010 sn).

    En INCE yer raporlaniyor, ortalama degil: baski o noktada patlar.
    """
    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("duvar_kalinligi: yalnizca mesh nesnelerde calisir "
                  "(kati icin kesit_capi kullan)")
        return {}

    b = m.BoundBox
    if z is None:
        z = b.ZMin + b.ZLength * 0.5
    merkez_x, merkez_y = b.Center.x, b.Center.y

    olcumler = []
    for derece in range(0, 360, 10):
        a = math.radians(derece)
        yon = (math.cos(a), math.sin(a), 0.0)
        try:
            vurus = m.foraminate((merkez_x, merkez_y, z), yon)
        except Exception:
            continue
        # Isin yonundeki ISARETLI uzakliklar. hypot ile mutlak uzaklik
        # almak, isinin ARKA tarafindaki vuruslari one karistirir ve
        # kalinligi sifira yaklastirir — ilk denemede tam bu oldu
        # (ortanca 0.045 mm cikmisti, dogrusu 2.1).
        t = []
        for v in vurus.values():
            uz = ((v[0] - merkez_x) * yon[0] + (v[1] - merkez_y) * yon[1])
            if uz > 1e-6:
                t.append(uz)
        t = sorted(t)
        # Ayni noktayi paylasan facetler tekrar veriyor: yakinlari birlestir.
        temiz = []
        for x in t:
            if not temiz or x - temiz[-1] > 1e-3:
                temiz.append(x)
        if len(temiz) >= 2:
            olcumler.append((temiz[1] - temiz[0], derece))

    if not olcumler:
        if yaz:
            print(f"duvar_kalinligi: z={_sayi(z)} yuksekliginde duvar "
                  f"bulunamadi (govde ici dolu olabilir)")
        return {}

    olcumler.sort()
    en_ince, aci = olcumler[0]
    ortanca = olcumler[len(olcumler) // 2][0]
    d = {"z": z, "en_ince": en_ince, "en_ince_aci": aci, "ortanca": ortanca,
         "olcum": len(olcumler)}
    d["satir"] = (f"{getattr(nesne, 'Name', '?')} duvar z={_sayi(z)}: "
                  f"en ince {_sayi(en_ince)} mm ({aci} derecede), "
                  f"ortanca {_sayi(ortanca)} mm, {len(olcumler)} olcum")
    if yaz:
        print(d["satir"])
        if en_ince < 0.8:
            print(f"    UYARI: {_sayi(en_ince)} mm cogu 3B yazicinin "
                  f"nozul capinin altinda — o bolge basilamaz ya da bosluk "
                  f"kalir.")
    return d


# --------------------------------------------------------------------------
# 4. IKI NESNE ARASI MESAFE
# --------------------------------------------------------------------------

def mesafe(a=None, b=None, yaz: bool = True) -> dict:
    """Iki nesne arasi EN KISA mesafe. "Degiyorlar mi" sorusunun cevabi.

    Kati-kati: `Shape.distToShape` — tam sonuc, temas noktalariyla birlikte
    (FreeCAD/OCC'nin kendi kodu).
    Mesh iceren durum: scipy `cKDTree` ile en yakin nokta ciftleri. Kaba
    kuvvet 3542x3542 nokta icin 3.9 sn suruyordu, cKDTree 0.032 sn —
    120 kat (olculdu). Sonuc NOKTA BAZLI, yani ucgen yuzeyinin ortasina
    denk gelen bir temasi biraz buyuk gosterebilir; bu, cevabi
    "degiyor mu" duzeyinde dogru tutar ve boyle raporlaniyor.
    """
    if a is None or b is None:
        if yaz:
            print("mesafe: iki nesne ver — mesafe(doc.getObject('a'), "
                  "doc.getObject('b'))")
        return {}

    sa, sb = _sekil_al(a), _sekil_al(b)
    if sa is not None and sb is not None:
        try:
            uzunluk, noktalar, _ = sa.distToShape(sb)
            d = {"mesafe": uzunluk, "yontem": "distToShape"}
            p1, p2 = noktalar[0]
            d["satir"] = (f"{a.Name} <-> {b.Name}: {_sayi(uzunluk)} mm "
                          f"(en yakin noktalar ({_sayi(p1.x)},{_sayi(p1.y)},"
                          f"{_sayi(p1.z)}) ve ({_sayi(p2.x)},{_sayi(p2.y)},"
                          f"{_sayi(p2.z)}))")
            if yaz:
                print(d["satir"])
                if uzunluk < 1e-7:
                    print("    degiyorlar (mesafe sifir).")
            return d
        except Exception:
            pass

    np = _np()
    try:
        from scipy.spatial import cKDTree
    except Exception:
        cKDTree = None

    def noktalari(o):
        m = _mesh_al(o)
        if m is not None:
            return [(p.x, p.y, p.z) for p in m.Points]
        s = _sekil_al(o)
        if s is None:
            return []
        try:
            kose, _ = s.tessellate(0.5)
            return [(p.x, p.y, p.z) for p in kose]
        except Exception:
            return [(v.Point.x, v.Point.y, v.Point.z) for v in s.Vertexes]

    pa, pb = noktalari(a), noktalari(b)
    if not pa or not pb:
        if yaz:
            print("mesafe: nesnelerin noktalari okunamadi")
        return {}

    if cKDTree is not None and np is not None:
        agac = cKDTree(np.asarray(pb))
        uzakliklar, _ = agac.query(np.asarray(pa), k=1)
        en_kisa = float(uzakliklar.min())
    else:
        en_kisa = min(
            math.dist(p, q) for p in pa[::max(1, len(pa) // 400)]
            for q in pb[::max(1, len(pb) // 400)])

    d = {"mesafe": en_kisa, "yontem": "nokta bazli (mesh)"}
    d["satir"] = (f"{getattr(a, 'Name', 'a')} <-> {getattr(b, 'Name', 'b')}: "
                  f"~{_sayi(en_kisa)} mm (mesh noktalari arasi; ucgen "
                  f"yuzeyinin ortasina denk gelen temasi biraz buyuk "
                  f"gosterebilir)")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 5. SECILEN YUZ/KENARIN OLCUSU — FreeCAD'in kendi motoru
# --------------------------------------------------------------------------

def olcu(nesne=None, alt: str = "", yaz: bool = True) -> dict:
    """Bir yuz/kenarin yaricapi, alani, uzunlugu — Measure.Measurement ile.

    Bu FreeCAD'in KENDI olcum motoru ve arayuzsuz calisiyor (olculdu: bir
    delik yuzunde radius() -> 1.7 tam). Delik capini elle uydurmak yerine
    dogrudan buradan sormak lazim.

    `alt` verilmezse secimdeki alt eleman kullanilir.
    """
    try:
        import Measure
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"olcu: Measure modulu yok ({e})")
        return {}

    if nesne is None or not alt:
        try:
            import FreeCADGui as Gui

            secim = Gui.Selection.getSelectionEx()
            if secim and secim[0].SubElementNames:
                nesne = nesne or secim[0].Object
                alt = alt or secim[0].SubElementNames[0]
        except Exception:
            pass
    if nesne is None or not alt:
        if yaz:
            print("olcu: nesne ve alt eleman gerek — "
                  "olcu(doc.getObject('Kutu'), 'Face7')")
        return {}

    m = Measure.Measurement()
    try:
        m.addReference3D(nesne.Name, alt)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"olcu: {alt} eklenemedi ({e})")
        return {}

    d = {"nesne": nesne.Name, "alt": alt}
    parcalar = []
    for ad, cagri in (("yaricap", m.radius), ("uzunluk", m.length),
                      ("alan", m.area)):
        try:
            v = float(cagri())
        except Exception:
            continue
        if v and v == v:                       # NaN degil
            d[ad] = v
            parcalar.append(f"{ad}={_sayi(v)}")
            if ad == "yaricap":
                parcalar.append(f"cap={_sayi(2 * v)}")
    d["satir"] = f"{nesne.Name}.{alt}: " + (" ".join(parcalar) or "olculemedi")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 6. CAKISMA — "degiyor mu, icinden geciyor mu" sorusunun DETERMINISTIK cevabi
# --------------------------------------------------------------------------

# Hacim esigi: OCC boolean'i teget yuzeylerde sifira cok yakin ama sifirdan
# farkli hacimler dondurebiliyor. 1e-3 mm3, 0.1x0.1x0.1 mm'lik bir kupten
# kucuk — gercek bir cakismanin altina dusmez.
_HACIM_ESIGI = 1e-3
# Kesisme egrisi uzunlugu esigi: iki yuzey gercekten kesisiyorsa section()
# uzunlugu olan kenarlar dondurur. Tek noktada tegetlik sifir uzunluk verir.
_KESIT_ESIGI = 1e-6
# Mesafe sifir sayilma esigi (distToShape'in sayisal gurultusu).
_TEMAS_ESIGI = 1e-7


def _bbox_kesisiyor_mu(a, b, pay: float = 0.0) -> bool:
    """Iki nesnenin sinir kutulari ust uste mi. UCUZ on eleme.

    Neden sart: n nesne icin n*(n-1)/2 cift var ve her boolean cagrisi
    OCC'de pahali. 52 nesnelik bir belgede 1326 cift demek; bbox testi
    bunlarin ezici cogunlugunu mikrosaniyede eliyor.
    """
    ka, kb = _kutu(a), _kutu(b)
    if ka is None or kb is None:
        return True              # bilmiyorsak elemiyoruz, olcum karar versin
    return not (ka.XMax + pay < kb.XMin or kb.XMax + pay < ka.XMin
                or ka.YMax + pay < kb.YMin or kb.YMax + pay < ka.YMin
                or ka.ZMax + pay < kb.ZMin or kb.ZMax + pay < ka.ZMin)


def _kati_mi(sekil) -> bool:
    """Sekil hacimli mi (kati) yoksa kalinliksiz mi (yuzey/kabuk/tel)."""
    try:
        return bool(sekil.Solids) and abs(sekil.Volume) > _HACIM_ESIGI
    except Exception:                                            # noqa: BLE001
        return False


def _sinirda_mi(nokta, sekil) -> bool:
    """Nokta seklin KENARINDA mi (yani ic degil, sinir).

    Neden gerekli: iki yuzey uc uca DEGDIGINDE de `section()` uzunlugu olan
    bir egri dondurur (olculdu: 10 mm). Degme ile GECME'yi ayiran sey,
    kesisme egrisinin seklin ICINDE mi yoksa SINIRINDA mi oldugu.
    """
    try:
        import Part as _Part

        kenarlar = sekil.Edges
        if not kenarlar:
            return False
        return _Part.Compound(kenarlar).distToShape(
            _Part.Vertex(nokta))[0] < 1e-6
    except Exception:                                            # noqa: BLE001
        return False


def _egri_ici_geciyor_mu(kesit, sa, sb) -> bool:
    """Kesisme egrisi iki seklin EN AZ BIRININ ici boyunca mi gidiyor.

    Ikisinin de sinirindaysa bu bir DEGME'dir (uc uca, kenar kenara) ve bu
    projede kusur degil. Birinin icindeyse gecistir — logdaki vaka tam
    buydu: "her flogun direge giden KENARI bu seritlerden birini kesiyor",
    yani A'nin siniri B'nin icinden geciyor.
    """
    for e in kesit.Edges:
        try:
            orta = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
        except Exception:                                        # noqa: BLE001
            continue
        if not (_sinirda_mi(orta, sa) and _sinirda_mi(orta, sb)):
            return True
    return False


def _cift_olc(a, b) -> dict:
    """Tek cift icin olcum — sekil TURUNE gore dogru test secilir.

    OLCULDU (LOG/2026-08-26_34ac9988.txt, MANTIK 39) ve burada gercek OCC
    geometrisiyle ayrica olculdu:

      kati x kati    -> `common().Volume`. Yan yana DEGEN iki kutuda hacim 0
                        ama `section()` 40 mm veriyor; yani section bu
                        durumda YANILTIR, hacim yanilmaz.
      kati x yuzey   -> `common()` ALAN dondurur; ama yuzey tam da katinin
                        bir yuzune yatiyorsa da alan dondurur (olculdu: iki
                        halde de 100 mm2). Ayrimi `isInside` yapiyor: ortak
                        parcanin agirlik merkezi katinin GERCEKTEN icinde mi.
      yuzey x yuzey  -> `section()` egrisi; degme ile gecmeyi ayirmak icin
                        egrinin ikisinin de SINIRINDA olup olmadigina
                        bakiliyor (bkz. _egri_ici_geciyor_mu).

    Her halde `distToShape` de olculuyor: "degiyor mu" sorusunun cevabi o.

    Doner: {"hukum", "mesafe", "hacim", "kesit_uzunluk", "satir", "gecis"}
    """
    sa, sb = _sekil_al(a), _sekil_al(b)
    ad_a = getattr(a, "Name", "a")
    ad_b = getattr(b, "Name", "b")
    d: dict = {"a": ad_a, "b": ad_b, "hacim": 0.0, "kesit_uzunluk": 0.0,
               "gecis": False}

    if sa is None or sb is None:
        # Mesh tarafi: common/section YOK. Yalnizca mesafe olculebiliyor ve
        # bu SOYLENIYOR — "olcemedigini uydurma" kurali.
        m = mesafe(a, b, yaz=False)
        if not m:
            d["hukum"] = "olculemedi"
            d["mesafe"] = float("nan")
            d["satir"] = f"{ad_a} <-> {ad_b}: olculemedi (sekil de mesh de yok)"
            return d
        d["mesafe"] = m.get("mesafe", 0.0)
        d["hukum"] = "degiyor" if d["mesafe"] < _TEMAS_ESIGI else "ayri"
        d["satir"] = (f"{ad_a} <-> {ad_b}: {_sayi(d['mesafe'])} mm "
                      f"(mesh — gecis testi KOSMADI, yalnizca mesafe)")
        return d

    try:
        d["mesafe"] = float(sa.distToShape(sb)[0])
    except Exception:                                            # noqa: BLE001
        d["mesafe"] = float("nan")

    kati_a, kati_b = _kati_mi(sa), _kati_mi(sb)
    ortak = None
    try:
        ortak = sa.common(sb)
        d["hacim"] = float(getattr(ortak, "Volume", 0.0) or 0.0)
        d["ortak_alan"] = float(getattr(ortak, "Area", 0.0) or 0.0)
    except Exception:                                            # noqa: BLE001
        d["hacim"] = 0.0
        d["ortak_alan"] = 0.0

    kesit = None
    try:
        kesit = sa.section(sb)
        d["kesit_uzunluk"] = float(sum(e.Length for e in kesit.Edges))
    except Exception:                                            # noqa: BLE001
        d["kesit_uzunluk"] = 0.0

    nasil: list[str] = []
    if kati_a and kati_b:
        # Hacim yanilmaz; section bu durumda temas egrisini de dondurur.
        if d["hacim"] > _HACIM_ESIGI:
            d["gecis"] = True
            nasil.append(f"ortak hacim {_sayi(d['hacim'])} mm3")
            # KUSURUN BUYUKLUGU — ham hacim bunu SOYLEMIYOR.
            # OLCULDU (LOG/2026-08-28_c503a8a4.txt): "ortak hacim 5.791e+04
            # mm3" satirini model "kasitli baglanti gecmesi" diye gecti.
            # Oysa o hacim ampulun TAMAMIYDI: ampul abajurun icine gomulu,
            # yani abajur ici bos olmasi gerekirken dolu koniydi. Ayni
            # oturumda 2872 mm3'luk bir mafsal gecmesi gercekten kasitliydi.
            # Iki durumu ayiran sey hacmin BUYUKLUGU degil, kucuk parcanin
            # ne kadarinin yutuldugu. O oran olmadan model dogru karari
            # ancak sansla veriyor.
            try:
                ha, hb = float(sa.Volume), float(sb.Volume)
                kucuk = min(ha, hb)
                ad_kucuk = ad_a if ha <= hb else ad_b
                if kucuk > 0:
                    oran = d["hacim"] / kucuk
                    d["oran"] = oran
                    d["oran_nesne"] = ad_kucuk
                    yuzde = oran * 100
                    if oran >= 0.98:
                        nasil.append(f"{ad_kucuk} TAMAMEN GOMULU "
                                     f"(hacminin %100'u iceride)")
                    elif yuzde < 1.0:
                        # "%0'i" YAZMAYACAGIZ. Olculdu
                        # (LOG/2026-08-28_88ba806a.txt): 237.8 mm3'luk
                        # gercek bir gecis "AltKol hacminin %0'i" diye
                        # ciktı — yuvarlama sifira dusurdu ve satir
                        # "cakisma yok" gibi okunuyor. Kusuru raporlarken
                        # onu YOK gosteren bir sayi yazmak, raporun
                        # kendisini bozar.
                        nasil.append(f"{ad_kucuk} hacminin %1'inden azi")
                    else:
                        nasil.append(f"{ad_kucuk} hacminin %{yuzde:.0f}'i")
            except Exception:                                    # noqa: BLE001
                pass
    elif kati_a or kati_b:
        # Yuzeyin ne kadari katinin ICINDE. Yuze yatan yuzey de alan verir,
        # o yuzden ortak parcanin merkezi gercekten iceride mi diye bakiyoruz.
        kati_sekil = sa if kati_a else sb
        if ortak is not None and d.get("ortak_alan", 0.0) > _KESIT_ESIGI:
            iceride = False
            try:
                for f in ortak.Faces:
                    if kati_sekil.isInside(f.CenterOfMass, 1e-7, False):
                        iceride = True
                        break
            except Exception:                                    # noqa: BLE001
                iceride = True          # karar veremiyorsak sessiz kalmayiz
            if iceride:
                d["gecis"] = True
                nasil.append(f"yuzeyin {_sayi(d['ortak_alan'])} mm2 kadari "
                             f"katinin icinde")
    else:
        # Iki yuzey: egri ikisinin de sinirindaysa DEGME, degilse gecis.
        if (kesit is not None and d["kesit_uzunluk"] > _KESIT_ESIGI
                and _egri_ici_geciyor_mu(kesit, sa, sb)):
            d["gecis"] = True
            nasil.append(f"kesisme egrisi {_sayi(d['kesit_uzunluk'])} mm")

    if d["gecis"]:
        d["hukum"] = "ICINDEN GECIYOR"
        d["satir"] = f"{ad_a} x {ad_b}: ICINDEN GECIYOR — " + ", ".join(nasil)
    elif d["mesafe"] < _TEMAS_ESIGI:
        d["hukum"] = "degiyor"
        d["satir"] = (f"{ad_a} <-> {ad_b}: degiyor (0 mm) — icinden GECMIYOR "
                      f"(ortak hacim yok, kesisme egrisi yok)")
    else:
        d["hukum"] = "ayri"
        d["satir"] = f"{ad_a} <-> {ad_b}: {_sayi(d['mesafe'])} mm ayri"
    return d


# BU BLOKTA MODELE ZATEN YAZILMIS GECISLER.
#
# OLCULDU (LOG/2026-08-31_f5a6a5ac.txt): model her yeni parcadan sonra
# `cakisma_kontrol(odak=...)` cagiriyor, ARDINDAN host'un dogrulama taramasi
# ayni ciftleri bir daha bulup BULGU olarak yaziyor. Ayni sayi, iki farkli
# cumleyle, tek istemin icinde:
#
#   BULGU RollbarKiris: icinden geciyor - ortak hacim 10.42 mm3,
#         RollbarDikme1 hacminin %16'i (RollbarDikme1 ile)
#   RollbarKiris x RollbarDikme1: ICINDEN GECIYOR - ortak hacim 10.42 mm3,
#         RollbarDikme1 hacminin %16'i
#
# O tek blokta ~950 karakter, oturum boyunca 52 blogun cogunda. Baglam
# 788k'ya cikan bir oturumda bu odenmesi gereksiz bir bedel; daha kotusu,
# ayni bulguyu iki kez okuyan model onu iki AYRI sorun sanabiliyor.
#
# KAZANAN TARAF `cakisma_kontrol` CIKTISI, tarama degil. Cunku (a) modelin
# KENDI sordugu sey odur, (b) ciktisi daha zengin - kac nesne, kac cift,
# kaci bbox ile elendi, ne kadar surdu, (c) taramanin isi zaten modelin
# SORMADIGINI yakalamak. Sorulani bir daha soylemesi gerekmiyor.
#
# YALNIZCA `yaz=True` cagrilari kaydediliyor: `yaz=False` (gorsel yolu)
# hicbir sey yazdirmaz, onun bulgusu bastirilirsa gercekten kaybolur.
_bildirilen_gecisler: set = set()


def bildirilen_gecisleri_sifirla() -> None:
    """Her kod blogunun BASINDA cagrilir (bkz. executor.calistir).

    Kayit tek bir blok icin gecerli: bir onceki turda yazilmis bir gecis,
    bu turdaki taramada bastirilmamali - model onu tekrar gormeli.
    """
    _bildirilen_gecisler.clear()


def gecis_bildirildi_mi(ad_a: str, ad_b: str) -> bool:
    return tuple(sorted((ad_a, ad_b))) in _bildirilen_gecisler


def cakisma_kontrol(*nesneler, odak=None, sure_butcesi: float = 2.0,
                    yaz: bool = True) -> dict:
    """Verilen nesnelerin BIRBIRINE gecip gecmedigini olcer.

    NEDEN VAR (olculdu, MANTIK 39): model uc acidan goruntuye bakip
    "birbirinin icine girmiyor" dedi, kullanici cakismayi gordu; sonradan
    ayni model ayni cakismayi ELLE yazdigi ucluyle (common + distToShape +
    slice) 20 saniyede buldu — 2.7 mm3. Goruntu bunu gosteremezdi: 900x640
    karede ~4 piksel/mm, cakisan sirit ~4 piksel ve yelkenin ARKASINDA.

    Yani bu, modelin akil yurutmesine birakilmayacak bir olcum — hazir:

        cakisma_kontrol()                       # belgedeki her ilgili cift
        cakisma_kontrol(a, b)                   # yalnizca bu ikisi
        cakisma_kontrol(a, b, c)                # ucunun tum ciftleri
        cakisma_kontrol(odak=a)                 # YALNIZCA a'yi ilgilendiren

    ODAK NEDEN VAR (olculdu, LOG/2026-08-27_9564dc71.txt): panel yakin
    cekimde tek bir nesne icin cakisma soruyordu ama kod onu belgedeki TUM
    nesnelerle carpiyordu — 44 nesne, 946 cift, 2 sn butce doldu ve **431
    cift hic olculmedi**. Yani sorulan cift bile bakilmadan kalabiliyordu.
    `odak` verildiginde ciftler yalnizca `odak x digerleri`: n(n-1)/2
    yerine n-1.

    TUKETILMIS NESNELER ELENIR (argumansiz ya da `odak` ile cagrilinca):
    bir kesme tabani ya da ayna kaynagi, sonucuyla elbette cakisir ve bu
    kusur degildir — bkz. kesif.tuketilmis_mi. Nesneleri ACIKCA verirsen
    eleme YAPILMAZ: sorulan seyi olceriz, sansure ugratmayiz.

    Ciftler once BBOX ile eleniyor (bkz. _bbox_kesisiyor_mu), sonra ucu
    birden olculuyor (bkz. _cift_olc). Sure butcesi dolarsa DURUR ve kac
    cifte bakilmadigini yazar — dogrulama katmanindaki durustluk kuralinin
    aynisi.

    "Degme" KUSUR DEGILDIR ve oyle raporlanmaz: bu projede yelken direge,
    kupeste govdeye bilerek deger (MANTIK 32'deki 31 kez tekrarlanan yanlis
    alarma donmemek icin). Kusur olan sey ICINDEN GECMEK.
    """
    import time

    from . import kesif as _kesif

    adaylar = [n for n in nesneler if n is not None]
    elenen_tuketilmis = 0
    if not adaylar:
        doc = App.ActiveDocument
        bulunan = _kesif.ilgili_nesneler(doc) if doc is not None else []
        # Kalinliksiz eskiz/2B iskele bu soruda gurultu: kesisme egrileri
        # her yerde cikar ve hicbiri kusur degil.
        bulunan = [o for o in bulunan
                   if _mesh_al(o) is not None
                   or (_sekil_al(o) is not None and _sekil_al(o).Faces)]
        # Baskasinin hammaddesi olanlar cikiyor. Odak nesnesinin KENDISI
        # asla elenmez: kullanici onu sordu, cevabini alir.
        adaylar = [o for o in bulunan
                   if (odak is not None and o is odak)
                   or not _kesif.tuketilmis_mi(o)]
        elenen_tuketilmis = len(bulunan) - len(adaylar)
    if odak is not None and not any(o is odak for o in adaylar):
        adaylar = [odak] + adaylar

    if len(adaylar) < 2:
        satir = ("cakisma_kontrol: en az iki nesne gerek "
                 "(belgede olculebilir iki parca bulunamadi)")
        if yaz:
            print(satir)
        return {"ciftler": [], "gecisler": [], "bakilan_cift": 0,
                "toplam_cift": 0, "bakilmayan": 0, "sure_sn": 0.0,
                "satir": satir}

    t0 = time.time()
    ciftler: list[dict] = []
    gecisler: list[dict] = []
    degenler = 0
    elenen = 0
    bakilmayan = 0
    toplam = 0

    # ODAK varsa cift sayisi n(n-1)/2 degil n-1: sorulan nesneyi
    # ilgilendirmeyen cift butceden yemez.
    if odak is not None:
        ham = [(odak, o) for o in adaylar if o is not odak]
    else:
        ham = [(adaylar[i], adaylar[j])
               for i in range(len(adaylar))
               for j in range(i + 1, len(adaylar))]

    for a, b in ham:
        toplam += 1
        if time.time() - t0 > sure_butcesi:
            bakilmayan += 1
            continue
        if not _bbox_kesisiyor_mu(a, b):
            elenen += 1
            continue
        d = _cift_olc(a, b)
        ciftler.append(d)
        if d.get("gecis"):
            gecisler.append(d)
        elif d.get("hukum") == "degiyor":
            degenler += 1

    sonuc = {"ciftler": ciftler, "gecisler": gecisler,
             "bakilan_cift": len(ciftler), "toplam_cift": toplam,
             "bakilmayan": bakilmayan, "sure_sn": time.time() - t0}

    bas = f"cakisma_kontrol — "
    if odak is not None:
        bas += f"odak {getattr(odak, 'Name', '?')}, "
    bas += (f"{len(adaylar)} nesne, {toplam} cift "
            f"({elenen} cift bbox ile elendi)")
    if elenen_tuketilmis:
        # DURUSTLUK: neyi olcmedigimizi soylemek zorundayiz, yoksa
        # "temiz" raporu yanlis guven verir.
        bas += (f"; {elenen_tuketilmis} nesne listeye alinmadi "
                f"(baskasinin kesme tabani/ayna kaynagi)")
    satirlar = [bas + f", {sonuc['sure_sn']:.2f} sn"]
    for d in gecisler:
        satirlar.append("  " + d["satir"])
    if not gecisler:
        satirlar.append("  ICINDEN GECEN CIFT YOK.")
    if degenler:
        satirlar.append(f"  degen (0 mm) cift: {degenler} — kusur degil, "
                        f"bilerek temas olabilir")
    if bakilmayan:
        satirlar.append(f"  KOSMAYAN: {bakilmayan} cift (sure siniri "
                        f"{sure_butcesi:g} sn asildi)")
    sonuc["satir"] = "\n".join(satirlar)
    if yaz:
        print(sonuc["satir"])
        # Bu ciftler artik modelin ISTEMINDE duruyor; dogrulama
        # taramasi onlari tekrar yazmasin.
        for d in gecisler:
            _bildirilen_gecisler.add(tuple(sorted((d["a"], d["b"]))))
    return sonuc


# --------------------------------------------------------------------------
# 7. SAGLIK — "bu sekil gercekten saglam mi"
# --------------------------------------------------------------------------
#
# NEDEN VAR (gunluklerden SAYILDI, PLAN S8 kabul olcutu):
#   isValid              156 kez / 9 dosya
#   isSolid              125 kez / 4 dosya
#   hasSelfIntersections  96 kez / 4 dosya
#   len(Shape.Solids)     86 kez / 7 dosya
#   hasNonManifolds       48 kez / 3 dosya
# Model bunu her oturumda ELLE yaziyor ve iki AYRI deyimle yaziyor:
#   kati  -> sh.isValid() and len(sh.Solids) == 1 and sh.isClosed()
#   mesh  -> m.isSolid() and not m.hasNonManifolds() and
#            not m.hasSelfIntersections()
# Yani nesnenin turune gore hangi testin gectigini de kendisi secmek
# zorunda kaliyor. Burasi o secimi ustlenir.
#
# ELENEN ADAYLAR (gunlukte KANITI YOK, o yuzden yazilmadi):
#   MatrixOfInertia / atalet tensoru ...  0 kez
#   sapma haritasi (Inspection) .........  0 kez
#   removeSplitter / Part::Refine .......  0 kez (modelin sozunde gecti,
#                                          kodunda hic cagrilmadi)

def _saglik_kati(s) -> tuple:
    """Bir Part sekli icin (kusurlar, bilgiler)."""
    kusur: list[str] = []
    bilgi: list[str] = []

    try:
        if not s.isValid():
            kusur.append("isValid=False — OCC dogrulamasindan gecmiyor")
    except Exception:
        pass

    # YUZU OLMAYAN SEKIL KATI OLMAYA ADAY DEGIL. Olculdu
    # (LOG/2026-08-31_ed2bc86b.txt): `saglik()` belge taramasinda
    # `KUSUR Origin001: KATI YOK` yazdi; o nesne bir datum NOKTASIYDI
    # (App::Point, Shape=Vertex). Nokta/kenar/tel'e kati testi uygulamak
    # kategori hatasi — ve kusur raporunu gurultuyle doldurmak, gercek
    # kusurlari degersizlestirmenin en kestirme yolu (§32'nin dersi).
    # Kesif tarafinda bu tip artik eleniyor; burasi ikinci kat: nesne
    # ELLE verilse de yanlis kusur yazilmasin.
    try:
        yuz_sayisi = len(s.Faces)
    except Exception:                                            # noqa: BLE001
        yuz_sayisi = None
    if yuz_sayisi == 0:
        bilgi.append("yuzu yok (nokta/kenar/tel) — kati testleri uygulanmadi")
        return kusur, bilgi

    kati = None
    try:
        kati = len(s.Solids)
    except Exception:
        pass
    if kati == 0:
        kusur.append("KATI YOK (yalnizca yuzey/kabuk) — hacim ve baski anlamsiz")
    elif kati and kati > 1:
        # Kusur DEGIL: bilesik bir sekil kasitli olabilir. Ama modelin
        # gunlukte tam da bunu aradigi gorulduğu icin soyleniyor.
        bilgi.append(f"{kati} ayri kati — birlestirilmemis olabilir")

    if kati:
        try:
            if not s.isClosed():
                kusur.append("kapali degil — acik kabuk")
        except Exception:
            pass

    try:
        h = float(s.Volume)
        if kati and h <= 0:
            kusur.append(f"hacim {_sayi(h)} mm3 — ters yonlu kati")
        else:
            bilgi.append(f"hacim {_sayi(h)} mm3")
    except Exception:
        pass

    try:
        bilgi.append(f"{len(s.Faces)} yuz")
    except Exception:
        pass
    return kusur, bilgi


# (ad, kusur sayilan deger, mesaj) — hepsi tek tek korumali cagriliyor
# cunku FreeCAD surumleri arasinda bu metotlarin hepsi bulunmayabilir.
_MESH_TESTLERI = (
    ("isSolid", False, "KAPALI KATI DEGIL — delik/acik kenar var; "
                       "hacim ve baski guvenilmez"),
    ("hasNonManifolds", True, "manifold olmayan kenar var"),
    ("hasSelfIntersections", True, "kendini kesen yuzey var"),
    ("hasInvalidPoints", True, "gecersiz nokta var"),
    ("hasDegeneratedFacets", True, "sifir alanli (bozuk) ucgen var"),
)


def _saglik_mesh(m) -> tuple:
    """Bir Mesh icin (kusurlar, bilgiler)."""
    kusur: list[str] = []
    bilgi: list[str] = []
    for ad, kotu, mesaj in _MESH_TESTLERI:
        try:
            deger = bool(getattr(m, ad)())
        except Exception:
            continue
        if deger is kotu:
            kusur.append(mesaj)
    try:
        bilgi.append(f"{m.CountFacets} ucgen")
    except Exception:
        pass
    try:
        bilgi.append(f"hacim {_sayi(m.Volume)} mm3")
    except Exception:
        pass
    return kusur, bilgi


def saglik(*nesneler, yaz: bool = True) -> dict:
    """Sekil/mesh SAGLAM MI — bozuk boolean ve basilamaz mesh yakalar.

        saglik()          # belgedeki her ilgili nesne
        saglik(a, b)      # yalnizca bunlar

    Kati ve mesh AYRI testlerden gecer (bkz. _saglik_kati / _saglik_mesh);
    hangisinin uygulanacagini bu fonksiyon secer.

    KUSUR ile BILGI ayrilir — projenin kurali. "3 ayri kati" bir kusur
    degildir, bilgidir; "kati yok" kusurdur. Bozuk cikan hicbir sey
    yuvarlanmaz: olculemeyen test sessizce ATLANIR, uydurulmaz.
    """
    import time

    from . import kesif as _kesif

    adaylar = [n for n in nesneler if n is not None]
    if not adaylar:
        doc = App.ActiveDocument
        adaylar = _kesif.ilgili_nesneler(doc) if doc is not None else []

    if not adaylar:
        satir = "saglik: bakilacak nesne bulunamadi"
        if yaz:
            print(satir)
        return {"nesneler": [], "kusurlu": [], "satir": satir}

    t0 = time.time()
    kayitlar: list[dict] = []
    for o in adaylar:
        ad = getattr(o, "Name", "?")
        m = _mesh_al(o)
        if m is not None:
            kusur, bilgi = _saglik_mesh(m)
            tur = "mesh"
        else:
            s = _sekil_al(o)
            if s is None:
                continue
            kusur, bilgi = _saglik_kati(s)
            tur = "kati"
        # Hammadde oldugunu SOYLUYORUZ ama elemiyoruz: bozuk bir kesme
        # tabani, bozuk sonucun ta kendisidir.
        try:
            hammadde = _kesif.tuketilmis_mi(o)
        except Exception:
            hammadde = False
        kayitlar.append({"ad": ad, "tur": tur, "kusurlar": kusur,
                         "bilgiler": bilgi, "hammadde": hammadde})

    kusurlu = [k for k in kayitlar if k["kusurlar"]]
    temiz = [k for k in kayitlar if not k["kusurlar"]]
    sure = time.time() - t0

    satirlar = [f"saglik — {len(kayitlar)} nesne, {len(kusurlu)} kusurlu, "
                f"{sure:.2f} sn"]
    for k in kusurlu:
        etiket = k["ad"] + (" (hammadde)" if k["hammadde"] else "")
        for mesaj in k["kusurlar"]:
            satirlar.append(f"  KUSUR {etiket}: {mesaj}")
    if not kusurlu:
        satirlar.append("  KUSUR YOK.")
    # Bilgi satirlari kusurdan SONRA ve kisaltilmis: gurultu yapmasin.
    # "uygulanmadi" da geciyor: bir nesneye BAKILMADIYSA bunu soylemek
    # zorundayiz, yoksa "0 kusurlu" temiz sanilir — projenin "olcemedigini
    # uydurma" kuralinin bu fonksiyondaki karsiligi.
    notlar = [f"  not {k['ad']}: {b}"
              for k in kayitlar for b in k["bilgiler"]
              if "birlestirilmemis" in b or "uygulanmadi" in b]
    satirlar.extend(notlar)
    if temiz:
        adlar = ", ".join(k["ad"] for k in temiz[:8])
        if len(temiz) > 8:
            adlar += f", +{len(temiz) - 8}"
        satirlar.append(f"  temiz: {adlar}")

    sonuc = {"nesneler": kayitlar, "kusurlu": kusurlu, "sure_sn": sure,
             "satir": "\n".join(satirlar)}
    if yaz:
        print(sonuc["satir"])
    return sonuc


# --------------------------------------------------------------------------
# 8. SIMETRI — "sol yari sag yariyla ayni mi"
# --------------------------------------------------------------------------
#
# NEDEN VAR (gunluklerden SAYILDI): "simetri" 5 ayri gunlukte 38 kez
# geciyor ve model bunu her seferinde ELLE kuruyor — bbox'tan orta ekseni
# cikarip bantlara bolerek nokta sayiyor. Bir kez de GERCEK bir kusuru
# boyle buldu: "Y=111-143 bandinda yalnizca pozitif X var, negatif tarafta
# hicbir nokta yok — eksik olan kuyruk yatay kanadinin sol yarisi."
# Bu, 4 piksel/mm'lik bir karede gozden kacabilecek bir kusurdu.
#
# ELLE YAZILANIN ZAYIFLIGI: bant sayimi yalnizca "hic nokta var mi"
# sorusunu sorar; kaymis ama VAR OLAN bir yariyi TEMIZ gosterir.
# Burada aynalanip GERCEK sapma olculuyor.

_EKSEN_NO = {"x": 0, "y": 1, "z": 2}


def _eksen_adi(eksen) -> str:
    ad = str(eksen).lower().strip()
    if ad not in _EKSEN_NO:
        raise ValueError("eksen 'x', 'y' ya da 'z' olmali (verilen: %r)" % (eksen,))
    return ad


def _ayna_taban_normal(eksen: str, merkez: float):
    i = _EKSEN_NO[eksen]
    taban = App.Vector(*[merkez if k == i else 0.0 for k in range(3)])
    normal = App.Vector(*[1.0 if k == i else 0.0 for k in range(3)])
    return taban, normal


def _simetri_kati(s, eksen: str, merkez: float):
    """Katida simetri: aynala, IKI YONLU farki al, hacmini olc.

    Tek yonlu fark (A - A') yetmez — yalnizca fazlaligi gorur, EKSIGI
    gormez. Simetrik fark iki taraflidir.
    """
    taban, normal = _ayna_taban_normal(eksen, merkez)
    try:
        ayna = s.mirror(taban, normal)
    except Exception:
        return None
    fark_h = 0.0
    kutular = []
    for a, b in ((s, ayna), (ayna, s)):
        try:
            f = a.cut(b)
        except Exception:
            return None
        try:
            h = abs(float(f.Volume))
        except Exception:
            h = 0.0
        if h > _HACIM_ESIGI:
            fark_h += h
            try:
                kutular.append(f.BoundBox)
            except Exception:
                pass
    try:
        toplam = abs(float(s.Volume))
    except Exception:
        toplam = 0.0
    if toplam <= 0:
        return None
    return {"yontem": "hacim", "fark": fark_h, "toplam": toplam,
            "oran": fark_h / toplam, "kutular": kutular}


_SIMETRI_AZAMI_NOKTA = 20000


def _simetri_nokta(noktalar, eksen: str, merkez: float):
    """Nokta bulutunda simetri: aynala, her aynalanan noktanin ORIJINALE
    en yakin uzakligini olc.

    scipy'nin cKDTree'si (modul basligindaki olcume gore kaba kuvvetten
    120 kat hizli) yoksa OLCMEYIZ, uydurmayiz -> None.
    """
    np = _np()
    if np is None or not noktalar:
        return None
    try:
        from scipy.spatial import cKDTree
    except Exception:
        return None

    P = np.array([[p.x, p.y, p.z] for p in noktalar], dtype=float)
    if len(P) > _SIMETRI_AZAMI_NOKTA:
        adim = int(len(P) / _SIMETRI_AZAMI_NOKTA) + 1
        P = P[::adim]
    Q = P.copy()
    i = _EKSEN_NO[eksen]
    Q[:, i] = 2.0 * merkez - Q[:, i]
    d, _bul = cKDTree(P).query(Q)
    en_kotu = int(np.argmax(d))
    return {"yontem": "nokta", "nokta_sayisi": int(len(P)),
            "azami": float(d.max()), "ortalama": float(d.mean()),
            "en_kotu_yer": tuple(float(v) for v in Q[en_kotu])}


def _simetri_hukum(olculen: dict, boy: float) -> tuple:
    """(hukum, aciklama). Esikler GORELI — 200 mm'lik bir parcada 0.1 mm
    simetriktir, 2 mm'lik parcada degildir."""
    if olculen["yontem"] == "hacim":
        oran = olculen["oran"]
        if oran < 0.001:
            return "simetrik", "fark hacmi %%%.3f" % (oran * 100)
        if oran < 0.01:
            return "neredeyse", "fark hacmi %%%.2f" % (oran * 100)
        return "ASIMETRIK", "fark hacmi %%%.1f" % (oran * 100)
    azami = olculen["azami"]
    goreli = azami / boy if boy else 0.0
    if goreli < 0.001:
        return "simetrik", "azami sapma %s mm" % _sayi(azami)
    if goreli < 0.01:
        return "neredeyse", "azami sapma %s mm" % _sayi(azami)
    return "ASIMETRIK", ("azami sapma %s mm (boyun %%%.1f'i)"
                         % (_sayi(azami), goreli * 100))


def simetri(nesne=None, eksen=None, merkez=None, yaz: bool = True) -> dict:
    """Parca bir eksene gore SIMETRIK MI — ve degilse NEREDE bozuk.

        simetri()                       # tek nesne, uc eksenin ucu de
        simetri(obj, "x")               # yalnizca x
        simetri(obj, "y", merkez=8.0)   # ayna duzlemi elle

    `eksen` verilmezse UCU DE olculur ve simetrik olanlar soylenir — "bu
    parca hangi eksene gore simetrik" sorusunun cevabi budur.
    `merkez` verilmezse ayna duzlemi bbox ortasidir (modelin gunlukte elle
    yaptigi secimin ayni: X_C = (XMin + XMax) / 2).

    Katida hacim farkiyla, mesh'te nokta bulutuyla olculur. Boolean
    patlarsa (bozuk sekilde olagan) nokta bulutuna DUSER ve bunu satirda
    SOYLER. Ikisi de olcemezse sonuc vermez — "simetrik" DEMEZ.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        satir = "simetri: nesne bulunamadi (nesneyi ver ya da tek nesne birak)"
        if yaz:
            print(satir)
        return {"satir": satir, "eksenler": {}}

    kutu = _kutu(nesne)
    if kutu is None:
        satir = "simetri: %s olculemedi (sekil yok)" % getattr(nesne, "Name", "?")
        if yaz:
            print(satir)
        return {"satir": satir, "eksenler": {}}

    eksenler = [_eksen_adi(eksen)] if eksen is not None else ["x", "y", "z"]
    ortalar = {"x": (kutu.XMin + kutu.XMax) / 2.0,
               "y": (kutu.YMin + kutu.YMax) / 2.0,
               "z": (kutu.ZMin + kutu.ZMax) / 2.0}
    boylar = {"x": kutu.XLength, "y": kutu.YLength, "z": kutu.ZLength}

    m = _mesh_al(nesne)
    s = None if m is not None else _sekil_al(nesne)
    noktalar = None
    if m is not None:
        try:
            noktalar = m.Topology[0]
        except Exception:
            noktalar = None

    sonuclar = {}
    for e in eksenler:
        orta = ortalar[e] if merkez is None else float(merkez)
        olculen = None
        if s is not None:
            olculen = _simetri_kati(s, e, orta)
            if olculen is None:
                try:
                    kose, _uc = s.tessellate(max(0.1, boylar[e] / 200.0))
                    olculen = _simetri_nokta(list(kose), e, orta)
                    if olculen:
                        olculen["yedek"] = True
                except Exception:
                    olculen = None
        elif noktalar:
            olculen = _simetri_nokta(noktalar, e, orta)
        if olculen is None:
            sonuclar[e] = {"hukum": "olculemedi", "merkez": orta}
            continue
        hukum, aciklama = _simetri_hukum(olculen, boylar[e])
        olculen.update({"hukum": hukum, "aciklama": aciklama, "merkez": orta})
        sonuclar[e] = olculen

    ad = getattr(nesne, "Name", "?")
    satirlar = ["simetri — %s" % ad]
    for e in eksenler:
        r = sonuclar[e]
        if r["hukum"] == "olculemedi":
            satirlar.append("  %s: OLCULEMEDI (duzlem %s) — boolean ve nokta "
                            "bulutu ikisi de basarisiz"
                            % (e, _sayi(r["merkez"])))
            continue
        ek = " [yedek: nokta bulutu]" if r.get("yedek") else ""
        satirlar.append("  %s (duzlem %s=%s): %s — %s%s"
                        % (e, e, _sayi(r["merkez"]), r["hukum"],
                           r["aciklama"], ek))
        if r["hukum"] == "ASIMETRIK":
            # NEREDE bozuk oldugu asil isi goren bilgi.
            for b in r.get("kutular", [])[:2]:
                satirlar.append(
                    "      fark bolgesi: x %s..%s, y %s..%s, z %s..%s"
                    % (_sayi(b.XMin), _sayi(b.XMax), _sayi(b.YMin),
                       _sayi(b.YMax), _sayi(b.ZMin), _sayi(b.ZMax)))
            if "en_kotu_yer" in r:
                x, y, z = r["en_kotu_yer"]
                satirlar.append("      en kotu nokta: (%s, %s, %s)"
                                % (_sayi(x), _sayi(y), _sayi(z)))

    olculenler = [e for e in eksenler if sonuclar[e]["hukum"] != "olculemedi"]
    if len(olculenler) > 1:
        temiz = [e for e in olculenler if sonuclar[e]["hukum"] != "ASIMETRIK"]
        if temiz:
            satirlar.append("  -> simetrik eksen: %s" % ", ".join(temiz))
        else:
            satirlar.append("  -> hicbir eksene gore simetrik degil")

    sonuc = {"eksenler": sonuclar, "satir": "\n".join(satirlar)}
    if yaz:
        print(sonuc["satir"])
    return sonuc
