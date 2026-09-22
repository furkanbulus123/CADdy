"""Kutuphane — gunlukleri listeleme ve eski bir sohbeti SURDURME.

    freecadcmd.exe tests\test_kayitlar_fc.py

Sinadigi sikayet: "logdan baslatma yok galiba, sadece logu goruyorum, o
baglamda FreeCAD'de baslatamiyorum". Kutuphane dugmesi yalnizca klasoru
aciyordu; artik gunluk basligindan oturum kimligini okuyup transport'u
`--resume <oturum>` moduna aliyor.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_kayitlar.txt")
open(RAPOR, "w", encoding="utf-8").close()

gecti = basarisiz = atlandi = 0


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
    _yaz("--- %s %s" % (ad, "-" * max(0, 60 - len(ad))))


from caddy import kayitlar, sohbet_log                          # noqa: E402

GECICI = Path(tempfile.mkdtemp(prefix="caddy_kayit_"))

ORNEK = """\
========================================================================
CADdy sohbet gunlugu
oturum : 9564dc71-071d-4ca3-9c21-483cf5766739
model  : claude-opus-5
efor   : Hızlı (az düşünür)
baslama: 2026-08-27T13:39:39
========================================================================

--- KULLANICI  [13:39:55] -----------------------------------------
bana bir kucuk model araba tasarla

--- AI  (claude-opus-5 · 7.4 sn)  [13:40:03] -----------------------
Kamyonet yapacagiz — once tek soru: ne icin?

```freecad-python title="bu blok ozete girmemeli"
kutu = doc.addObject("Part::Box", "Sasi")
```

