"""MEVCUT belgenin bastan asagi olculmesi — `kesif()`, modelin ilk adimi.

NEDEN VAR. Kullanicinin istegi: "sifirdan bir sey yapilacaksa normal
surece devam etsin, ama VAR OLAN bir seyin uzerine yapacaksa once ne
oldugunu tam anlasin, her yerini olcsun, kullaniciya da soylesin — sonra
profesyonel ve bilgili bir cevap versin: 'evet bu bardaga kulp
ekleyebiliriz, kulbun araligi 24-12 mm olabilir, sen nereye eklemek
istiyorsun'."

Gunluk (2026-08-21 incelemesi) bunun neden gerektigini gosteriyor: model
mevcut geometriyi TAHMIN ederek ise basliyordu. `baa70fa4`'te ilk soru
"agiz capi ne kadar" idi ve model capi bilmiyordu; `b2938bd0`'da vidanin
neresinin nerede oldugunu anlamak icin bes tur harcandi. Ikisinde de olcum
ZATEN mumkundu, yalnizca kimse basta yapmiyordu.

OLCEN KIM: MODEL, host degil.
Ilk tasarimda host olcup baglama koyuyordu ("bir tur kazanir" diye).
Kullanici bunu reddetti ve hakliydi: NE OLCULECEGINE ISE BAKARAK karar
verilir. Host kor kor her nesnenin uc kesitini alir — cogu turda
gereksiz, her turda token. Model ise "kulp eklenecek" bilgisiyle neyin
onemli oldugunu bilir. Ustelik model olcunce olcum SOHBETTE gorunur:
kullanici hangi sayinin nereden geldigini gorur ve gerekirse kodu
duzeltip yeniden calistirir. Host'un yaptigi olcum gorunmez bir sihirdir.

Bu yuzden burasi bir NAMESPACE YARDIMCISI: model `kesif()` yaziyor,
cikti print ile kendisine donuyor (bkz. conversation._ciktiyi_yolla).

KATMAN KURALI (MANTIK 12): burada Qt YOK.
"""

from __future__ import annotations

import time

import FreeCAD as App

from .. import log
from . import dogrulama, olcum

# Kesifte en fazla kac nesne olculur ve toplam sure siniri. Ikisi de ust
# sinir; asilirsa kesif DURUR ve durdugu metne yazilir (dogrulama.py'deki
# durustluk kuralinin aynisi).
# 8 -> 24: OLCULDU (MANTIK 39), 52 nesnelik gercek bir belgede kesif 8
# nesnede durdu ama sure butcesinin (3.0 sn) yalnizca 0.48 sn'ini kullandi.
# Yani freni SAYI koyuyordu, oysa asil kaynak SURE. Sayiyi buyutup freni
# sureye birakiyoruz; siralama da onceliklendirildi (bkz. _oncelik).
AZAMI_NESNE = 24
SURE_BUTCESI = 3.0

# Kesif disi tipler: bunlar "mevcut is" degil, iskele.
_ATLANAN = (
    "App::Origin", "App::Plane", "App::Line", "App::Point", "App::Part",
    "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
    "App::DocumentObjectGroup",
)
# "App::Point" SONRADAN eklendi. Olculdu (LOG/2026-08-31_ed2bc86b.txt):
# `saglik()` belge taramasinda `KUSUR Origin001: KATI YOK` yazdi. O nesne
# bir datum NOKTASI (`App::Point`, Shape=Vertex) — katisi olmamasi normal.
# Listede `App::Plane` ve `App::Line` vardi, `App::Point` unutulmustu;
# ucu ayni iskele takiminin parcasi.


def _atlanir_mi(o) -> bool:
    tip = getattr(o, "TypeId", "") or ""
    return any(tip.startswith(x) for x in _ATLANAN)


def _oncelik(o) -> tuple:
    """Kesif sirasi: ONCE isin kendisi, SONRA iskele.

    OLCULDU (LOG/2026-08-26_34ac9988.txt, MANTIK 39): 52 nesnelik bir
    belgede yalnizca 8'i olculdu ve o 8 slotun 3'u hacimsiz ESKIZLERE gitti
    (`YelkenAltKesit1`, `YelkenAltKesit2`, `YelkenOrtaKesit1`), cunku
    siralama `doc.Objects` sirasiydi. Yani modelin cakismasini sordugumuz
    yelkenlerin cogu hic olculmedi.

    Anahtar (kucuk = once): hacimli kati > yuzeyli sekil > mesh > geri
    kalan (eskiz, tel, 2B). Esitlikte gorunur olan once — kullanicinin
    ekranda gordugu sey, isin kendisidir.
    """
    kati = yuzey = mesh = False
    try:
        s = o.Shape
        kati = bool(s.Solids) and abs(s.Volume) > 1e-9
        yuzey = bool(s.Faces)
    except Exception:                                            # noqa: BLE001
        pass
    if not kati and not yuzey:
        try:
            mesh = hasattr(o.Mesh, "CountFacets")
        except Exception:                                        # noqa: BLE001
            mesh = False
    if kati:
        sinif = 0
    elif yuzey:
        sinif = 1
    elif mesh:
        sinif = 2
    else:
        sinif = 3
    gorunur = 0 if getattr(o, "Visibility", True) else 1
    return (sinif, gorunur)


