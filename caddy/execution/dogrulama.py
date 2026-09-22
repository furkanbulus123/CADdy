"""Kod calistiktan sonra DETERMINISTIK geometri kontrolu.

NEDEN VAR. CADdy'de iki dogrulama katmani olmasi gerekiyordu, bir tanesi
vardi. Gorsel kontrol (§8e) ANLAMSAL hatayi yakaliyor — "kulak yanlis yere
kondu", "parcalar birbirine degmiyor". Yakalayamadigi sey, goze normal
gorunen bozuk topoloji. Onu deterministik kontrol yakalar, ve o katman yoktu.

Bolunme sudur:

    deterministik kontrol  ->  gecti/kaldi kararini VERIR
    gorsel kontrol         ->  deterministigin kodlamadigi hatayi yakalar

Fikir earthtojake/text-to-cad'in `inspection-and-validation.md` dosyasindan
alindi. Oradaki iki uyari FreeCAD 1.1.1'de OLCULDU ve ikisi de dogru cikti:

  1. `isValid()` TERS KATIYI YAKALAMIYOR. Part.makeBox(10,10,10).reversed()
     icin isValid() -> True, Volume -> -999.9999. Topolojik gecerlilik ters
     yonlu bir govdeyi gecerli sayar; onu yalnizca HACMIN ISARETI yakalar.
     Ters kati 3B'de "dunyada delik" gibi gorunur ve boolean'lari bozar.

  2. HACIM ASLA TOPLANMAZ, kati kati bakilir. Olculdu: icinde +1000 ve -1000
     olan bir bilesigin `.Volume` degeri **0.0**. Toplama bakan bir kontrol
     hicbir sey gormez.

Ucuncusu kendi olcumumuz:

  3. ACIK KABUK da isValid()'i geciyor. Bes yuzlu kutu: isValid() -> True,
     isClosed() -> False, Solids -> 0. Yani "gecerli" ama basilamaz.

Dorduncusu MESH tarafinda, ayni kalibin tekrari:

  4. `mesh.isSolid()` de tek basina yetmiyor. Olculdu: birbirinin icine
     giren iki kutunun mesh'i icin isSolid() -> True ama
     hasSelfIntersections() -> True ve countComponents() -> 2. "Kapali"
     olmak basilabilir olmak demek degil.

MALIYET (olculdu, 36 yuzlu katida): isValid 0.043 sn, isClosed ~0, Solids
ve Volume 0.001 sn, BoundBox ~0. isValid yuz sayisiyla buyuyor, o yuzden
hem sure hem nesne sayisi butceli.
Mesh tarafi (olculdu, 12850 facet): isSolid 0.008, hasSelfIntersections
0.024, hasNonManifolds 0.005, countComponents 0.001 sn.

DURUSTLUK KURALI. Rapor, KOSAN kontrolleri kosmayanlardan ayirir. Kosmamis
bir kontrol sessizce "temiz" sayilmaz; adi `atlanan`a yazilir ve sebebiyle
birlikte modele gider. Sebep: model gormedigi bir kontrolu gecmis sayip
"dogrulandi" diye rapor ediyor — kaynak dosyanin deyimiyle *"report only
checks that were actually run"*.

KATMAN KURALI (MANTIK 12): burada Qt YOK, yalnizca FreeCAD. Arayuzsuz
sinanabilmeli.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import FreeCAD as App

from .. import log

# Tek calistirmada kontrol edilecek en fazla nesne ve toplam sure. Ikisi de
# ust sinir; asilirsa kontrol DURUR ve durdugu rapora yazilir.
AZAMI_NESNE = 25
SURE_BUTCESI = 1.5          # saniye

# Kati uretmesi BEKLENMEYEN tipler. Bir eskizin katisi olmamasi kusur degil;
# bunlari "kati uretmedi" diye raporlamak kurt masali olur ve model gercek
# bulgulari da ciddiye almaz.
_KATI_BEKLENMEYEN = (
    "Sketcher::",
    "Part::Part2DObject",
    "App::Origin",
    "App::Plane",
    "App::Line",
    "App::DocumentObjectGroup",
    "PartDesign::Plane",
    "PartDesign::Line",
    "PartDesign::Point",
)


@dataclass
class Bulgu:
    nesne: str
    tur: str
    ayrinti: str

    def __str__(self) -> str:
        return f"{self.nesne}: {self.tur} — {self.ayrinti}"


@dataclass
class Rapor:
    kosan: list[str] = field(default_factory=list)
    atlanan: list[str] = field(default_factory=list)
    bulgular: list[Bulgu] = field(default_factory=list)
    olcumler: list[str] = field(default_factory=list)
    bakilan: int = 0
    sure_sn: float = 0.0

    @property
    def temiz(self) -> bool:
        return not self.bulgular

    def metin(self) -> str:
        """Modele giden metin. Kisa tutuluyor — her calistirmada gonderiliyor."""
        if not self.kosan and not self.atlanan:
            return ""
        p = [f"dogrulama: {self.bakilan} nesne, {self.sure_sn:.2f} sn"]
        if self.kosan:
            p.append("  kosan kontroller: " + ", ".join(self.kosan))
        for a in self.atlanan:
            p.append("  KOSMAYAN: " + a)
        for o in self.olcumler:
            p.append("  " + o)
        for b in self.bulgular:
            p.append("  BULGU " + str(b))
        if not self.bulgular and self.kosan:
            p.append("  bulgu yok (yalnizca yukarida kosan kontroller icin)")
        return "\n".join(p)


def _kati_beklenir_mi(o) -> bool:
    tip = getattr(o, "TypeId", "") or ""
    return not any(tip.startswith(x) for x in _KATI_BEKLENMEYEN)


def _sayi(x) -> str:
    try:
        return f"{float(x):.6g}"
    except Exception:
        return str(x)


def _mesh_al(o):
    """Nesnenin mesh'i (Mesh::Feature) ya da None. ASLA patlamaz."""
    try:
        m = getattr(o, "Mesh", None)
    except Exception:
        return None
    # Mesh::Feature'in Mesh'i bir MeshObject; baska tiplerde ayni adda
    # alakasiz bir ozellik olabilir, o yuzden metoda bakiyoruz.
    return m if m is not None and hasattr(m, "CountFacets") else None


