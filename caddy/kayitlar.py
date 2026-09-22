"""Gunluk klasorunu okunabilir bir KAYIT LISTESINE cevirir.

Neden ayri modul: kutuphane dugmesi eskiden yalnizca klasoru aciyordu —
kullanicinin sikayeti tam buydu: "logdan baslatma yok galiba, sadece logu
goruyorum, o baglamda FreeCAD'de baslatamiyorum". Bir sohbeti SURDUREBILMEK
icin once gunluk basligindaki oturum kimligini okumak gerekiyor; okuma isi
Qt'siz durursa bassiz test edilebilir (MANTIK §12: ui disinda Qt yok).

Surdurme, `claude --resume <oturum>` uzerinden yurur. Bu, transport'un
zaten kullandigi yol (surec olunce sonraki tur boyle devam ediyor); yeni
olan tek sey, kimligi ESKI bir gunlukten alabilmek.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

_OTURUM = re.compile(r"^oturum\s*:\s*(\S+)", re.MULTILINE)
_MODEL = re.compile(r"^model\s*:\s*(.+?)\s*$", re.MULTILINE)
_BASLAMA = re.compile(r"^baslama\s*:\s*(\S+)", re.MULTILINE)
_BELGE = re.compile(r"^belge\s*:\s*(.+?)\s*$", re.MULTILINE)
_DOSYA = re.compile(r"^dosya\s*:\s*(.+?)\s*$", re.MULTILINE)
_KULLANICI = re.compile(r"^--- KULLANICI\b.*$", re.MULTILINE)

# Basligi okumak icin dosyanin tamamini okumaya gerek yok; ilk mesaji da
# yakalayacak kadar bir parca yetiyor. Olculdu: en buyuk gunluk 195 KB,
# hepsini okumak listeyi gereksiz yavaslatirdi.
_ONBELLEK_BAYT = 4096


class Kayit:
    """Tek bir gunluk dosyasinin ozeti."""

    def __init__(self, dosya: Path, oturum: str, model: str, baslama: str,
                 ilk_mesaj: str, boyut: int, tur: int,
                 belge: str = "", belge_yolu: str = "") -> None:
        self.dosya = dosya
        self.oturum = oturum
        self.model = model
        self.baslama = baslama
        self.ilk_mesaj = ilk_mesaj
        self.boyut = boyut
        self.tur = tur
        # DIKKAT: `dosya` GUNLUK dosyasi, `belge_yolu` FreeCAD belgesidir.
        # Ikisi ayri sey; adlarin karismasi S14'te en kolay yapilacak hata.
        self.belge = belge
        self.belge_yolu = belge_yolu

    @property
    def surdurulebilir(self) -> bool:
        """Oturum kimligi yoksa `--resume` yapilamaz — dugme kapali olsun."""
        return bool(self.oturum) and self.oturum != "oturumsuz"

    def etiket(self) -> str:
        tarih = self.baslama.replace("T", " ")[:16] or self.dosya.stem
        ozet = self.ilk_mesaj or "(mesaj yok)"
        if len(ozet) > 60:
            ozet = ozet[:57] + "…"
        return "%s · %d tur · %s" % (tarih, self.tur, ozet)

    def __repr__(self) -> str:                                   # pragma: no cover
        return "<Kayit %s %s>" % (self.dosya.name, self.oturum[:8])


def _ilk_deger(desen, metin: str, yer_tutucu: str = "") -> str:
    """Basliktaki ILK eslesmeyi dondurur; yer tutucu ise bos sayar.

    Ilk eslesme, cunku baslik dosyanin tepesinde: bir kullanici mesaji
    "dosya : ..." diye baslarsa onu degil basligi almaliyiz.
    """
    m = desen.search(metin)
    if not m:
        return ""
    d = m.group(1).strip()
    return "" if d == yer_tutucu else d


def _ilk_kullanici_mesaji(metin: str) -> str:
    """Basliktan sonraki ilk KULLANICI blogunun ilk satiri."""
    m = _KULLANICI.search(metin)
    if not m:
        return ""
    for satir in metin[m.end():].splitlines():
        s = satir.strip()
        if s:
            return s
    return ""


def kok(kok_dizin: Path | None = None) -> Path:
    """Gunluk kokunu bulur — `sohbet_log` ile AYNI kural (test koku dahil)."""
    if kok_dizin is not None:
        return Path(kok_dizin)
    cevre = os.environ.get("CADDY_LOG_DIR", "").strip()
    if cevre:
        return Path(cevre)
    from . import config

    return config.eklenti_dizini() / "LOG"


def listele(kok_dizin: Path | None = None, azami: int = 60) -> list:
    """Gunlukleri YENIDEN ESKIYE dogru siralayip ozetler.

    Okunamayan dosya listeyi dusurmez, atlanir: bir bozuk dosya yuzunden
    kutuphaneyi hic acamamak, en kotu davranis olurdu.
    """
    d = kok(kok_dizin)
    if not d.is_dir():
        return []
    dosyalar = sorted((p for p in d.glob("*.txt") if p.is_file()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    kayitlar = []
    for p in dosyalar[:azami]:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                bas = f.read(_ONBELLEK_BAYT)
            oturum = (_OTURUM.search(bas).group(1) if _OTURUM.search(bas)
                      else "")
            model = (_MODEL.search(bas).group(1) if _MODEL.search(bas) else "")
            baslama = (_BASLAMA.search(bas).group(1) if _BASLAMA.search(bas)
                       else "")
            belge = _ilk_deger(_BELGE, bas, "(bilinmiyor)")
            belge_yolu = _ilk_deger(_DOSYA, bas, "(kaydedilmemis)")
            with open(p, encoding="utf-8", errors="replace") as f:
                tam = f.read()
            kayitlar.append(Kayit(
                dosya=p, oturum=oturum, model=model, baslama=baslama,
                ilk_mesaj=_ilk_kullanici_mesaji(tam),
                boyut=p.stat().st_size,
                tur=len(_KULLANICI.findall(tam)),
                belge=belge, belge_yolu=belge_yolu,
            ))
        except Exception:                                        # noqa: BLE001
            continue
    return kayitlar


def son_mesajlar(dosya: Path, adet: int = 6) -> list:
    """Panelde gostermek icin son N (rol, metin) ciftini dondurur.

    Surdururken sohbet penceresi BOS kalmasin diye: kullanici eski isine
    donduğunde ne konusuldugunu gormeli. Tam gunlugu yeniden cizmiyoruz —
    kod bloklari, dogrulama raporlari ve yedek satirlari o dosyada duruyor;
    burada amac hatirlatmak, arsivi kopyalamak degil.
    """
    try:
        metin = open(dosya, encoding="utf-8", errors="replace").read()
    except Exception:                                            # noqa: BLE001
        return []
    bloklar = []
    desen = re.compile(r"^--- (KULLANICI|AI)\b.*?-*\s*$", re.MULTILINE)
    isaretler = list(desen.finditer(metin))
    for i, m in enumerate(isaretler):
        son = isaretler[i + 1].start() if i + 1 < len(isaretler) else len(metin)
        govde = metin[m.end():son].strip()
        # Kod blogu ve arac ciktisi ozetlenerek geciyor: hatirlatma metni
        # olacak, yeniden calistirilacak bir sey degil.
        govde = re.split(r"^```", govde, maxsplit=1, flags=re.MULTILINE)[0]
        govde = govde.strip()
        if govde:
            rol = "kullanici" if m.group(1) == "KULLANICI" else "ai"
            bloklar.append((rol, govde))
    return bloklar[-adet:]


def bugun() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# BELGE ESLESTIRME (PLAN S14)
#
# Sorun kullanicinin sozuyle: "kaldigi yerden yanlis basliyor... tamam dogru
# chati duzeltiyor ama kaldigi model o degil." Sohbet `--resume` ile geliyor,
# BELGE gelmiyor; kod o an acik olan belgede kosuyor. `doc.getObject("Sasi")`
# None donerse zaten patlar ve zararsizdir — asil tehlike adlarin CAKISTIGI
# durum: iki projede de `Kutu`, `Govde`, `Taban` olmasi hic uzak degil, ve o
# zaman kod sessizce yanlis modeli degistirir.
#
# KIMLIK DOSYA YOLUDUR. Olculdu (freecadcmd 1.1.3, 2026-08-31): `ProbeAc`
# adiyla acilan belge kaydedilip kapatilip yeniden acilinca `caddy_probe_ac`
# oldu — ic ad DOSYA ADINDAN yeniden turetiliyor, oturumlar arasi sabit
# degil. Ad yalnizca insana gosterilir; karsilastirma yolla yapilir.
# Ayni olcumde: zaten acik bir dosyayi `openDocument` ile acmak IKINCI KOPYA
# URETMIYOR, ayni nesneyi donduruyor (`d2 is d`), ve olmayan dosya OSError
# veriyor. Yani asagidaki iki cagri da guvenli.
# ---------------------------------------------------------------------------

DURUM_BILINMIYOR = "bilinmiyor"
DURUM_ACIK = "acik"
DURUM_KAPALI = "kapali"
DURUM_KAYIP = "kayip"
DURUM_KAYDEDILMEMIS = "kaydedilmemis"


def _ayni_yol(a: str, b: str) -> bool:
    """Windows'ta buyuk/kucuk harf ve `..` farki ayni dosyayi ayirmasin."""
    try:
        return (os.path.normcase(os.path.abspath(str(a)))
                == os.path.normcase(os.path.abspath(str(b))))
    except Exception:                                            # noqa: BLE001
        return False