# Bir nesneyi HAMMADDE olarak tuketen alanlar. Part/PartDesign/Draft'ta
# baska ad kullanan her sey buraya giriyor; bilinmeyen bir tip cikarsa
# nesne tuketilmemis sayilir (sessizce elemektense fazla gostermek yeg).
_TUKETEN_ALANLAR = ("Base", "Tool", "Shapes", "Source", "Objects",
                    "Profile", "Sections", "Spine", "Sketch", "Group")


def tuketilmis_mi(o) -> bool:
    """Bu nesne baska bir nesnenin HAMMADDESI mi (kesme tabani, ayna kaynagi)?

    OLCULDU (LOG/2026-08-27_9564dc71.txt): kamyonet oturumunda cakisma
    raporundaki 813 "ICINDEN GECIYOR" satirinin **627'si (%77)** boyle
    nesnelerdi — `KabinDetay x Kabin` 37 844 mm3, `Teker1 x CamIc1` 904 mm3.
    Ikisi de kusur degil: Kabin, KabinDetay'in kesilmemis hali; CamIc1 bir
    kesme silindiri, parca degil takim. Model her turda "bunlar gizli
    kaynak nesneler, yeni bir sorun yok" diye feragat cumlesi yazmak
    zorunda kaldi — MANTIK 32'deki 31 kez tekrarlanan yanlis alarmin
    aynisi, yeni kilikta.

    IKI SART BIRDEN ARANIYOR, ve ikisi de olcumle geldi:

    * Yalnizca GORUNURLUK yetmez — kullanici gercek bir parcayi gecici
      olarak gizlemis olabilir; o parca hala parcadir.
    * Yalnizca REFERANS da yetmez. Ilk deneme boyleydi ve ayni belgede
      `KapiKolu`yu eledi: o bir `Part::Mirroring` kaynagi, ama FreeCAD
      ayna kaynagini GIZLEMEZ — kol ekranda duran gercek bir parca.
      Oysa `Part::Cut`/`MultiFuse` tabanlarini gizler.

    Yani olcut sudur: **baskasinin hammaddesi VE FreeCAD onu gizlemis.**
    Gizlemediyse sonuca dahildir, olculur.
    """
    if getattr(o, "Visibility", True):
        return False
    try:
        ustler = list(getattr(o, "InList", []) or [])
    except Exception:                                            # noqa: BLE001
        return False
    for ust in ustler:
        for alan in _TUKETEN_ALANLAR:
            try:
                deger = getattr(ust, alan, None)
            except Exception:                                    # noqa: BLE001
                continue
            if deger is None:
                continue
            if deger is o:
                return True
            try:
                if any(x is o for x in deger):
                    return True
            except TypeError:
                pass
    return False


def ilgili_nesneler(doc) -> list:
    """Kesfedilmeye deger nesneler — iskele haric, govde olanlar.

    ONCELIK SIRALI (bkz. _oncelik): butce dolarsa atlanan sey eskiz olsun,
    parca olmasin. Siralama KARARLI (`sorted` stabil), yani ayni siniftaki
    nesneler belge sirasini koruyor.
    """
    if doc is None:
        return []
    return sorted((o for o in doc.Objects if not _atlanir_mi(o)),
                  key=_oncelik)


def kesif(nesne=None, yaz: bool = True) -> str:
    """Modelin cagirdigi giris noktasi: belgeyi (ya da tek nesneyi) olcer.

    Tek satir: `kesif()`. Ciktisi print ile modele donuyor, yani "once ne
    oldugunu anla" adimi TEK BLOK ve tek tur.
    """
    if nesne is not None:
        metin = "\n".join(_bir_nesne(nesne))
    else:
        metin = kesif_metni()
    if not metin:
        metin = ("kesif: belgede olculecek bir sey yok — bos belge. "
                 "Sifirdan basliyorsun.")
    if yaz:
        print(metin)
    return metin