def _bir_mesh(o, m, rapor: Rapor) -> None:
    """Mesh nesnesinin kontrolu.

    NEDEN AYRI BIR YOL. Mesh::Feature'in `Shape`'i YOKTUR. Eski surumde
    _bir_nesne ilk satirda `Shape is None` diye donuyordu, yani mesh'ler
    dogrulamanin gozune HIC gorunmuyordu. Gunluk incelemesi (2026-08-21)
    bunun bedelini olctu: son dort gercek oturumun ana nesnesi mesh idi ve
    bu katman o oturumlarin hicbirinde tek bir kontrol kosmadi. Monkey
    indirilen modeli mesh olarak getirdigi icin asil is akisi da bu.

    `isSolid()` DE YALAN SOYLUYOR — olculdu: birbirinin icine giren iki
    kutunun mesh'i icin isSolid() -> True, hasSelfIntersections() -> True,
    countComponents() -> 2. Yani "kapali" olmak yetmiyor; kesisme ve parca
    sayisi ayrica sorulmali. isValid() icin bulunan kalibin (bkz. modul
    basligi) mesh'teki karsiligi.

    MALIYET (olculdu, 12850 facet): isSolid 0.008, hasSelfIntersections
    0.024, hasNonManifolds 0.005, countComponents 0.001 sn. Toplami sure
    butcesinin ellide biri — hepsi kosuyor.
    """
    ad = o.Name
    hazir, engeller, olcumler = baskiya_hazir_mesh(m)

    for tur, ayrinti in engeller:
        rapor.bulgular.append(Bulgu(ad, tur, ayrinti))
    if olcumler:
        rapor.olcumler.append(f"{ad}: " + " ".join(olcumler))
    # Bu satir modelin "hazir mi" sorusuna kanaatle degil olcumle cevap
    # vermesi icin. Kullanici bunu neredeyse her oturumda soruyor.
    rapor.olcumler.append(
        f"{ad}: baskiya hazir = {'EVET' if hazir else 'HAYIR'}")