def _acik_belgeyi_bul(yol: str):
    """Yolu eslesen ACIK belgeyi dondurur, yoksa None."""
    if not yol:
        return None
    try:
        import FreeCAD as App

        for doc in list(App.listDocuments().values()):
            if _ayni_yol(getattr(doc, "FileName", "") or "", yol):
                return doc
    except Exception:                                            # noqa: BLE001
        return None
    return None


def _ic_ad(belge: str) -> str:
    """`belge` satirindan FreeCAD ic adini cikarir.

    Baslikta `Etiket (IcAd)` bicimi var (ikisi ayrildiginda); ayni ise tek
    kelime yaziliyor. Ic ad gerekli cunku YEDEK dosyalari `doc.Name` ile
    adlandiriliyor (`executor._yedek_al`).
    """
    d = (belge or "").strip()
    if d.endswith(")") and "(" in d:
        return d[d.rindex("(") + 1:-1].strip()
    return d


def _son_yedek(belge: str) -> str:
    """Bu belgeye ait EN YENI yedek kopyanin yolu; yoksa bos.

    Yedek bir ACMA hedefi DEGIL, yalnizca bilgi satiri. `_yedek_al` kopyayi
    ilk AI degisikliginden ONCE aliyor — yani icerigi isin BASINDAKI hal.
    Onu "modelin geldi" diye acmak, yapilan her seyi silinmis gostermek
    olurdu; sessiz yanlis cevabin ta kendisi.
    """
    ad = _ic_ad(belge)
    if not ad:
        return ""
    try:
        from . import config

        d = config.yedek_dizini()
        adaylar = sorted(Path(d).glob("%s_*.FCStd" % ad),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        return str(adaylar[0]) if adaylar else ""
    except Exception:                                            # noqa: BLE001
        return ""


def belge_durumu(kayit) -> dict:
    """Surdurulen sohbetin belgesi su an ne durumda — dort daldan biri.

    Karar VERMEZ, yalnizca durumu ve insan cumlesini uretir; acmak ui'nin
    isi (ve kullaniciya sorulur). Boylece bu fonksiyon Qt'siz test edilir.
    """
    yol = (getattr(kayit, "belge_yolu", "") or "").strip()
    ad = (getattr(kayit, "belge", "") or "").strip()
    sonuc = {"durum": DURUM_BILINMIYOR, "ad": ad, "yol": yol,
             "belge": None, "yedek": "", "mesaj": ""}

    if not yol:
        if not ad:
            # Eski gunlukler (baslikta belge satiri yok). Uydurmuyoruz:
            # bilmedigimiz seyi uyari diye yazmak, gercek uyarilari da
            # degersizlestirir.
            return sonuc
        sonuc["durum"] = DURUM_KAYDEDILMEMIS
        sonuc["yedek"] = _son_yedek(ad)
        sonuc["mesaj"] = (
            "Bu sohbet “%s” belgesinde geçti ama o belge hiç "
            "kaydedilmemişti — geri getirilecek dosya yok. Kod şu an açık "
            "olan belgede çalışır." % ad)
        if sonuc["yedek"]:
            sonuc["mesaj"] += ("\nİşin BAŞINDAKI hâlin bir kopyası duruyor: "
                               "%s (sohbetin sonundaki hâli değil.)"
                               % sonuc["yedek"])
        return sonuc

    doc = _acik_belgeyi_bul(yol)
    if doc is not None:
        sonuc["durum"] = DURUM_ACIK
        sonuc["belge"] = doc
        sonuc["mesaj"] = "Sohbetin belgesi (%s) zaten açık." % (
            ad or Path(yol).name)
        return sonuc

    if not Path(yol).is_file():
        sonuc["durum"] = DURUM_KAYIP
        sonuc["mesaj"] = (
            "Bu sohbet şu dosyada çalışıyordu ama dosya orada değil:\n%s\n"
            "Taşınmış ya da silinmiş olabilir. Kod şu an açık olan belgede "
            "çalışır." % yol)
        return sonuc

    sonuc["durum"] = DURUM_KAPALI
    sonuc["mesaj"] = ("Bu sohbet “%s” belgesinde çalışıyordu:\n%s"
                      % (ad or Path(yol).name, yol))
    return sonuc


def belgeyi_ac(yol: str):
    """Belgeyi acar (zaten acikse ayni nesneyi dondurur) ve etkin yapar.

    Donen: (belge, hata_metni). Belge None ise hata metni doludur — panelde
    gosterilecek; sessizce yutmak, kullanicinin "acildi mi acilmadi mi"
    bilmemesi demek olurdu.
    """
    try:
        import FreeCAD as App

        doc = App.openDocument(str(yol))
    except Exception as e:                                       # noqa: BLE001
        return None, "Belge açılamadı: %s" % e
    try:
        App.setActiveDocument(doc.Name)
        App.ActiveDocument = doc
    except Exception:                                            # noqa: BLE001
        pass
    try:
        import FreeCADGui as Gui

        # GUI'de her belge kendi sekmesi; acmak acik belgeni KAPATMAZ,
        # yanina sekme gelir. Odagi da oraya tasiyoruz ki kullanici
        # bastigi seyin sonucunu gorsun.
        Gui.ActiveDocument = Gui.getDocument(doc.Name)
    except Exception:                                            # noqa: BLE001
        # Bassiz calisma (freecadcmd) ve testler buraya duser — belge yine
        # de acildi, hata degil.
        pass
    return doc, ""
