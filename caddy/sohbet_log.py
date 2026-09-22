"""Sohbet gunlugu - her mesajdan sonra oturumu diske yazar.

Yer: <eklenti>/LOG/<tarih>_<oturum>.txt  (ornek: 2026-08-18_0c44b5ad.txt)

Neden dosya basina OTURUM: her sohbet kendi dosyasinda durur, "Yeni sohbet"e
basinca yeni dosya acilir. Boylece bir isi sonradan bulmak kolay.

Neden HER MESAJDAN SONRA yaziliyor (tamponlamadan): FreeCAD cokerse ya da
kullanici pencereyi kapatirsa konusma kaybolmasin. Tur basina birkac KB'lik
bir ekleme, maliyeti yok.

KURAL: buradaki hicbir hata paneli etkilemez. Disk dolu, yol yazilamaz, dosya
kilitli - hepsi sessizce yutulur ve yalnizca FreeCAD gunlugune duser. Sohbet
kaydi, sohbetin kendisinden onemli degildir.

BASLIK TEMBEL YAZILIR. Eskiden `oturum_ac` cagrilir cagrilmaz dosya acilip
baslik basiliyordu; oturum acilip hic mesaj yazilmayinca geriye 298 baytlik
bos bir dosya kaliyordu. OLCULDU (2026-08-26): LOG/ altinda 106 dosyanin
43'u tam olarak buydu. Artik baslik ILK GERCEK KAYDA kadar bekliyor —
konusulmayan oturum dosya uretmez.

TEST KOKU. Kok dizin `CADDY_LOG_DIR` ortam degiskeniyle degistirilebilir.
Sebebi olculdu: testler gercek LOG/ klasorune yaziyordu (kucuk dosyalarin
icerigi "SilenKutu", "patlayan", "birinci hata" gibi test verileriydi) ve
suite her kosuşta ~10 dosya birakiyordu.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

from . import log

_GECERSIZ = re.compile(r"[^A-Za-z0-9_.-]")


def _acik_belge() -> tuple:
    """(etiket, dosya_yolu) — belge yoksa ('', '').

    FreeCAD ithali KORUMALI: gunluk modulu testlerde ve bassiz araclarda
    FreeCAD olmadan da yuklenebilmeli. Bu dosyanin kurali degismedi —
    buradaki hicbir hata paneli etkilemez.
    """
    try:
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return "", ""
        ad = str(getattr(doc, "Name", "") or "")
        etiket = str(getattr(doc, "Label", "") or ad)
        # Ikisi de yaziliyor cunku ikisi de gerekli: ETIKET kullaniciya
        # gosterilen isim, AD ise yedek dosyasinin adi (`_yedek_al`
        # `doc.Name` kullaniyor). Ayrildiklarinda birini secmek, digerini
        # arayan tarafi kor birakirdi.
        return (etiket if etiket == ad else f"{etiket} ({ad})",
                str(getattr(doc, "FileName", "") or ""))
    except Exception:                                            # noqa: BLE001
        return "", ""


class SohbetGunlugu:
    def __init__(self, kok: Path | None = None) -> None:
        from . import config

        cevre = os.environ.get("CADDY_LOG_DIR", "").strip()
        self._kok = Path(kok) if kok else Path(
            cevre or (config.eklenti_dizini() / "LOG"))
        self._dosya: Path | None = None
        self._oturum = ""
        self._kapali = False        # bir kez patlarsa bir daha denemeyiz
        self._model_yazildi = False
        # Belge kimligi de basliga giriyor (S14). Dosya yolu oturum
        # ORTASINDA dogabilir: kullanici cogunlukla isin sonunda
        # kaydediyor. O yuzden yol bulunana kadar her kayitta bakilir,
        # bulununca bir daha dokunulmaz.
        self._belge_yazildi = False
        # HENUZ YAZILMAMIS baslik satirlari. Bos liste = yazilacak baslik yok
        # (ya zaten yazildi ya da var olan dosyaya devam ediliyor).
        self._baslik: list[str] = []

    # -- yasam dongusu -----------------------------------------------------

    def dosyaya_devam(self, oturum: str, dosya: Path) -> None:
        """Var olan bir gunluk dosyasina DEVAM eder (kutuphaneden surdurme).

        Neden `oturum_ac` yetmiyor: dosya adi BUGUNUN tarihinden uretiliyor.
        Dun baslamis bir sohbeti surdururken `oturum_ac` bugunun adiyla
        IKINCI bir dosya acardi ve ayni sohbet iki parcaya bolunurdu. Burada
        yol disaridan geliyor, baslik tekrar yazilmiyor, araya gorunur bir
        ayrac koyuluyor — sonradan okurken "burada FreeCAD yeniden acildi"
        bilgisi kaybolmasin.
        """
        self._oturum = oturum or "oturumsuz"
        self._dosya = Path(dosya)
        self._baslik = []
        self._model_yazildi = True      # baslik zaten var, dokunma
        # Surdurulen gunlugun basligi ESKI belgeyi yaziyor ve S14'un
        # butun meselesi o: uzerine simdi acik olani yazarsak sohbetin
        # hangi modelde gectigi bilgisini kendi elimizle sileriz.
        self._belge_yazildi = True
        zaman = datetime.datetime.now().isoformat(timespec="seconds")
        self._ekle("", "-" * 72,
                   f"DEVAM — sohbet kutuphaneden surduruldu  [{zaman}]",
                   "-" * 72)

    def oturum_ac(self, oturum: str, model: str = "") -> None:
        """Bir oturum = bir dosya. Ayni oturum icin tekrar cagrilirsa hicbir sey yapmaz.

        Erken donus onemli: dosya adi bugunun tarihinden uretiliyor, ama
        oturum kimligi ayniysa yolu YENIDEN HESAPLAMIYORUZ. Yoksa gece
        yarisini gecen bir sohbet ikinci bir dosyaya bolunurdu.

        DISKE DOKUNMAZ. Yalnizca yolu hesaplar ve basligi HAZIRLAR; ilk
        gercek kayit gelince `_ekle` onu dosyanin basina yaziyor. Bos
        oturumun dosya birakmamasinin sebebi bu (bkz. modul basligi).
        """
        oturum = oturum or "oturumsuz"
        if self._dosya is not None and oturum == self._oturum:
            return

        self._oturum = oturum
        self._model_yazildi = bool(model)
        kisa = _GECERSIZ.sub("", oturum)[:8] or "oturumsuz"
        gun = datetime.date.today().isoformat()
        self._dosya = self._kok / f"{gun}_{kisa}.txt"

        if self._dosya.exists():
            self._baslik = []        # ayni dosyaya devam, basligi tekrarlama
            return

        # EFOR da basliga giriyor. Modeli eklerken bunu unutmustuk ve hemen
        # ardindan gelen oturumda "hangi efor seviyesiyle calisti" sorusunu
        # gunluge bakarak cevaplayamadik — oysa gecikmenin %91-94'unu o
        # belirliyor (bkz. config.EFORLAR).
        try:
            from . import config

            e = config.efor()
            efor_metni = next((x[2] for x in config.EFORLAR if x[0] == e),
                              e or "(varsayilan)")
        except Exception:                                        # noqa: BLE001
            efor_metni = "(okunamadi)"

        self._baslik = [
            "=" * 72,
            "CADdy sohbet gunlugu",
            f"oturum : {self._oturum}",
            f"model  : {model or '(bilinmiyor)'}",
            f"efor   : {efor_metni}",
            "belge  : (bilinmiyor)",
            "dosya  : (kaydedilmemis)",
            f"baslama: {datetime.datetime.now().isoformat(timespec='seconds')}",
            "=" * 72,
        ]

    # -- kayit -------------------------------------------------------------

    def kullanici(self, metin: str) -> None:
        self._blok("KULLANICI", metin)

    def otomatik(self, metin: str) -> None:
        """Panelin KENDILIGINDEN gonderdigi tur (gorsel kontrol, hata onarimi).

        Ayri basligi var cunku eskiden bunlar da "KULLANICI" diye
        kaydediliyordu ve gunluge sonradan bakan biri (ki bu projede kalite
        analizinin tek kaynagi gunlukler) insanin yazdigi mesajlarla
        otomatik turlari ayirt edemiyordu.
        """
        self._blok("OTOMATIK", metin)

    def ai(self, metin: str, model: str = "", sure_sn: float = 0.0,
           token: str = "") -> None:
        if model:
            self._basliga_model_yaz(model)
        ek = " · ".join(x for x in (model,
                                    f"{sure_sn:.1f} sn" if sure_sn else "",
                                    token) if x)
        self._blok("AI" + (f"  ({ek})" if ek else ""), metin)

    def _basliga_model_yaz(self, model: str) -> None:
        """Baslikta duran '(bilinmiyor)' yerine gercek modeli koyar.

        NEDEN. Baslik oturum acilirken yaziliyor, model ise ilk yanit
        donunce belli oluyor; arada kalan bu bosluk yuzunden LOG/'daki her
        dosyanin tepesinde `model : (bilinmiyor)` yaziyordu. Iki modeli
        karsilastirmaya baslayinca (2026-08-24: ayni tavsan, once Sonnet
        sonra Opus) bu gercek bir engel oldu — dosyanin basina bakip hangi
        modelle calisildigini anlamak mumkun degildi, her turu tek tek
        okumak gerekiyordu.

        Bir kez yazilir. Kullanici oturum ortasinda model degistirirse
        baslik ILK modeli gosterir; tur satirlari zaten her turun kendi
        modelini yaziyor, dogru yer orasi.
        """
        if self._model_yazildi or self._kapali or self._dosya is None:
            return
        self._model_yazildi = True        # basarisiz olsa da tekrar denemeyiz
        self._baslik_satirini_degistir("model  : (bilinmiyor)",
                                       f"model  : {model}")

    def _baslik_satirini_degistir(self, eski: str, yeni: str) -> bool:
        """Basliktaki tek bir satiri yerinde degistirir.

        Iki durumu birden idare etmek zorunda, cunku baslik TEMBEL yaziliyor:
        henuz diske inmemisse bekleyen listede duzeltilir, inmisse dosya
        okunup yazilir. Ayrimi cagiranlara birakmak, ayni hatayi iki yerde
        yapma davetiydi.
        """
        if self._kapali or self._dosya is None:
            return False
        if self._baslik:
            if eski not in self._baslik:
                return False
            self._baslik = [yeni if s == eski else s for s in self._baslik]
            return True
        try:
            metin = self._dosya.read_text(encoding="utf-8")
            if eski not in metin:
                return False
            self._dosya.write_text(metin.replace(eski, yeni, 1),
                                   encoding="utf-8")
            return True
        except Exception as e:                                   # noqa: BLE001
            log.ayik(f"gunluk basligi guncellenemedi: {e}")
            return False

    def _belgeyi_tazele(self) -> None:
        """Baslikta duran belge/dosya satirlarini gercek degerlerle doldurur.

        NEDEN BU MADDE VAR (PLAN S14). Kutuphaneden bir sohbeti surdurunce
        sohbet doğru geliyor ama BELGE gelmiyordu: kod o an acik olan
        belgede kosuyor. Adlar cakisirsa (Kutu, Govde, Taban — hic uzak bir
        ihtimal degil) sessizce yanlis model degisir. Uyarabilmek icin once
        sohbetin HANGI belgede gectigini kaydetmek gerekiyor; kaydedilmeyen
        sey sonradan karsilastirilamaz.

        KIMLIK DOSYA YOLUDUR, AD DEGIL. Olculdu (freecadcmd, 2026-08-31):
        `ProbeAc` adiyla acilan belge kaydedilip kapatilip yeniden acilinca
        `caddy_probe_ac` oldu — ic ad dosya adindan YENIDEN turetiliyor.
        Yani `doc.Name` oturumlar arasi sabit degil; karsilastirma yolla
        yapilir, ad yalnizca insana gosterilir.

        Maliyet: iki oznitelik okumasi. Diske yalnizca deger DEGISTIGINDE
        dokunulur, yani tipik oturumda en fazla iki kez.
        """
        if self._belge_yazildi or self._kapali or self._dosya is None:
            return
        ad, yol = _acik_belge()
        if ad:
            self._baslik_satirini_degistir("belge  : (bilinmiyor)",
                                           f"belge  : {ad}")
        if yol:
            self._baslik_satirini_degistir("dosya  : (kaydedilmemis)",
                                           f"dosya  : {yol}")
            # Yol bulundu; artik her kayitta yeniden bakmanin anlami yok.
            self._belge_yazildi = True

    def kod(self, kod: str, baslik: str = "") -> None:
        self._blok(f"KOD ONERISI{f'  ({baslik})' if baslik else ''}", kod)

    def calisma(self, sonuc) -> None:
        satir = [f"sonuc : {'BASARILI' if sonuc.basarili else 'HATA'}",
                 f"ozet  : {sonuc.ozet}"]
        if getattr(sonuc, "yedek", ""):
            satir.append(f"yedek : {sonuc.yedek}")
        # Yalnizca YAVAS turlarda dolu (bkz. executor.YAVAS_ESIGI). Bir kez
        # 17.1 saniyelik bir tur gorduk ve gunlukte yalnizca toplam sure
        # oldugu icin sebebi sonradan bulunamadi; bir daha olursa satir
        # burada olacak.
        asama = getattr(sonuc, "asama_metni", None)
        if callable(asama):
            dokum = asama()
            if dokum:
                satir.append(f"asamalar: {dokum}")
        if sonuc.eklenen:
            satir.append(f"eklenen nesneler: {', '.join(sonuc.eklenen)}")
        dokunulan = getattr(sonuc, "dokunulan", None)
        if dokunulan:
            satir.append(f"dokunulan: {', '.join(dokunulan)}")
        for u in sonuc.uyarilar:
            satir.append(f"uyari : {u}")
        # Deterministik geometri kontrolu (MANTIK 17). Gunluge YAZILMASI sart:
        # bu projede kalite analizinin tek kaynagi gunlukler, kaydetmedigimiz
        # seyi sonradan olcemiyoruz.
        d = getattr(sonuc, "dogrulama", None)
        if d is not None:
            metin = d.metin()
            if metin:
                satir.append(metin)
        if sonuc.cikti:
            satir.append("cikti :\n" + sonuc.cikti)
        if getattr(sonuc, "engellendi", False):
            # Kod KOSMADI. Bunun gunlukte hatadan ayirt edilebilir olmasi
            # sart: sonraki kalite olcumunde "hata orani"na karismamali.
            satir.append("sebep :\n" + sonuc.hata_izi.strip())
        elif not sonuc.basarili:
            satir.append("hata izi:\n" + sonuc.hata_izi.strip())
        self._blok("CALISTIRMA", "\n".join(satir))

    def sistem(self, metin: str) -> None:
        self._blok("SISTEM", metin)

    # -- ic ---------------------------------------------------------------

    def _blok(self, baslik: str, govde: str) -> None:
        an = datetime.datetime.now().strftime("%H:%M:%S")
        self._belgeyi_tazele()
        self._ekle("", f"--- {baslik}  [{an}] " + "-" * max(0, 50 - len(baslik)),
                   (govde or "").rstrip())

    def _ekle(self, *satirlar: str) -> None:
        if self._kapali:
            return
        if self._dosya is None:
            self.oturum_ac(self._oturum or "oturumsuz")
            if self._dosya is None:
                return
        # Bekleyen baslik varsa ONCE o gider — dosya tam da bu anda dogar.
        hepsi = self._baslik + list(satirlar)
        self._baslik = []
        try:
            self._kok.mkdir(parents=True, exist_ok=True)
            with open(self._dosya, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(hepsi) + "\n")
        except Exception as e:
            # Bir kez sus, bir daha deneme - her mesajda hata basmak
            # kullaniciyi bogar ve asil ise engel olur.
            self._kapali = True
            log.uyari(f"sohbet gunlugu yazilamadi ({e}); kayit kapatildi")

    @property
    def dosya(self) -> Path | None:
        return self._dosya