def baskiya_hazir_mesh(m) -> tuple[bool, list[tuple[str, str]], list[str]]:
    """(hazir_mi, [(tur, ayrinti)...], [olcum...]). ASLA patlamaz.

    "Baskiya hazir" = 3B yazicinin dilimleyicisinin kabul edecegi hal:
    kapali (su sizdirmaz), kendiyle kesismeyen, non-manifold noktasi
    olmayan, tek parca ve hacmi pozitif bir mesh. Bunlarin hepsini FreeCAD
    hazir veriyor; tek eksik onlari soruyor olmakti.
    """
    engeller: list[tuple[str, str]] = []
    olcumler: list[str] = []

    def sor(cagri, varsayilan=None):
        try:
            return cagri()
        except Exception:
            return varsayilan

    facet = sor(lambda: int(m.CountFacets), 0)
    olcumler.append(f"facet={facet}")

    b = sor(lambda: m.BoundBox)
    if b is not None:
        olcumler.append(f"bbox={_sayi(b.XLength)}x{_sayi(b.YLength)}"
                        f"x{_sayi(b.ZLength)} mm")

    hacim = sor(lambda: float(m.Volume))
    if hacim is not None:
        olcumler.append(f"hacim={_sayi(hacim)} mm3")

    kapali = sor(lambda: bool(m.isSolid()))
    if kapali is False:
        engeller.append(("kapali degil",
                         "mesh su sizdirmaz degil (acik kenar/delik var); "
                         "dilimleyici bunu ya reddeder ya da tahmin ederek "
                         "kapatir"))

    kesisme = sor(lambda: bool(m.hasSelfIntersections()))
    if kesisme:
        engeller.append(("kendiyle kesisme",
                         "yuzeyler birbirinin icinden geciyor. isSolid() "
                         "bunu YAKALAMAZ — olculdu"))

    manifold = sor(lambda: bool(m.hasNonManifolds()))
    if manifold:
        engeller.append(("non-manifold",
                         "bir kenari ikiden fazla yuzey paylasiyor; "
                         "dilimleyicide delik/artifact uretir"))

    bozuk = sor(lambda: bool(m.hasCorruptedFacets()))
    if bozuk:
        engeller.append(("bozuk facet", "dejenere ucgen var"))

    parca = sor(lambda: int(m.countComponents()), 1)
    if parca is not None:
        olcumler.append(f"parca={parca}")
        if parca > 1:
            engeller.append((
                "cok parca",
                f"{parca} ayri kabuk var. Kasitliysa sorun degil; degilse "
                f"biri artik parcadir — kulp ayirma denemelerinde tam bu "
                f"olusuyordu"))

    if hacim is not None and hacim <= 0 and facet:
        engeller.append(("hacim pozitif degil",
                         f"hacim {_sayi(hacim)} — normaller ters donmus "
                         f"olabilir (flipNormals/harmonizeNormals)"))

    return (not engeller), engeller, olcumler


def _desen_kontrolu(o, sekil, rapor: Rapor) -> None:
    """PartDesign deseni GERCEKTEN cogaltmis mi?

    OLCULDU ve bu, sessiz yanlisin en kotu turu: `PartDesign::PolarPattern`
    bir PRIMITIF uzerinde (AdditiveCylinder gibi) calistirildiginda hata
    VERMIYOR, State "Up-to-date" diyor, hacim degismiyor — yani tek kopya
    birakiyor. Model "6 delik actim" der, belgede bir delik vardir.
    (Desenler yalnizca ESKIZ TABANLI ozelliklerde — Pad/Pocket — calisiyor.)

    Kontrol: desenin sekli, beslendigi BaseFeature'in seklinden farkli
    olmali. Ayni hacimse desen GORUNMEZ kalmistir.
    """
    tip = getattr(o, "TypeId", "") or ""
    if not any(tip.endswith(x) for x in
               ("PolarPattern", "LinearPattern", "Mirrored", "MultiTransform")):
        return
    try:
        taban = getattr(o, "BaseFeature", None)
        if taban is None or taban.Shape is None:
            return
        h1 = float(sekil.Volume)
        h0 = float(taban.Shape.Volume)
    except Exception:
        return
    if h0 and abs(h1 - h0) <= max(1e-6, 1e-6 * abs(h0)):
        rapor.bulgular.append(Bulgu(
            o.Name, "desen tek kopya birakti",
            f"hacim {_sayi(h1)} — {taban.Name} ile AYNI, yani desen "
            f"uygulanmadi. Hata verilmez ve State 'Up-to-date' gorunur. "
            f"Genellikle sebep: desen bir PRIMITIFE baglanmis; yalnizca "
            f"eskiz tabanli ozellikte (Pad/Pocket) calisir. Ayrica "
            f"Originals dolu mu ve body.Tip desene tasinmis mi bak"))