--- KULLANICI  [13:41:00] -----------------------------------------
f secenegi
"""

(GECICI / "2026-08-27_9564dc71.txt").write_text(ORNEK, encoding="utf-8")
# Kimliksiz gunluk: okunur ama surdurulemez.
(GECICI / "2026-08-01_bozuk.txt").write_text(
    "rastgele metin, baslik yok\n", encoding="utf-8")

# Siralama MTIME ile yapiliyor. Iki dosyayi ayni anda yazdigimiz icin
# damgalari elle ayirmak gerekiyor — yoksa "yeniden eskiye" testi bir sey
# sinamamis olurdu (once yazilan mi sonra yazilan mi belirsiz kalirdi).
os.utime(GECICI / "2026-08-27_9564dc71.txt", (1_000_000_200, 1_000_000_200))
os.utime(GECICI / "2026-08-01_bozuk.txt", (1_000_000_000, 1_000_000_000))

# ------------------------------------------------------------------ listele
bolum("listele — baslik ve ilk mesaj okunuyor")
ks = kayitlar.listele(GECICI)
kontrol("iki dosya da listelendi", len(ks) == 2, len(ks))
k = next((x for x in ks if x.dosya.name.startswith("2026-08-27")), None)
if k is None:
    atlandi += 1
    _yaz("  ATLA  ornek kayit bulunamadi")
else:
    _yaz("       etiket: %s" % k.etiket())
    kontrol("oturum kimligi basliktan okundu",
            k.oturum == "9564dc71-071d-4ca3-9c21-483cf5766739", k.oturum)
    kontrol("model okundu", k.model == "claude-opus-5", k.model)
    kontrol("ilk KULLANICI mesaji ozete girdi",
            k.ilk_mesaj.startswith("bana bir kucuk"), k.ilk_mesaj)
    kontrol("tur sayisi KULLANICI bloklarini sayiyor", k.tur == 2, k.tur)
    kontrol("surdurulebilir", k.surdurulebilir is True)

bozuk = next((x for x in ks if x.dosya.name.startswith("2026-08-01")), None)
kontrol("kimliksiz gunluk SURDURULEMEZ isaretli",
        bozuk is not None and not bozuk.surdurulebilir,
        getattr(bozuk, "oturum", "?"))
kontrol("yeniden eskiye siralaniyor",
        ks[0].dosya.name.startswith("2026-08-27"), ks[0].dosya.name)
kontrol("olmayan klasor bos liste dondurur",
        kayitlar.listele(GECICI / "yok") == [])

# ------------------------------------------------------------- son mesajlar
bolum("son_mesajlar — hatirlatma metni")
sm = kayitlar.son_mesajlar(GECICI / "2026-08-27_9564dc71.txt")
_yaz("       %r" % [(r, m[:30]) for r, m in sm])
kontrol("uc blok cikti", len(sm) == 3, len(sm))
kontrol("roller dogru", [r for r, _ in sm] == ["kullanici", "ai", "kullanici"],
        [r for r, _ in sm])
kontrol("KOD BLOGU ozete girmiyor",
        all("addObject" not in m for _, m in sm), sm)

# ------------------------------------------------------ gunluge devam etme
bolum("sohbet_log.dosyaya_devam — ayni dosyaya yaziyor")
g = sohbet_log.SohbetGunlugu(GECICI)
hedef = GECICI / "2026-08-27_9564dc71.txt"
onceki_boyut = hedef.stat().st_size
g.dosyaya_devam("9564dc71-071d-4ca3-9c21-483cf5766739", hedef)
g.kullanici("devam eden mesaj")
metin = hedef.read_text(encoding="utf-8")
kontrol("yeni dosya ACILMADI", len(list(GECICI.glob("*.txt"))) == 2,
        [p.name for p in GECICI.glob("*.txt")])
kontrol("dosya buyudu", hedef.stat().st_size > onceki_boyut)
kontrol("DEVAM ayraci yazildi", "DEVAM" in metin)
kontrol("baslik TEKRARLANMADI", metin.count("CADdy sohbet gunlugu") == 1,
        metin.count("CADdy sohbet gunlugu"))
kontrol("devam mesaji dosyada", "devam eden mesaj" in metin)

# Ayni oturum icin oturum_ac cagrilirsa (her tur cagriliyor) dosyayi
# BUGUNUN adiyla yeniden acmamali — yoksa sohbet ikiye bolunurdu.
g.oturum_ac("9564dc71-071d-4ca3-9c21-483cf5766739")
g.kullanici("ikinci mesaj")
kontrol("oturum_ac dosyayi degistirmedi", g.dosya == hedef, g.dosya)
kontrol("hala tek dosya", len(list(GECICI.glob("*.txt"))) == 2,
        [p.name for p in GECICI.glob("*.txt")])

# ------------------------------------------------------------- S14: belge
bolum("S14 — surdurulen sohbetin BELGESI")

import FreeCAD as App                                            # noqa: E402

_BELGE_YOLU = str(GECICI / "S14Model.FCStd")
_d = App.newDocument("S14Model")
_d.addObject("Part::Box", "Sasi")
_d.recompute()
_d.saveAs(_BELGE_YOLU)

# --- ON KABUL: bu maddenin dayandigi iki olcum -------------------------
kontrol("ON KABUL: zaten acik dosyayi openDocument IKINCI KOPYA URETMIYOR",
        App.openDocument(_BELGE_YOLU) is _d
        and list(App.listDocuments()).count("S14Model") == 1)

_eski_ad = _d.Name
App.closeDocument(_eski_ad)
_yeniden = App.openDocument(_BELGE_YOLU)

# Adin DOSYA ADINDAN turedigini gostermek icin ikisinin AYRILDIGI bir
# ornek gerekiyor: ad ile dosya adi ayni oldugunda esitlik hicbir sey
# kanitlamaz. Ilk olcum de boyle yakalanmisti (ProbeAc -> caddy_probe_ac).
_ayrik = App.newDocument("IcAdiBaska")
_ayrik.saveAs(str(GECICI / "DosyaAdiBaska.FCStd"))
App.closeDocument(_ayrik.Name)
_ayrik2 = App.openDocument(str(GECICI / "DosyaAdiBaska.FCStd"))
kontrol("ON KABUL: belge ADI oturumlar arasi SABIT DEGIL — kimlik YOLDUR",
        _ayrik2.Name != "IcAdiBaska" and _ayrik2.Name == "DosyaAdiBaska",
        "acilan ad=%s" % _ayrik2.Name)
App.closeDocument(_ayrik2.Name)
kontrol("ON KABUL: yeniden acilan belgede nesne adlari duruyor",
        [o.Name for o in _yeniden.Objects] == ["Sasi"])


def _gunluk_yaz(ad, belge, dosya):
    """Baslikta belge/dosya satiri olan bir gunluk uretir."""
    metin = ORNEK.replace("efor   : Hızlı (az düşünür)",
                          "efor   : Hızlı (az düşünür)\n"
                          "belge  : %s\ndosya  : %s" % (belge, dosya))
    (GECICI / ad).write_text(metin, encoding="utf-8")
    return metin


def _kayit(ad):
    return next(k for k in kayitlar.listele(GECICI) if k.dosya.name == ad)


# --- 1) ACIK ------------------------------------------------------------
_gunluk_yaz("2026-08-30_acik.txt", "S14Model", _BELGE_YOLU)
k = _kayit("2026-08-30_acik.txt")
kontrol("basliktan belge adi okundu", k.belge == "S14Model", k.belge)
kontrol("basliktan dosya yolu okundu", k.belge_yolu == _BELGE_YOLU,
        k.belge_yolu)
d = kayitlar.belge_durumu(k)
kontrol("belge acikken durum ACIK", d["durum"] == kayitlar.DURUM_ACIK,
        d["durum"])
kontrol("acik dalinda belge nesnesi geliyor", d["belge"] is _yeniden)

# Yol yazimi farkliysa da ayni dosya sayilmali (Windows: buyuk/kucuk harf).
_gunluk_yaz("2026-08-30_harf.txt", "S14Model", _BELGE_YOLU.upper())
kontrol("buyuk/kucuk harf ayni dosyayi ayirmiyor",
        kayitlar.belge_durumu(_kayit("2026-08-30_harf.txt"))["durum"]
        == kayitlar.DURUM_ACIK)

# --- 2) KAPALI ----------------------------------------------------------
App.closeDocument(_yeniden.Name)
d = kayitlar.belge_durumu(_kayit("2026-08-30_acik.txt"))
kontrol("belge kapaliyken durum KAPALI", d["durum"] == kayitlar.DURUM_KAPALI,
        d["durum"])
kontrol("kapali mesaji dosya yolunu yaziyor", _BELGE_YOLU in d["mesaj"])
doc, hata = kayitlar.belgeyi_ac(d["yol"])
kontrol("belgeyi_ac gercekten aciyor", doc is not None and hata == "", hata)
kontrol("acildiktan sonra durum ACIK'a donuyor",
        kayitlar.belge_durumu(_kayit("2026-08-30_acik.txt"))["durum"]
        == kayitlar.DURUM_ACIK)
App.closeDocument(doc.Name)

# --- 3) KAYIP -----------------------------------------------------------
_yok = str(GECICI / "TasinmisModel.FCStd")
_gunluk_yaz("2026-08-30_kayip.txt", "TasinmisModel", _yok)
d = kayitlar.belge_durumu(_kayit("2026-08-30_kayip.txt"))
kontrol("dosya yoksa durum KAYIP", d["durum"] == kayitlar.DURUM_KAYIP,
        d["durum"])
kontrol("kayip mesaji yolu ve sonucu SOYLUYOR",
        _yok in d["mesaj"] and "açık olan belgede" in d["mesaj"])
doc, hata = kayitlar.belgeyi_ac(_yok)
kontrol("olmayan dosyada belgeyi_ac patlamiyor, hata METNI donuyor",
        doc is None and bool(hata), hata[:60])

# --- 4) KAYDEDILMEMIS ---------------------------------------------------
_gunluk_yaz("2026-08-30_kayitsiz.txt", "Adsız (Unnamed)", "(kaydedilmemis)")
k = _kayit("2026-08-30_kayitsiz.txt")
kontrol("yer tutucu YOL sayilmiyor", k.belge_yolu == "", k.belge_yolu)
d = kayitlar.belge_durumu(k)
kontrol("yol yoksa durum KAYDEDILMEMIS",
        d["durum"] == kayitlar.DURUM_KAYDEDILMEMIS, d["durum"])
kontrol("kaydedilmemis mesaji belge adini yaziyor", "Adsız" in d["mesaj"])
kontrol("ic ad parantezden cikariliyor (yedek dosyasi Name ile adlandirilir)",
        kayitlar._ic_ad("Adsız (Unnamed)") == "Unnamed"
        and kayitlar._ic_ad("Araba") == "Araba")

# --- 5) BILINMIYOR — eski gunlukler -------------------------------------
d = kayitlar.belge_durumu(_kayit("2026-08-27_9564dc71.txt"))
kontrol("baslikta belge satiri yoksa durum BILINMIYOR",
        d["durum"] == kayitlar.DURUM_BILINMIYOR, d["durum"])
kontrol("bilmedigimiz seyi UYARI diye yazmiyoruz", d["mesaj"] == "")

# --- 6) Kullanici mesaji basligi taklit edemesin -------------------------
_metin = _gunluk_yaz("2026-08-30_taklit.txt", "S14Model", _BELGE_YOLU)
(GECICI / "2026-08-30_taklit.txt").write_text(
    _metin.replace("bana bir kucuk model araba tasarla",
                   "dosya : C:\sahte\Tuzak.FCStd"), encoding="utf-8")
kontrol("mesajdaki 'dosya :' satiri basligin yerine gecmiyor",
        _kayit("2026-08-30_taklit.txt").belge_yolu == _BELGE_YOLU,
        _kayit("2026-08-30_taklit.txt").belge_yolu)

# --- 7) Gunluk basligi belgeyi GERCEKTEN yaziyor mu ---------------------
_d2 = App.newDocument("S14Yazim")
_d2.saveAs(str(GECICI / "S14Yazim.FCStd"))
App.setActiveDocument(_d2.Name)
_g = sohbet_log.SohbetGunlugu(GECICI / "yazim")
_g.oturum_ac("aaaabbbb-0000-0000-0000-000000000000")
_g.kullanici("merhaba")
_bas = _g.dosya.read_text(encoding="utf-8")
kontrol("baslikta belge satiri var ve dolu",
        "belge  : S14Yazim" in _bas, _bas[:400])
kontrol("baslikta dosya yolu var ve dolu",
        "dosya  : " in _bas and "S14Yazim.FCStd" in _bas)
kontrol("yol bulununca bir daha aranmiyor", _g._belge_yazildi is True)

# Surdurme ESKI basligi bozmamali — S14'un butun anlami o satirda.
_g2 = sohbet_log.SohbetGunlugu(GECICI / "yazim")
_g2.dosyaya_devam("aaaabbbb-0000-0000-0000-000000000000", _g.dosya)
App.closeDocument(_d2.Name)
_g2.kullanici("devam")
kontrol("surdurulen gunlugun ESKI belge satiri korunuyor",
        "belge  : S14Yazim" in _g.dosya.read_text(encoding="utf-8"))
App.closeDocument(App.getDocument("S14Model").Name) \
    if "S14Model" in App.listDocuments() else None


# ------------------------------------------------------- transport --resume
bolum("transport.oturumu_surdur — argumanlar --resume oluyor")
try:
    from PySide import QtWidgets                                # noqa: E402

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from caddy.transport import transport as T                  # noqa: E402

    t = T.KaliciTransport()
    kontrol("ON KABUL: yeni oturum ILK TUR modunda", t._ilk_tur is True)
    argv1 = t._argv()
    kontrol("ON KABUL: ilk tur --session-id kullaniyor",
            "--session-id" in argv1 and "--resume" not in argv1, argv1[-6:])

    t.oturumu_surdur("9564dc71-071d-4ca3-9c21-483cf5766739")
    argv2 = t._argv()
    kontrol("surdurunce --resume'a geciyor",
            "--resume" in argv2 and "--session-id" not in argv2, argv2[-6:])
    kontrol("kimlik dogru gecti",
            argv2[argv2.index("--resume") + 1]
            == "9564dc71-071d-4ca3-9c21-483cf5766739")
    kontrol("bos kimlik SESSIZCE yok sayiliyor",
            (t.oturumu_surdur(""), t.oturum)[1]
            == "9564dc71-071d-4ca3-9c21-483cf5766739", t.oturum)
except Exception as e:                                           # noqa: BLE001
    import traceback

    atlandi += 1
    _yaz("  ATLA  transport: %s" % str(e)[:150])
    _yaz(traceback.format_exc()[-500:])

import shutil                                                    # noqa: E402

shutil.rmtree(GECICI, ignore_errors=True)

_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d   ATLANDI %d" % (gecti, basarisiz, atlandi))
_yaz("=" * 70)