def _delik_dokumu(sekil) -> str:
    """Silindirik yuzleri capa gore gruplar: 'Ø3.4x4, Ø8x2'.

    Delik envanteri, mevcut bir parcaya bir sey eklerken en cok sorulan
    sey: "vida deligi var mi, kac mm". Silindirik yuz saymak bunu tam
    vermiyor (bir cikinti da silindirik olabilir) ama modele dogru soruyu
    sorduracak kadar veriyor.
    """
    try:
        yuzler = sekil.Faces
    except Exception:
        return ""
    sayac: dict[float, int] = {}
    for y in yuzler:
        try:
            yuzey = y.Surface
            if type(yuzey).__name__ != "Cylinder":
                continue
            r = round(float(yuzey.Radius), 2)
        except Exception:
            continue
        sayac[r] = sayac.get(r, 0) + 1
    if not sayac:
        return ""
    parcalar = [f"Ø{olcum._sayi(2 * r)}x{n}"
                for r, n in sorted(sayac.items(), reverse=True)]
    return "silindirik yuzler: " + ", ".join(parcalar[:6])


def _bir_nesne(o) -> list[str]:
    """Tek nesnenin kesif satirlari. ASLA istisna firlatmaz."""
    satirlar: list[str] = []
    ad = o.Name
    etiket = f" '{o.Label}'" if getattr(o, "Label", "") != ad else ""
    satirlar.append(f"  {ad}{etiket} ({getattr(o, 'TypeId', '?')})")

    try:
        d = olcum.olc(o, yaz=False)
        if d.get("satir"):
            satirlar.append("    " + d["satir"])
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"kesif olcumu: {ad}: {e}")

    m = dogrulama._mesh_al(o)
    if m is not None:
        # Uc yukseklikten kesit: taban, orta, ust. Kupa/silindir/koni gibi
        # donel govdelerde bu uc sayi seklin TAMAMINI anlatiyor — model
        # "agiz capi 55, taban 45, yani hafif konik" diyebiliyor.
        try:
            b = m.BoundBox
            h = b.ZLength
            for etiketi, z in (("taban", b.ZMin + h * 0.05),
                               ("orta", b.ZMin + h * 0.5),
                               ("agiz/ust", b.ZMin + h * 0.95)):
                k = olcum.kesit_capi(o, z=z, yaz=False)
                if k.get("satir"):
                    satirlar.append(f"    {etiketi}: " + k["satir"])
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"kesif kesiti: {ad}: {e}")

        # Duvar kalinligi: baskiya uygunlugun asil sorusu ve isin atarak
        # olculuyor (bkz. olcum.duvar_kalinligi).
        try:
            k = olcum.duvar_kalinligi(o, yaz=False)
            if k.get("satir"):
                satirlar.append("    " + k["satir"])
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"kesif duvar: {ad}: {e}")

        try:
            hazir, engeller, _ = dogrulama.baskiya_hazir_mesh(m)
            satirlar.append(f"    baskiya hazir = "
                            f"{'EVET' if hazir else 'HAYIR'}"
                            + ("" if hazir else
                               " (" + ", ".join(t for t, _a in engeller) + ")"))
        except Exception:
            pass
        return satirlar

    try:
        dokum = _delik_dokumu(o.Shape)
        if dokum:
            satirlar.append("    " + dokum)
    except Exception:
        pass
    return satirlar


def kesif_metni(doc=None, azami: int = AZAMI_NESNE,
                sure_butcesi: float = SURE_BUTCESI) -> str:
    """Belgenin olculmus ozeti. Bos belgede bos string doner."""
    doc = doc or App.ActiveDocument
    nesneler = ilgili_nesneler(doc)
    if not nesneler:
        return ""

    t0 = time.time()
    satirlar = [f"KESIF — {len(nesneler)} nesne olculdu (deterministik, "
                f"tahmin degil):"]

    try:
        b = doc.BoundBox if hasattr(doc, "BoundBox") else None
    except Exception:
        b = None
    if b is not None:
        satirlar.append(f"belge sinirlari: {olcum._sayi(b.XLength)}x"
                        f"{olcum._sayi(b.YLength)}x{olcum._sayi(b.ZLength)} mm")

    atlanan = 0
    for i, o in enumerate(nesneler):
        if i >= azami or time.time() - t0 > sure_butcesi:
            atlanan = len(nesneler) - i
            break
        try:
            satirlar.extend(_bir_nesne(o))
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"kesif: {o.Name}: {e}")

    if atlanan:
        satirlar.append(f"  ... {atlanan} nesne olculMEDI (sinir asildi). "
                        f"Gerekiyorsa adiyla olc: kesif(doc.getObject('ad'))")

    satirlar.append(f"olcum suresi: {time.time() - t0:.2f} sn")
    return "\n".join(satirlar)