def _bir_nesne(o, rapor: Rapor) -> None:
    """Tek nesnenin kontrolu. Hicbir kosulda ISTISNA FIRLATMAZ.

    Dogrulama, calismasi basarili olmus bir islemin ustune kosuyor. Burada
    patlamak, iyi biten bir isi kotu bitirmek olur.
    """
    ad = o.Name
    try:
        sekil = getattr(o, "Shape", None)
    except Exception:
        sekil = None

    if sekil is None:
        m = _mesh_al(o)
        if m is not None:
            _bir_mesh(o, m, rapor)
        return

    try:
        if sekil.isNull():
            if _kati_beklenir_mi(o):
                rapor.bulgular.append(Bulgu(ad, "bos sekil",
                                            "nesnenin sekli yok"))
            return
    except Exception:
        return

    _desen_kontrolu(o, sekil, rapor)

    try:
        if not sekil.isValid():
            rapor.bulgular.append(
                Bulgu(ad, "gecersiz topoloji",
                      "Shape.isValid() False — sonraki boolean'lar bunun "
                      "uzerine kurulursa hata ZINCIRIN SONUNDA cikar"))
    except Exception:
        pass

    # --- hacim isareti: KATI KATI, asla toplayarak degil -------------------
    katilar = []
    try:
        katilar = list(sekil.Solids)
    except Exception:
        pass

    if katilar:
        toplam = 0.0
        for i, k in enumerate(katilar, start=1):
            try:
                h = float(k.Volume)
            except Exception:
                continue
            toplam += h
            if h < 0:
                rapor.bulgular.append(
                    Bulgu(ad, "ters kati",
                          f"kati {i} hacmi negatif ({_sayi(h)}). isValid() "
                          f"bunu YAKALAMAZ; 3B'de dunyada delik gibi gorunur "
                          f"ve boolean'lari bozar"))
            elif h == 0:
                rapor.bulgular.append(
                    Bulgu(ad, "sifir hacim", f"kati {i} bos"))
        try:
            b = sekil.BoundBox
            rapor.olcumler.append(
                f"{ad}: kati={len(katilar)} hacim={_sayi(toplam)} mm3 "
                f"bbox={_sayi(b.XLength)}x{_sayi(b.YLength)}x"
                f"{_sayi(b.ZLength)} mm")
        except Exception:
            pass
        return

    # --- kati yoksa: kabuk kapali mi ---------------------------------------
    kabuklar = []
    try:
        kabuklar = list(sekil.Shells)
    except Exception:
        pass

    if kabuklar:
        acik = 0
        for k in kabuklar:
            try:
                if not k.isClosed():
                    acik += 1
            except Exception:
                pass
        if acik:
            rapor.bulgular.append(
                Bulgu(ad, "acik kabuk",
                      f"{acik} kabuk kapali degil — isValid() bunu gecirir "
                      f"ama basilamaz ve kati islemleri kabul etmez"))
        return

    # Ne kati ne kabuk: eskiz, tel, yuz. Kusur degil, bilgi.
    if _kati_beklenir_mi(o):
        try:
            rapor.olcumler.append(f"{ad}: kati degil ({sekil.ShapeType})")
        except Exception:
            pass




# Cakisma taramasinin sure butcesi. Her calistirmadan sonra kosuyor, yani
# turun gecikmesine dogrudan biniyor. Olculdu (52 nesnelik belge, dokunulan
# 1 nesne): 0.02 sn. Butce, patolojik durumlar icin tavan.
CAKISMA_BUTCESI = 1.0
# Kac cakisma bulgusu tek tek yazilir; fazlasi tek satirda toplanir.
# Gerekcesi olculdu (MANTIK 32): ayni bulgunun 31 kez tekrarlanmasi hem
# ciktiyi hem baglami doldurdu.
CAKISMA_AZAMI_SATIR = 5


def _akraba_mi(a, b) -> bool:
    """Iki nesne ayni bagimlilik zincirinde mi (biri otekinin girdisi mi).

    NEDEN SART: `Part::Cut`in Base ve Tool nesneleri belgede DURUR ve sonuc
    onlarla tamamen ust uste biner (olculdu: Kesilmis.OutList = [A, B]).
    Bunu cakisma diye raporlamak, MANTIK 32'deki 31 kez tekrarlanan yanlis
    alarmin aynisini uretirdi — kullanicinin hicbir seyi bozuk degilken.
    """
    for x, y in ((a, b), (b, a)):
        try:
            liste = getattr(x, "OutListRecursive", None) or x.OutList
        except Exception:                                        # noqa: BLE001
            liste = []
        if any(getattr(o, "Name", None) == y.Name for o in liste):
            return True
    return False


def _cakisma_taramasi(doc, adlar, rapor: "Rapor",
                      sure_butcesi: float = CAKISMA_BUTCESI) -> None:
    """Dokunulan nesneler baska bir parcanin ICINDEN geciyor mu.

    NEDEN HOST YAPIYOR (olculdu, MANTIK 39): model uc kareye bakip
    "cakisma yok" dedi ve yanildi; kullanici gordu. Goruntu bu soruyu
    kapatamiyor — 900x640 karede ~4 piksel/mm. Modelin sormayi unutma
    ihtimalini ortadan kaldirmanin yolu, HOST'un olcup raporlamasi.

    KAPSAM DAR TUTULUYOR: yalnizca kodun dokundugu nesneler x sinir kutusu
    onlarla kesisen adaylar. 52 nesnelik belgede bile birkac cift eder;
    tam tarama (1326 cift) 0.33 sn suruyordu ve her turda odenemez.

    DEGME BULGU DEGILDIR. Bu projede yelken direge, kupeste govdeye
    bilerek deger; her temasi kusur saymak MANTIK 32'deki 31 kez
    tekrarlanan yanlis alarmi geri getirirdi. Kusur = ICINDEN GECMEK.

    TUKETILMIS NESNE DE BULGU DEGILDIR (2026-08-27). `Part::Cut` yapan bir
    tur uc nesneye birden dokunur: sonuc, taban ve takim. Taban sonucun
    icinden "geciyor" gorunur — cunku sonuc ondan oyulmustur. Olculdu
    (LOG/2026-08-27_9564dc71.txt): rapordaki bulgularin cogu buydu. Hem
    dokunulan hem aday listesinden eleniyor (bkz. kesif.tuketilmis_mi).

    GRUP DA PARCA DEGILDIR (2026-09-04). FreeCAD bir
    `App::DocumentObjectGroup`a `.Shape` VERIYOR — cocuklarin bilesigi
    (olculdu: 2 kutuluk grupta Compound, 2 kati, hacim = ikisinin toplami).
    Yani grup, cocuklarinin her cakismasini kendi adiyla IKINCI kez
    bildiriyordu. Olculdu (LOG/2026-09-04_92416f9e.txt, satir 2912-2914):
    uc BULGU satirinin ikisi yankiydi — `REF_Cihaz x D_sol_k4` ile
    `REF_Cihaz x D_sag`, ikisi de 2520 mm3, ikisi de zaten yazilmis
    `D_sol_k4 x REF_OnPanel` / `D_sag x REF_OnPanel` cifti. `_akraba_mi`
    burada yetmiyor: grubu KENDI cocuguna karsi koruyor, ama gruba karsi
    UCUNCU bir nesneyi korumuyor. Aday havuzu gruplari zaten eliyordu
    (kesif._ATLANAN); eksik olan DOKUNULAN tarafiydi.
    """
    from . import olcum

    if doc is None or not adlar:
        return

    t0 = time.time()
    from . import kesif as _kesif

    dokunulan = [doc.getObject(a) for a in adlar]
    dokunulan = [o for o in dokunulan if o is not None
                 and not _kesif._atlanir_mi(o)
                 and olcum._sekil_al(o) is not None
                 and not _kesif.tuketilmis_mi(o)]
    if not dokunulan:
        return

    # Aday havuzu: belgedeki olculebilir, hacimli/yuzeyli parcalar. Eskiz ve
    # 2B iskele disarida — kesisme egrileri her yerde cikar ve hicbiri kusur
    # degil.
    adaylar = []
    for o in _kesif.ilgili_nesneler(doc):
        s = olcum._sekil_al(o)
        if s is None or not s.Faces:
            continue
        if _kesif.tuketilmis_mi(o):
            continue
        adaylar.append(o)

    rapor.kosan.append("cakisma (dokunulan nesneler x bbox kesisen komsular; "
                       "kesme tabani/ayna kaynagi haric)")

    gecisler = []
    bakilan = 0
    bakilmayan = 0
    zaten_yazili = 0
    gorulen = set()
    for a in dokunulan:
        for b in adaylar:
            if a.Name == b.Name:
                continue
            anahtar = tuple(sorted((a.Name, b.Name)))
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            if time.time() - t0 > sure_butcesi:
                bakilmayan += 1
                continue
            if not olcum._bbox_kesisiyor_mu(a, b):
                continue
            if _akraba_mi(a, b):
                # Boolean'in girdisi sonucuyla ust uste biner; kusur degil.
                continue
            bakilan += 1
            d = olcum._cift_olc(a, b)
            if d.get("gecis"):
                # Blogun KENDI `cakisma_kontrol` ciktisi bu cifti zaten
                # yazdiysa tekrarlamiyoruz — ayni sayi, iki cumle, tek
                # istem (olculdu, LOG/2026-08-31_f5a6a5ac.txt; gerekcesi
                # olcum._bildirilen_gecisler'de).
                if olcum.gecis_bildirildi_mi(d["a"], d["b"]):
                    zaten_yazili += 1
                    continue
                gecisler.append(d)

    if bakilmayan:
        rapor.atlanan.append(
            f"cakisma: {bakilmayan} cift (sure siniri {sure_butcesi:g} sn "
            f"asildi)")

    # ONEM SIRASI. Eskiden liste belge sirasindaydi ve kesme KEYFIYDI:
    # 5 satirlik tavan, en agir gecisi listenin disinda birakabiliyordu.
    # Olculdu (LOG/2026-08-28_c503a8a4.txt): raporda 7 gecis vardi, ilk
    # 5'i yazildi ve "kalanlari cakisma_kontrol() ile gor" dendi — model
    # o cagriyi yapmadi. Artik once yutulma orani, sonra hacim: bir sey
    # kesilecekse en HAFIFI kesilsin.
    gecisler.sort(key=lambda x: (x.get("oran", 0.0), x.get("hacim", 0.0)),
                  reverse=True)
    for d in gecisler[:CAKISMA_AZAMI_SATIR]:
        rapor.bulgular.append(Bulgu(d["a"], "icinden geciyor",
                                    d["satir"].split("— ", 1)[-1]
                                    + f" ({d['b']} ile)"))
    if len(gecisler) > CAKISMA_AZAMI_SATIR:
        kalan = gecisler[CAKISMA_AZAMI_SATIR:]
        rapor.bulgular.append(Bulgu(
            f"{len(kalan)} cift daha", "icinden geciyor",
            "en agirlari yukarida (yutulma oranina gore sirali); "
            "kalanlarin en buyugu %s x %s, ortak hacim %s mm3 — "
            "hepsi icin cakisma_kontrol()"
            % (kalan[0]["a"], kalan[0]["b"],
               olcum._sayi(kalan[0].get("hacim", 0.0)))))
    # DURUSTLUK: bastirilan sey SESSIZ kalmaz. Model yukaridaki
    # `cakisma_kontrol` ciktisina bakmali, "tarama bir sey bulmadi"
    # sanmamali.
    if zaten_yazili:
        rapor.olcumler.append(
            f"cakisma: {zaten_yazili} gecis blogun kendi cakisma_kontrol "
            f"ciktisinda zaten yazili — burada tekrarlanmadi")
    if bakilan and not gecisler and not zaten_yazili:
        rapor.olcumler.append(
            f"cakisma: {bakilan} cift olculdu, icinden gecen yok "
            f"(degme kusur sayilmaz)")

def dogrula(doc, adlar, azami_nesne: int = AZAMI_NESNE,
            sure_butcesi: float = SURE_BUTCESI) -> Rapor:
    """`adlar` icindeki nesneleri deterministik olarak kontrol eder.

    `adlar` genelde kodun DOKUNDUGU nesneler (eklenen + degisen). Yalnizca
    eklenenlere bakmak yetmez: "pad.Length = 20" hicbir nesne EKLEMEZ ama
    modeli bozabilir — o durumda eski surumde hicbir kontrol kosmuyordu.
    """
    rapor = Rapor()
    if doc is None or not adlar:
        return rapor

    t0 = time.time()
    rapor.kosan = ["bos sekil", "topoloji gecerliligi",
                   "kati hacim isareti (kati kati)", "kapali kabuk",
                   "mesh: kapalilik/kesisme/manifold/parca/hacim",
                   "desen gercekten cogaltti mi"]
    # Kendiyle kesisme BRep tarafinda ucuz degil — OCC'de boolean testi
    # gerektiriyor. MESH tarafinda hazir ve ucuz (olculdu: 12850 facet'te
    # 0.024 sn), orada kosuyor.
    rapor.atlanan.append("kendiyle kesisme, KATI (BRep) nesnelerde "
                         "(OCC'de pahali; mesh'te kosuyor)")

    # GRUPLAR ELENIYOR, ve eleme SAYI SINIRINDAN ONCE. Grubun `.Shape`i
    # cocuklarinin bilesigi oldugu icin olcum satiri cocugun satirinin
    # birebir kopyasi oluyor (olculdu, sentetik belge: "GRUP: kati=1
    # hacim=1000" ile "A: kati=1 hacim=1000"), ustelik 25 nesnelik kotadan
    # slot yiyor. Gerekcesi _cakisma_taramasi'nin docstring'inde.
    from . import kesif as _kesif
    sirali = []
    for a in adlar:
        o = doc.getObject(a)
        if o is not None and _kesif._atlanir_mi(o):
            continue
        sirali.append(a)
    if len(sirali) > azami_nesne:
        rapor.atlanan.append(
            f"{len(sirali) - azami_nesne} nesne (nesne siniri {azami_nesne})")
        sirali = sirali[:azami_nesne]

    kalan_zamansiz = 0
    for i, ad in enumerate(sirali):
        if time.time() - t0 > sure_butcesi:
            kalan_zamansiz = len(sirali) - i
            break
        o = doc.getObject(ad)
        if o is None:
            continue
        rapor.bakilan += 1
        _bir_nesne(o, rapor)

    if kalan_zamansiz:
        rapor.atlanan.append(
            f"{kalan_zamansiz} nesne (sure siniri {sure_butcesi:g} sn asildi)")

    # CAKISMA TARAMASI. Nesne bazli kontrollerden AYRI, cunku sorusu farkli:
    # ötekiler "bu nesne kendi icinde saglam mi" diye sorar, bu "baska bir
    # parcanin icinden geciyor mu" diye. Olculdu (MANTIK 39): modelin
    # goruntuye bakip kacirdigi tek kusur turu buydu.
    try:
        _cakisma_taramasi(doc, adlar, rapor)
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"cakisma taramasi yapilamadi: {e}")

    rapor.sure_sn = time.time() - t0
    return rapor


class Izleyici:
    """Kodun DOKUNDUGU nesneleri toplar (App.addDocumentObserver).

    Neden gerekli: `onceki`/`sonraki` nesne kumesi farki yalnizca EKLENENI
    verir. Cok yaygin bir tur — "su pad'i 3 mm uzat" — hicbir nesne eklemez.
    Dokunulan nesne kumesi olmadan o turda kontrol edecek bir sey bulunamaz.

    Touched bayragina bakmak da yetmez: kodun kendi icinde `doc.recompute()`
    cagirmasi SERBEST ve yaygin (eskiz olusturup pad'lemek icin gerekli),
    o recompute bayraklari temizler. Gozlemci ise araya girmeden yakalar —
    olculdu.

    Geri cagrimlar ASLA istisna firlatmamali: FreeCAD'in sinyal zincirinde
    calisiyorlar.
    """

    def __init__(self) -> None:
        self.adlar: set[str] = set()
        self._acik = False

    def _ekle(self, nesne) -> None:
        try:
            self.adlar.add(nesne.Name)
        except Exception:
            pass

    # FreeCAD'in cagirdigi adlar — degistirilemez.
    def slotCreatedObject(self, nesne):
        self._ekle(nesne)

    def slotChangedObject(self, nesne, ozellik):
        self._ekle(nesne)

    def slotDeletedObject(self, nesne):
        try:
            self.adlar.discard(nesne.Name)
        except Exception:
            pass

    def bagla(self) -> None:
        try:
            App.addDocumentObserver(self)
            self._acik = True
        except Exception:
            self._acik = False

    def coz(self) -> None:
        # Sizan bir gozlemci kullanicinin HER hareketinde atesler ve sessizce
        # birikir. Cozme finally'de cagriliyor.
        if not self._acik:
            return
        try:
            App.removeDocumentObserver(self)
        except Exception:
            pass
        self._acik = False
