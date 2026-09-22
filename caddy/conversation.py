"""Tur orkestrasyonu - panel ile tasima/calistirma arasindaki beyin.

Arayuz BILMEZ (widget import etmez); yalnizca sinyal yayar. Boylece sohbet
mantigi arayuzden bagimsiz test edilebilir.
"""

from __future__ import annotations

import re
import time

from PySide import QtCore

from . import config, gorunum, log
from .context import serializer
from .execution import blocks
from .execution.executor import CodeExecutor
from .sohbet_log import SohbetGunlugu
from .transport.transport import KaliciTransport, TurSonucu


# Modelin gorsel istemek icin kullandigi isaret. Sozlesme "yanitini bu
# isaretle BITIR" diyor; kabul edilen iki yer de bu: kendi satirinda ya da
# mesajin en sonunda. Isaretin metnin ortasinda gecmesi tetiklemez, yoksa
# "gorsel-kontrol yapmama gerek yok" gibi bir cumle resim cektirirdi.
# Turkce karakterli yazma ihtimaline karsi iki yazim da kabul ediliyor.
# Sonuna "3" gelirse model UC ACI istiyor demektir (buyuk degisiklik).
#
# NEDEN SATIR SONU DA KABUL: olculdu — model "...baskiya hazir —
# GORSEL-KONTROL" yazdi, isaret kendi satirinda olmadigi icin host SESSIZCE
# hicbir sey gondermedi ve model bunu ogrenemedi. 5 istekten 1'i boyle
# kayboldu, 41 saniye sonra kullanici yazmak zorunda kaldi.
#
# "YAKIN <ad>" eki: kamerayi o nesnelere yaklastirir (bkz. gorunum.
# yakala_yakin). Gerekcesi olculdu — tum model kadraja sigdiginda kare
# ~4 piksel/mm veriyor ve ince isler gorunmuyor (MANTIK 39). Adlar FreeCAD
# IC ADI, virgulle ayrilir; desende bosluga izin YOK ki cumlenin devami
# yanlislikla ad sanilmasin.
_GORSEL_ISARET = re.compile(
    r"(?:^[ \t]*|[ \t—:-][ \t]*)G[OÖ]RSEL-KONTROL(?:[ \t]+(3))?"
    r"(?:[ \t]+YAKIN[ \t]+([A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*))?[ \t]*$",
    re.MULTILINE | re.IGNORECASE)

# Yakin cekimde en fazla kac nesne. Uctan fazlasi "yakin" olmaktan cikar:
# kamera hepsini kadraja almak icin geri cekilir ve elimizde yine genel
# kare kalir.
_YAKIN_AZAMI = 3

# Isaret metinde GECIYOR ama yukaridaki kaliba uymuyor mu? O zaman sessiz
# kalinmaz: bir sonraki otomatik isteme tek cumle iliştirilir. Ek tur
# harcamaz, mevcut isteme biner.
_GORSEL_ANAHTAR = re.compile(r"G[OÖ]RSEL-KONTROL", re.IGNORECASE)
_GORSEL_UYARI = ("Not: Yanitinda GORSEL-KONTROL gecti ama yanitin SONUNDA "
                 "degildi, o yuzden gorsel gonderilmedi. Gercekten bakmak "
                 "istiyorsan yanitini yalnizca o isaretle bitir.")

# Arka arkaya en fazla kac gorsel kontrol turu. Model resme bakip yine resim
# isteyebilir; ucuncude durup topu kullaniciya birakiyoruz.
_GORSEL_SINIR = 2

# GORSEL SISTEMI SIMDILIK KAPALI (kullanici karari, 2026-08-28).
#
# KOD SILINMEDI, ETKISIZ BIRAKILDI — gelecekte duzeltip acabiliriz.
# Acmak icin: bunu True yap ve transport.SISTEM_SOZLESMESI'ne GORSEL-KONTROL
# maddesini geri koy (ikisi birden gerekli; sozlesme anlatmazsa model
# isaretini hic yazmaz).
#
# NEDEN KAPATILDI — deney yapildi (PLAN S9, ayni istem uc kez):
#   A  fotografli   6 blok, 129 KB kare, 48.7k token -> iyi
#   B1 fotografsiz  4 blok,      0 KB,   37.2k token -> kotu
#   B2 fotografsiz  8 blok,      0 KB,   50.6k token -> EN IYI
# En iyi ve en kotu kosu AYNI koldaydi. Yani kaliteyi ayiran sey goruntu
# degil ADIM SAYISI cikti (4 -> kotu, 6 -> iyi, 8 -> en iyi) ve fotografin
# olculen bedeli bu ciftte %31 token, %44 sure idi. Goruntunun katkisi
# olcum gurultusunun altinda kaldi; kesin hukum icin ornek yetmiyor ama
# masrafi kesin, faydasi degil.
GORSEL_ACIK = False

# Modelin KENDI degisikligini geri almak icin kullandigi isaret.
# Kullanicinin sorusu: "geri almayi da AI yapamaz mi, niye kullaniciya zorla
# yaptiriyor?" Yapabilir — yalnizca neyi geri aldigi denetlenmeli.
_GERI_AL_ISARET = re.compile(r"^[ \t]*GER[İI]-AL[ \t]*$",
                             re.MULTILINE | re.IGNORECASE)

# Arka arkaya en fazla kac otomatik geri alma. Model geri alip yine geri
# almak isteyebilir; boyle bir dongu kullanicinin isini turu turu soker.
_GERI_AL_SINIR = 2

# Executor'un actigi islemlerin oneki. Geri almanin tepe kaydini AI'in mi
# yoksa kullanicinin mi biraktigini AYIRT EDEN tek sey bu.
_AI_ONEK = "AI: "

# Kod patladiginda kac kez OTOMATIK onarim turu istenir. PLAN M4'un butcesi.
# Ikiden fazlasi kullanicinin haberi olmadan uzun bir zincire donusur.
_ONARIM_SINIRI = 2


def _kisa_sayi(n: int) -> str:
    """12400 -> '12.4k'. Panelde yer dar, ham rakam okunmuyor."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class ConversationController(QtCore.QObject):
    # role: "user" | "ai" | "sistem"
    mesaj = QtCore.Signal(str, str)          # role, metin
    akis_basladi = QtCore.Signal()           # canli yanit kutusu acilsin
    akis_parcasi = QtCore.Signal(str)        # yanit metni, akarken
    dusunce_parcasi = QtCore.Signal(str)     # modelin dusunme metni (varsa)
    dusunce_olcusu = QtCore.Signal(int)      # tahmini dusunme tokeni
    akis_bitti = QtCore.Signal()
    asama = QtCore.Signal(str)               # baglaniyor | dusunuyor | yaziyor
    oneri = QtCore.Signal(object)            # blocks.KodBloku
    calisma_sonucu = QtCore.Signal(object)   # executor.CalismaSonucu
    durum = QtCore.Signal(str)               # bosta | calisiyor | oluyor
    bilgi_satiri = QtCore.Signal(str, str)   # metin, ipucu (tooltip)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.transport = KaliciTransport(self)
        self.executor = CodeExecutor()
        self.gunluk = SohbetGunlugu()

        # Oturum boyunca biriken token - "bu sohbette ne kadar harcadim"
        self._tk_toplam = 0
        self._tur_sayisi = 0
        self._akan_var = False

        # Gorsel kontrol durumu. `_gorsel_bekliyor`: model GORSEL-KONTROL
        # istedi ama ayni yanitta kod da vardi -> kod calistiktan SONRA cek.
        self._gorsel_bekliyor = False
        self._gorsel_tur = 0
        # Model bu sefer UC ACI istedi mi ("GORSEL-KONTROL 3").
        self._gorsel_cok = False
        # "GORSEL-KONTROL YAKIN Ad1,Ad2" — kamerayi yaklastirilacak nesneler.
        self._gorsel_yakin: list[str] = []
        # Isaret metinde gecti ama yanitin sonunda degildi -> bir sonraki
        # OTOMATIK isteme tek cumlelik not iliştirilecek.
        self._gorsel_uyari = False
        # Son calisan blogun EKLEDIGI nesneler. Uc kare hakkini host bunun
        # uzerinden veriyor (bkz. _kac_kare).
        self._son_eklenen: list[str] = []
        self._geri_al_tur = 0
        self._onarim_tur = 0
        self._son_hata = ""

        self.transport.tur_bitti.connect(self._tur_bitti)
        self.transport.durum_degisti.connect(self.durum.emit)
        self.transport.metin_parcasi.connect(self._metin_parcasi)
        self.transport.dusunce_parcasi.connect(self.dusunce_parcasi.emit)
        self.transport.dusunce_olcusu.connect(self.dusunce_olcusu.emit)
        self.transport.asama.connect(self.asama.emit)
        self.transport.limit_bilgisi.connect(
            lambda s: self.mesaj.emit("sistem", s))

        self.gunluk.oturum_ac(self.transport.oturum)

    # -- disari acik -------------------------------------------------------

    def mesgul_mu(self) -> bool:
        return self.transport.mesgul_mu()

    def gonder(self, metin: str, gorsel: bytes | None = None,
               kullanici_mi: bool = True) -> None:
        metin = (metin or "").strip()
        if not metin:
            return
        if self.mesgul_mu():
            self.mesaj.emit("sistem", "Onceki istek hala calisiyor. "
                                      "Bitmesini bekle ya da Iptal'e bas.")
            return

        # ASIL kullanici mesaji gorsel-kontrol sayacini sifirlar; otomatik
        # gonderilen gorsel turu sifirlamaz, yoksa sinir hic dolmazdi.
        if kullanici_mi:
            self._gorsel_tur = 0
            self._geri_al_tur = 0
            self._onarim_tur = 0
            self._son_hata = ""
            self._gorsel_uyari = False
        elif self._gorsel_uyari:
            # Dusen gorsel istegi SESSIZ kalmaz. Ek tur acmiyoruz; zaten
            # gidecek olan otomatik istemin sonuna biniyor.
            metin = metin + "\n\n" + _GORSEL_UYARI
            self._gorsel_uyari = False

        if kullanici_mi:
            self.mesaj.emit("user", metin)
        self.gunluk.oturum_ac(self.transport.oturum)
        # Insanin yazdigi mesaj ile panelin kendiliginden gonderdigi tur
        # gunlukte AYIRT EDILEBILIR olmali.
        (self.gunluk.kullanici if kullanici_mi else self.gunluk.otomatik)(metin)

        self.executor.oturumu_ayarla(self.transport.oturum)
        self._akan_var = False
        self._t0 = time.time()

        try:
            baglam = serializer.belge_metni()
        except Exception as e:
            log.uyari(f"belge baglami alinamadi: {e}")
            baglam = "<document>okunamadi</document>"

        self.transport.tur_gonder(f"{baglam}\n\n<request>\n{metin}\n</request>",
                                  gorsel=gorsel)

    def iptal(self) -> None:
        self.transport.iptal()

    def yeni_sohbet(self) -> None:
        self.transport.yeni_oturum()
        self.executor.namespace_temizle()
        self._tk_toplam = 0
        self._tur_sayisi = 0
        # Yeni oturum = YENI DOSYA. "1 session = 1 log" kurali.
        self.gunluk.oturum_ac(self.transport.oturum)
        self.mesaj.emit("sistem", "Yeni sohbet baslatildi - onceki baglam unutuldu.")
        self.bilgi_satiri.emit("", "")

    def sohbeti_surdur(self, oturum: str, dosya) -> None:
        """Kutuphaneden secilen eski bir sohbete geri doner.

        `yeni_sohbet`ten iki farki var ve ikisi de kasitli:
        - isim alanini TEMIZLEMIYORUZ; kullanici ayni FreeCAD belgesinde
          calismaya devam ediyor, degiskenlerini silmek isine yaramaz.
        - gunluk YENI dosya acmiyor, eskisine devam ediyor (bkz.
          `sohbet_log.dosyaya_devam`) — bir sohbet bir dosya.

        Sayaclar sifirlanir: token toplami ve tur sayisi BU oturumdaki
        turlari sayiyor; devralinan gecmisi bizim sayacimiz bilmiyor ve
        bilir gibi yapmasi yanlis bir rakam uretirdi.
        """
        self.transport.oturumu_surdur(oturum)
        self._tk_toplam = 0
        self._tur_sayisi = 0
        try:
            self.gunluk.dosyaya_devam(oturum, dosya)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"gunluge devam edilemedi: {e}")
        self.executor.oturumu_ayarla(oturum)
        self.bilgi_satiri.emit("", "")

    def blogu_calistir(self, blok: blocks.KodBloku) -> None:
        """Panelden 'Calistir'a basildiginda."""
        self.gunluk.kod(blok.kod, blok.baslik)
        ileri_vardi = self._ileri_sayisi()
        sonuc = self.executor.calistir(blok.kod, blok.baslik)
        self.gunluk.calisma(sonuc)
        # ARADA IS YAPILDI: gorsel sayaci "bak - yine bak" zincirini sayar,
        # "bak - degistir - yine bak"i degil (bkz. _gorseli_gonder). Kod
        # kostuysa yeni bakilacak bir sey var demektir.
        if not sonuc.engellendi:
            self._gorsel_tur = 0
            self._son_eklenen = list(getattr(sonuc, "eklenen", None) or [])
        # Geri aldiktan SONRA calisan kod ileri yiginini yakar (olculdu, bkz.
        # ileri_al). Sessizce kaybolmasin: kullanici geri aldigi seye geri
        # donebilecegini saniyor ve dugmeye bastiginda bos bir yigin buluyor.
        if ileri_vardi and self._ileri_sayisi() == 0:
            self.mesaj.emit("sistem",
                            f"İleri alma geçmişi silindi ({ileri_vardi} adım) "
                            "— üzerine yeni bir işlem yapıldı.")
            self.gunluk.sistem(f"ILERI YIGINI SILINDI ({ileri_vardi} adim)")
        self.calisma_sonucu.emit(sonuc)

        try:
            import FreeCADGui as Gui
            Gui.updateGui()
        except Exception:
            pass

        # Tekrar korumasi durdurduysa kod HIC kosmadi. Bu bir hata degil,
        # kullaniciya sorulmus bir soru; modele "kodun patladi" diye
        # gondermek onu bos yere baska bir yol aramaya iter.
        if sonuc.engellendi:
            return

        # Model bu kodun SONUCUNU gormek istemisti. Simdi cekiyoruz: kod
        # calisti, 3B guncel. updateGui() yukarida cagrildigi icin goruntu
        # yeni geometriyi icerir.
        if self._gorsel_bekliyor:
            if sonuc.basarili:
                # Cikti varsa AYNI tura bindiriliyor — ayri bir tur harcamak
                # gereksiz ve model iki mesaji sirayla degil birlikte gormeli.
                self._gorseli_gonder(sonuc.cikti)
                return
            # Kod patladi, islem geri alindi - gosterecek yeni bir sey yok.
            self._gorsel_bekliyor = False

        if not sonuc.basarili:
            self._otomatik_onar(sonuc)
        elif sonuc.cikti:
            self._ciktiyi_yolla(sonuc)

    def _ciktiyi_yolla(self, sonuc) -> None:
        """Kod BASARILI oldu ve print ile bir sey yazdi: modele geri gonder.

        NEDEN. Gunluk incelemesi (2026-08-21, madde 1) sunu olctu: print()
        iceren 8 blok kosmus, 8'inin de ciktisi modele HIC ulasmamis.
        Executor ciktiyi yakaliyordu, gunluge yaziyordu, panelde de
        gosteriyordu — yalnizca modele gondermiyordu. Karttaki "Sonucu AI'a
        gonder" dugmesi de yalnizca UYARI varken goruluyordu, yani sadece
        ciktidan ibaret bir sonucu iletmenin HICBIR yolu yoktu.

        Modelin buna verdigi tepki gunlukte duruyor ve maliyeti buydu:

          * olcum icin belgeye nesne uretmek (bir sayi ogrenmek icin Draft
            cemberi ekleyip bir SONRAKI turda yaricapini okumak),
          * sonucu kasitli bir istisnaya gomup geri almak — kendi cumlesi:
            "sonucu kasitli bir hataya gomup size otomatik olarak geri
            gelmesini saglayacagim". Calisiyordu, cunku HATA yolu otomatik
            besleniyor, BASARI yolu beslenmiyordu. Model host'un acik
            biraktigi tek deligi bulmustu.

        Simdi basari yolu da besleniyor; o iki kalibin ikisi de gereksiz.
        Dongu riski yok: her tur kullanicinin Calistir'a basmasiyla
        basliyor, kendiliginden zincirlenmiyor.
        """
        if self.mesgul_mu():
            return
        self.gunluk.sistem("CIKTI otomatik gonderildi "
                           f"({len(sonuc.cikti)} karakter)")
        self.sonucu_gonder(sonuc, kullanici_mi=False)

    # -- otomatik onarim ---------------------------------------------------

    @staticmethod
    def _hata_imzasi(sonuc) -> str:
        """Tracebackin son satiri — hatanin kimligi.

        Satir numaralari ve yollar degisebilir; degisen sey hatanin TURU ve
        mesaji degilse model ayni duvara toslamaya devam ediyor demektir.
        """
        satirlar = (sonuc.hata_izi or "").strip().splitlines()
        return satirlar[-1].strip() if satirlar else ""

    def _otomatik_onar(self, sonuc) -> None:
        """Kod patlayinca hatayi KENDILIGINDEN modele gonderir.

        NEDEN. Eskiden bunun icin kullanicinin "Hatayi AI'a gonder" dugmesine
        BASMASI gerekiyordu; basmazsa model kodunun patladigini hic bilmezdi.
        Bu, geri alma sorununun (MANTIK 19) birebir ayni kalibi: host'un
        kendiliginden yapabilecegi bir is insana yaptiriliyordu. Gunlukte
        kullanici o dugmeye uc kez basmis — akis her seferinde ayni, tek fark
        bir tiklama ve kullanicinin o an baska yere bakiyor olma ihtimali.

        IKI SINIR. PLAN M4 "2 deneme butcesi" diyordu:

        1. En fazla _ONARIM_SINIRI otomatik tur. Sonrasinda durulur ve top
           kullaniciya birakilir — dugme yerinde duruyor, elle gonderilebilir.
        2. AYNI hata iki kez gelirse HEMEN durulur. Butceyi doldurmanin
           anlami yok: model ayni duvara tosluyor ve ucuncu deneme de ayni
           yere carpar. Bu, butce sinirindan daha erken devreye giren
           gercek sinir.
        """
        imza = self._hata_imzasi(sonuc)

        if imza and imza == self._son_hata:
            self._son_hata = ""
            self.mesaj.emit("sistem",
                            "Aynı hata tekrarladı; otomatik onarım "
                            "durduruldu. Farklı bir yol tarif etmen "
                            "gerekiyor.")
            self.gunluk.sistem("OTOMATIK ONARIM durduruldu: ayni hata tekrar")
            return

        if self._onarim_tur >= _ONARIM_SINIRI:
            self.mesaj.emit("sistem",
                            f"{_ONARIM_SINIRI} otomatik onarım denemesi "
                            "yetmedi; durduruldu. İstersen “Hatayı AI'a "
                            "gönder” ile devam edebilirsin.")
            self.gunluk.sistem("OTOMATIK ONARIM butcesi doldu")
            return

        if self.mesgul_mu():
            return                     # elle gonderme yolu acik kalsin

        self._onarim_tur += 1
        self._son_hata = imza
        self.mesaj.emit("sistem",
                        f"Hata otomatik olarak AI'a gönderildi "
                        f"({self._onarim_tur}/{_ONARIM_SINIRI}).")
        self._hatayi_yolla(sonuc, kullanici_mi=False)

    # -- geri alma ---------------------------------------------------------

    def geri_al(self, ai_mi: bool = False) -> tuple[bool, str]:
        """Son AI degisikligini geri alir. Doner: (oldu_mu, aciklama).

        Hem paneldeki dugme hem modelin GERI-AL isareti BURAYA girer, cunku
        tehlikeli olan sey ikisinde de ayni: yiginin tepesinde KIMIN isi var.

        Eski dugme `doc.undo()`'yu kosulsuz cagiriyordu ve etiketi "Son AI
        degisikligini geri al" idi. Kullanici AI'in kodundan sonra elle bir
        seyler yaptiysa dugme ONUN isini geri aliyordu — etiket yalan
        soyluyordu. Artik tepe kaydin oneki denetleniyor.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "Açık belge yok."
        adlar = list(getattr(doc, "UndoNames", ()) or ())
        if not adlar:
            return False, "Geri alınacak bir şey yok."

        tepe = adlar[0]
        if not tepe.startswith(_AI_ONEK):
            return False, (
                f"Geri alma yığınının tepesinde AI değişikliği yok — orada "
                f"“{tepe}” var, yani senin kendi düzenlemen. Onu silmemek "
                f"için durdum. Kendin geri almak istersen Ctrl+Z.")

        doc.undo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"geri alma sonrasi recompute: {e}")
        # Bayat baglama = SERT COKME riski (bkz. executor.namespace_temizle).
        self.executor.namespace_temizle()
        kim = "AI" if ai_mi else "Kullanıcı"
        self.gunluk.sistem(f"GERI-AL ({kim}): {tepe}")
        return True, tepe

    @staticmethod
    def _ileri_sayisi() -> int:
        """Ileri yiginindaki adim sayisi. Belge yoksa 0."""
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return 0
        return len(list(getattr(doc, "RedoNames", ()) or ()))

    def ileri_al(self) -> tuple[bool, str]:
        """Geri alinan son degisikligi TEKRAR UYGULAR. Doner: (oldu_mu, aciklama).

        OLCULDU (LOG/2026-08-24_3ad4cef1.txt, 12:09:33 -> 12:09:58): kullanici
        tam da "evet guzel oldu istedigim gibi" dedigi sonucu yanlislikla geri
        aldi — alti saniye icinde uc kez. Sonra eski kod blogunu yeniden
        calistirmayi denedi, iki kez ayni hatayi aldi ("bunny veya
        Karin_dolgusu yok" — cunku dolguyu geri alma silmisti) ve oturum orada
        bitti. O anda FreeCAD'in ileri yiginda UC kayit hala duruyordu; 25
        dakikalik is bir dugme eksikligi yuzunden geri gelmedi.

        GERI-AL'IN AKSINE kullanicinin kendi kaydi da ileri alinabiliyor.
        Asimetri kasitli: geri alma is SILER (yigininin tepesinde kullanicinin
        emegi varsa onu yok eder — bu yuzden orada denetim var), ileri alma is
        GERI GETIRIR. Reddetmenin koruyacagi bir sey yok, o yuzden yalnizca
        neyin geri geldigi soyleniyor.

        OLCULDU — ileri yigini TAM OLARAK ne zaman siliniyor (FreeCAD 1.1.1):

            bos transaction (commit ya da abort)   -> KORUNUR
            salt-okunur kod (sadece print)         -> KORUNUR
            SyntaxError (transaction hic acilmadi) -> KORUNUR
            DEGISIKLIK yapip iptal edilen islem    -> SILINIR
            yeni ve basarili islem                 -> SILINIR (normal davranis)

        Yani gunlukteki iki basarisiz calistirma yigina DOKUNMAMISTI; dugme o
        gun var olsaydi is geri gelirdi. Yine de "degisiklik yapip patlayan"
        kod yigini yakiyor — blogu_calistir bunu fark edince soyluyor.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "Açık belge yok."
        adlar = list(getattr(doc, "RedoNames", ()) or ())
        if not adlar:
            return False, ("İleri alınacak bir şey yok. Geri aldıktan sonra "
                           "yeni bir işlem yaptıysan ileri geçmişi silinmiştir.")

        tepe = adlar[0]
        doc.redo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"ileri alma sonrasi recompute: {e}")
        # Bayat baglama = SERT COKME riski — geri almadaki gerekcenin aynisi.
        self.executor.namespace_temizle()
        self.gunluk.sistem(f"ILERI-AL: {tepe}")
        return True, tepe

    def _ai_geri_al(self) -> None:
        """Modelin GERI-AL istegini yerine getirir.

        OLCULDU (LOG/2026-08-20_baa70fa4.txt) — bu ozelligin yoklugu uc ayri
        kayba yol acti:

          15:32:51  AI: "Ilk adim kod degil: Ctrl+Z ile ... geri don."
          15:46:12  KULLANICI: "geri aldim"
                    -> 13 dakika 21 saniye, oturum tamamen durdu.

          16:04:52  AI yine ayni seyi soyledi.
          16:05:20  AI: "GERI ALINDIGININ VARSAYIP devam ediyorum"
                    -> ve o varsayimin uzerine kod uretti. Kullanici "tamam"
                       demisti; bu "geri aldim" mi "devam et" mi belli degil.
                       Model dogrulayamadigi bir duruma kod yazdi.

        Ucuncusu asil olan: bu bir hiz sorunu degil, DOGRULUK sorunu.
        """
        if self._geri_al_tur >= _GERI_AL_SINIR:
            self.mesaj.emit("sistem",
                            f"AI arka arkaya {_GERI_AL_SINIR} kez geri alma "
                            "istedi; durduruldu. Nereye dönmek gerektiğini "
                            "sen söyleyebilirsin.")
            return

        oldu, aciklama = self.geri_al(ai_mi=True)
        if oldu:
            self._geri_al_tur += 1
            self.mesaj.emit("sistem", f"AI geri aldı: {aciklama}")
            return

        # BASARISIZ. Model kendi istegini yerine getirilmis SANIYOR ve bir
        # sonraki adimi o varsayimla kuracak — olculen 3. kaybin ta kendisi.
        # Bu yuzden sessiz kalmiyoruz: tek otomatik tur harcanip modele
        # neyin olmadigi soyleniyor. Basarili halde tur HARCANMIYOR, cunku
        # orada modelin varsayimi zaten dogru.
        self.mesaj.emit("sistem", "AI geri almak istedi ama yapılmadı: "
                                  + aciklama)
        self.gunluk.sistem("GERI-AL reddedildi: " + aciklama)
        self.gonder(
            "Geri alma isteğin YERINE GETIRILMEDI. Sebep: " + aciklama +
            "\nBelge hala eski halinde. Geri alındığını VARSAYMA. "
            "Ya kullanıcıdan ne yapmasını istediğini tek cümleyle söyle, "
            "ya da mevcut durumdan devam eden bir adım ver.",
            kullanici_mi=False)

    def sonucu_gonder(self, sonuc, kullanici_mi: bool = True) -> None:
        """Calistirma sonucunu (cikti ve konsol uyarilari dahil) modele yollar.

        Kullanicinin istegi: "uyari ve haber kodlarini da AI gorsun, yani
        turuncu kisimlari." FreeCAD'in konsol uyarilari cogu zaman istisna
        firlatmiyor; kod basarili gorunuyor ama bir sey ters gitmis oluyor.

        Cikti varsa buraya _ciktiyi_yolla kendiliginden giriyor; dugme
        yalnizca kullanici ekstra bir sey gondermek istediginde gerekiyor.
        """
        self.gonder(
            "Az once verdigin kod calistirildi. Kodun print() ciktisi ve "
            "FreeCAD'in kendi konsolundan gelen uyarilar dahil sonuc asagida. "
            "Sorun varsa neyin yanlis gittigini soyle ve duzeltmenin YALNIZCA "
            "ilk adimini ver; sorun yoksa tek cumleyle onayla — bir sayi "
            "sorulduysa dogrudan sayiyi yaz.\n\n"
            f"<execution_result>\n{sonuc.modele_metin()}\n</execution_result>",
            kullanici_mi=kullanici_mi)

    def hatayi_gonder(self, sonuc) -> None:
        """Panelden "Hatayi AI'a gonder" dugmesi.

        Otomatik onarim (bkz. _otomatik_onar) devreye girdikten sonra bu
        dugme hala duruyor: butce dolunca ya da ayni hata tekrarlayinca
        kullanici yine de gondermek isteyebilir.
        """
        self._hatayi_yolla(sonuc, kullanici_mi=True)

    def _hatayi_yolla(self, sonuc, kullanici_mi: bool) -> None:
        self.gonder(
            "Az once verdigin kod canli belgede calistirilinca hata verdi. "
            "Islem geri alindi, belge degismedi. "
            "Duzeltilmis TAM bir blok ver; ozur dileme, aciklamayi uzatma. "
            "Ayni yaklasimla ikinci kez denemek yerine, hata bunu "
            "gerektiriyorsa BASKA bir yol sec.\n\n"
            f"<execution_error>\n{sonuc.hata_izi.strip()}\n</execution_error>",
            kullanici_mi=kullanici_mi)

    # -- ic ---------------------------------------------------------------

    def _metin_parcasi(self, parca: str) -> None:
        # Ilk parca gelene kadar canli kutuyu acmiyoruz; kodsuz/bos yanitlarda
        # bos bir balon birakmasin.
        if not self._akan_var:
            self._akan_var = True
            self.akis_basladi.emit()
        self.akis_parcasi.emit(parca)

    def _tur_bitti(self, sonuc: TurSonucu) -> None:
        if self._akan_var:
            self.akis_bitti.emit()
            self._akan_var = False

        if sonuc.hata_mi:
            self.mesaj.emit("sistem", sonuc.aciklama or "Bilinmeyen hata.")
            self.gunluk.sistem("HATA: " + (sonuc.aciklama or "bilinmeyen"))
            self.bilgi_satiri.emit("hata", sonuc.aciklama or "")
            return

        self._tur_sayisi += 1
        self._tk_toplam += sonuc.tk_toplam

        duz, bulunan = blocks.ayikla(sonuc.metin)

        # GORSEL-KONTROL isteniyor mu? Isareti kullaniciya gostermiyoruz -
        # o bir protokol sozcugu, mesajin parcasi degil.
        gorsel_esleme = _GORSEL_ISARET.search(duz or "")
        gorsel_istendi = gorsel_esleme is not None
        if gorsel_istendi:
            # "GORSEL-KONTROL 3" = model kendisi uc aci istedi (buyuk
            # degisiklik yapti ve tek kareye guvenmiyor).
            self._gorsel_cok = bool(gorsel_esleme.group(1))
            # "YAKIN Ad1,Ad2" = kamerayi o nesnelere yaklastir.
            adlar = (gorsel_esleme.group(2) or "").strip()
            self._gorsel_yakin = [a for a in adlar.split(",")
                                  if a][:_YAKIN_AZAMI]
            duz = _GORSEL_ISARET.sub("", duz).strip()
        elif _GORSEL_ANAHTAR.search(duz or ""):
            # Isaret var ama yerinde degil. Kanali SESSIZ birakmiyoruz:
            # gunluge yaziliyor ve bir sonraki otomatik isteme not olarak
            # biniyor (bkz. gonder).
            self._gorsel_uyari = True
            self.gunluk.sistem("GORSEL-KONTROL isareti yanitin sonunda "
                               "degildi — gorsel gonderilmedi, modele "
                               "bildirilecek")

        geri_al_istendi = _GERI_AL_ISARET.search(duz or "") is not None
        if geri_al_istendi:
            duz = _GERI_AL_ISARET.sub("", duz).strip()

        if duz:
            self.mesaj.emit("ai", duz)
        elif not bulunan:
            self.mesaj.emit("ai", "(bos yanit)")

        # Geri alma, kod kartlarindan ONCE. Ayni yanitta hem "bunu geri al"
        # hem duzeltilmis kod olabiliyor; kullanici Calistir'a bastiginda
        # belge dogru noktada olmali.
        if geri_al_istendi:
            self._ai_geri_al()

        for b in bulunan:
            self.oneri.emit(b)

        self.gunluk.oturum_ac(sonuc.oturum or self.transport.oturum, sonuc.model)
        # Gunluge HARCAMA ve BAGLAM ayri yaziliyor; ikisini tek sayiya
        # katlamak baglami 2 kat gosteren sicramayi uretmisti. `api=` de
        # burada: sicrama yine olursa sebebi gunlukte gorunsun.
        olcu = f"{sonuc.tk_toplam} token · baglam {sonuc.tk_baglam}"
        if sonuc.api_cagrisi > 1:
            olcu += f" · api={sonuc.api_cagrisi}"
        self.gunluk.ai(sonuc.metin, sonuc.model, sonuc.sure_ms / 1000.0, olcu)

        self.bilgi_satiri.emit(*self._bilgi(sonuc, len(bulunan)))

        if gorsel_istendi:
            if bulunan:
                # Kod var: simdi cekmek eski hali gosterirdi. Calistiktan
                # sonra cekilecek (bkz. blogu_calistir).
                self._gorsel_bekliyor = True
            else:
                self._gorseli_gonder()

    # -- gorsel kontrol ----------------------------------------------------

    def _cakisma_metni(self, adlar: list[str]) -> str:
        """YAKIN cekimdeki nesnelerin cakisma olcumu — metin olarak.

        Neden host yapiyor da modelden istemiyoruz: olculdu (MANTIK 39),
        model goruntuye bakip "cakisma yok" dedi ve yanildi. Yakindan
        bakmak istedigi an dogru cevabi ELINE VERIYORUZ; bir tur daha
        harcamiyor ve unutma ihtimali kalmiyor.

        ODAK MODU (2026-08-27). Eskiden burada nesneler bir listeye konup
        `cakisma_kontrol(*hepsi)` cagriliyordu ve bu, docstring'in aksine
        TUM BELGEYI tariyordu. Olculdu (LOG/2026-08-27_9564dc71.txt): 44
        nesne, 946 cift, 2 sn butce doldu, **431 cift hic olculmedi** ve
        donen 38 satirin cogu gizli kesme tabanlariydi — yani sorulan
        cevap gelmiyordu, gurultu geliyordu.

        Artik `odak=` kullaniliyor: yalnizca yakin cekimdeki nesneyi
        ilgilendiren ciftler. Ayni belgede 16 cift, 0.38 sn, 2 satir.
        """
        try:
            import FreeCAD as App

            from .execution import olcum

            doc = App.ActiveDocument
            if doc is None:
                return ""
            nesneler = [doc.getObject(a) for a in adlar]
            nesneler = [o for o in nesneler if o is not None]
            if not nesneler:
                return ""
            if len(nesneler) == 1:
                # Tek nesne: o nesneyi ILGILENDIREN ciftler. Adaylari
                # cakisma_kontrol kendisi buluyor ve tuketilmis olanlari
                # eliyor (bkz. kesif.tuketilmis_mi).
                sonuc = olcum.cakisma_kontrol(odak=nesneler[0], yaz=False)
                return sonuc.get("satir", "")
            # Birden fazla nesne ACIKCA istendi: tam olarak onlar olculur,
            # eleme yok — model neyi sorduysa onu alir.
            sonuc = olcum.cakisma_kontrol(*nesneler, yaz=False)
            return sonuc.get("satir", "")
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"yakin cekim cakisma olcumu yapilamadi: {e}")
            return ""

    def _gorsel_yerine_cikti(self, cikti: str, sebep: str) -> None:
        """Gorsel gonderilemedi. CIKTI ONA BINMISTI — onu da yutma.

        OLCULDU (LOG/2026-08-24_3ad4cef1.txt, 12:03:26): basarili bir
        calistirmadan sonra gunluge HICBIR sey dusmedi — ne cikti ne gorsel.
        Sebep gorsel butcesiydi, ama fatura ciktiya kesildi: cikti bu cagriya
        BINDIRILIYOR (bkz. blogu_calistir), gorsel yolu erken donunce
        `dolgu alani: 3080 mm2 | cakisma: 0.00 mm2` da beraberinde gitti.
        Model, basarili bir calistirma hakkinda sifir geri bildirim aldi.

        Ayrica bastirma artik GUNLUGE de yaziliyor. Eskiden yalnizca panele
        `mesaj.emit` ediliyordu; oteki butun bastirma yollari (ornegin
        "OTOMATIK ONARIM butcesi doldu") gunluge yaziyor. Bu yuzden logu
        sonradan inceleyen biri o bosluga bir sebep bulamiyordu.
        """
        self.gunluk.sistem("GORSEL GONDERILMEDI: " + sebep)
        if not cikti:
            return
        self.gunluk.sistem(f"CIKTI yine de gonderildi ({len(cikti)} karakter)")
        self.gonder(
            "Az once verdigin kod calistirildi; ciktisi asagida. Istedigin 3B "
            "goruntu GONDERILEMEDI (" + sebep + "), yani goruntuye bakmis "
            "gibi konusma. Elindeki sayilarla ilerleyebiliyorsan ilerle; "
            "gercekten bakman gerekiyorsa kullanicidan ne gormen gerektigini "
            "tarif etmesini iste.\n\n"
            f"<execution_result>\n{cikti}\n</execution_result>",
            kullanici_mi=False)

    def _kac_kare(self) -> tuple[bool, str]:
        """Uc kare mi tek kare mi — KARARI HOST VERIYOR, model degil.

        NEDEN DEGISTI (olculdu, LOG/2026-08-27_9564dc71.txt). Eski kural
        "model 'GORSEL-KONTROL 3' derse uc kare"ydi, yani karar modeldeydi.
        Sonuc: 30 gorsel gonderiminin **27'si uc kare** (%90), ve sozlesmeye
        "uc kare varsayilan degil" yazildiktan SONRA bile oran %90 kaldi.
        Bir sistem istemi satiri, modelin kendi baglamindaki 40 ornegi
        yenmiyor. Kural tutmuyorsa, kurali uygulayacak yere tasinir.

        Bedeli olculdu: 30 gonderim 916 KB, tur basina ortalama 30 KB ve
        modelin karmasiklastikca buyuyor (ilk yarida 22 KB, ikinci yarida
        47 KB) — baglam penceresinin kabaca ucte biri.

        Kazanci olculmedi, cunku YOK: gorsel donusu olan 30 turun 7'sinde
        model bir sorun buldu ve **yedisinde de** delil yazdirilan bir
        sayiydi (bbox, hacim, cakisma_kontrol) — "0.2 mm tasma" gibi
        kalemler zaten 4 piksel/mm'de gorunmez. Goruntunun tek basina
        yakaladigi tek bulgu yok.

        Uc kare hakki iki durumda veriliyor:
          * son blok YENI NESNE ekledi — uzayda yeri hic kanitlanmamis bir
            sey var, tek aci "havada mi duruyor"u kapatmaz; ya da
          * bu arka arkaya ikinci bakis — ilk kare soruyu kapatmamis.
        Ikisi de yoksa tek kare gider ve modele NEDEN tek kare oldugu
        soylenir; yoksa ayni istegi tekrarlar.
        """
        istedi = self._gorsel_cok
        yeni_nesne = bool(self._son_eklenen)
        ikinci_bakis = self._gorsel_tur >= 1
        if yeni_nesne or ikinci_bakis:
            return True, ""
        if istedi:
            return False, (
                "\n\nNOT: uc kare istedin, tek kare gonderildi — bu turda "
                "yeni nesne eklenmedi (var olani degistirdin) ve bu ilk "
                "bakis. Uc kare baglam penceresinin buyuk bir parcasini "
                "yiyor ve olculdu ki bulgulari zaten SAYI veriyor. Tek "
                "kare yetmiyorsa bir sonraki blokta olc: bbox, hacim, "
                "cakisma_kontrol(odak=...). Gercekten aci lazimsa yanitini "
                "yine GORSEL-KONTROL 3 ile bitir, ikinci bakista verilir.")
        return False, ""

    def _gorseli_gonder(self, cikti: str = "") -> None:
        """3B gorunumu yakalayip modele yollar. Basarisizlikta sessiz kalmaz.

        `cikti` verilirse ayni mesaja bindirilir: kod hem bir sey yazdirmis
        hem gorsel istenmisse iki tur harcamanin anlami yok.
        """
        self._gorsel_bekliyor = False

        # GORSEL KAPALI (bkz. GORSEL_ACIK). En basta duruyor ki asagidaki
        # sayaclarin hicbirini kirletmesin; acildiginda eski davranis
        # oldugu gibi geri gelsin.
        #
        # Model yine de isteyebilir (sozlesmede madde kalmasa bile eski
        # aliskanlikla yazabilir). O yuzden SESSIZ KALMIYORUZ: cikti
        # gonderiliyor ve "goruntuye bakmis gibi konusma" deniyor.
        if not GORSEL_ACIK:
            self._gorsel_cok = False
            self._son_eklenen = []
            self._gorsel_yakin = []
            self._gorsel_yerine_cikti(
                cikti, "gorsel sistemi kapali — olcerek ilerle")
            return

        # DONGU EMNIYETI: model resme bakip yine resim isteyebilir. Iki tur
        # yeter; ucuncude durup topu kullaniciya birakiyoruz.
        #
        # SAYAC NEYI SAYAR. Yalnizca ARKA ARKAYA, arada is yapilmadan gelen
        # bakislari. Kod calistiginda sifirlaniyor (bkz. blogu_calistir),
        # cunku korumanin hedefi "bakip yine bakmak"ti, "bak - degistir -
        # yine bak" degil. Olculdu (LOG/2026-08-24_3ad4cef1.txt): Opus
        # 11:46 / 11:53 / 11:58'de bakti, her bakis arasinda GERI-AL verip
        # yeni kod yazdi — yani tam da istedigimiz dongu — ve dorduncude
        # butce doldugu icin cezalandirildi.
        if self._gorsel_tur >= _GORSEL_SINIR:
            self.mesaj.emit("sistem",
                            f"AI arka arkaya {_GORSEL_SINIR} kez görsel "
                            "kontrol istedi; durduruldu. Ne görmesi "
                            "gerektiğini sen tarif edebilirsin.")
            self._gorsel_yerine_cikti(
                cikti, f"arka arkaya {_GORSEL_SINIR} kez istendi, durduruldu")
            return

        if not gorunum.yakalanabilir_mi():
            self.mesaj.emit("sistem",
                            "AI 3B görünümü görmek istedi ama aktif bir 3B "
                            "pencere yok. Bir belge açıp tekrar dene.")
            self._gorsel_yerine_cikti(cikti, "acik 3B pencere yok")
            return

        cok_aci, kare_notu = self._kac_kare()
        self._gorsel_cok = False
        # Hak BIR KEZ kullanilir. Temizlemezsek bir onceki turda eklenmis
        # nesne, sonraki bakislara da uc kare hakki vermeye devam ederdi.
        self._son_eklenen = []
        yakin = list(self._gorsel_yakin)
        self._gorsel_yakin = []

        if yakin:
            # YAKIN CEKIM. Genel kare ince isi gostermiyor: 201 mm'lik bir
            # modelde 900x640 kare ~4 piksel/mm, yani 0.6 mm'lik parca 2
            # piksel (olculdu, MANTIK 39). Kamera nesneye yaklasiyor.
            kareler = gorunum.yakala_yakin(yakin, cok_aci=cok_aci)
            if not kareler:
                # Yaklasamadiysak SESSIZ kalmiyoruz: normal kareye dusuyoruz
                # ve modele bunu soyluyoruz (asagida istem metninde).
                tek = gorunum.yakala()
                kareler = [tek] if tek else []
                yakin_dustu = True
            else:
                yakin_dustu = False
        elif cok_aci:
            kareler = gorunum.yakala_cok()
            yakin_dustu = False
        else:
            tek = gorunum.yakala()
            kareler = [tek] if tek else []
            yakin_dustu = False

        if not kareler:
            self.mesaj.emit("sistem",
                            "AI 3B görünümü istedi ama görüntü alınamadı "
                            "(ayrıntı Report view'da).")
            self._gorsel_yerine_cikti(cikti, "goruntu alinamadi")
            return

        veri = kareler if len(kareler) > 1 else kareler[0]
        bayt = sum(len(k) for k in kareler)
        etiket = (f"{len(kareler)} açıdan görünüm" if len(kareler) > 1
                  else "3B görünüm")

        self._gorsel_tur += 1
        yakin_eki = f", YAKIN: {', '.join(yakin)}" if yakin else ""
        self.mesaj.emit("sistem",
                        f"{etiket} AI'a gönderildi ({bayt // 1024} KB"
                        f"{yakin_eki}).")
        self.gunluk.sistem(f"GORSEL-KONTROL: {len(kareler)} kare gonderildi "
                           f"({bayt} bayt){yakin_eki}")
        if len(kareler) > 1:
            istem = (f"Istedigin 3B goruntuleri ekte, {len(kareler)} acidan: "
                     f"1) kullanicinin ekranda gordugu aci, 2) ON gorunus "
                     f"(-Y'den), 3) UST gorunus (+Z'den). Ucune de bak — tek "
                     f"acidan gorunmeyen sey (bir seyin havada durup "
                     f"durmadigi, hizanin bozuk olup olmadigi) diger "
                     f"acilarda gorunur. Baktiktan sonra: dogru gorunuyorsa "
                     f"tek cumleyle onayla; bir sorun varsa neyin yanlis "
                     f"oldugunu soyle ve duzeltmenin YALNIZCA ilk adimini ver.")
        else:
            istem = ("Istedigin 3B goruntusu ekte. Baktiktan sonra: dogru "
                     "gorunuyorsa tek cumleyle onayla; bir sorun varsa neyin "
                     "yanlis oldugunu soyle ve duzeltmenin YALNIZCA ilk "
                     "adimini ver. Tek acidan emin olamadiysan tahmin etme: "
                     "yanitini GORSEL-KONTROL 3 ile bitir, uc acidan bakarsin.")
        # Host uc kareyi tek kareye indirdiyse SEBEBINI soyluyoruz. Sessizce
        # indirmek modeli ayni istegi tekrarlamaya iter.
        istem += kare_notu

        # YAKIN CEKIMDE OLCUM DE GIDIYOR. Kullanicinin karari: "yakindan
        # baksin ve ayrintili incelesin" + goruntuyle birlikte sayi. Cakisma
        # sorusu zaten goruntuyle kapanmiyor (MANTIK 39), o yuzden ayni
        # mesajda deterministik cevabi da veriyoruz — ek tur harcamadan.
        if yakin:
            istem = (f"YAKIN CEKIM: kamera su nesnelere yaklastirildi — "
                     f"{', '.join(yakin)}. " + istem)
            if yakin_dustu:
                istem += ("\n\nNOT: kamera yaklastirilamadi, bu kare GENEL "
                          "gorunumden alindi (ayrinti Report view'da).")
            olcum_metni = self._cakisma_metni(yakin)
            if olcum_metni:
                istem += ("\n\nAyni nesnelerin DETERMINISTIK cakisma olcumu "
                          "(goruntu bu soruyu kapatmaz, bu kapatir):\n"
                          f"<execution_result>\n{olcum_metni}\n"
                          "</execution_result>")
        if cikti:
            istem += (f"\n\nAyni kodun print() ciktisi:\n"
                      f"<execution_result>\n{cikti[:2000]}\n"
                      f"</execution_result>")
        self.gonder(istem, gorsel=veri, kullanici_mi=False)

    def _bilgi(self, s: TurSonucu, blok_sayisi: int) -> tuple[str, str]:
        """Alt bilgi cubugu metni + ipucu.

        Dolar YERINE token gosteriliyor: abonelikte dolar tahsil edilmiyor,
        o rakam yalnizca "API fiyatiyla yapilsaydi" karsiligiydi ve
        "para harciyorum" diye yanlis anlasildi. Token ise gercekten
        kullanilan kaynak.
        """
        satir = [f"{s.sure_ms / 1000:.1f} sn"]
        if s.model:
            satir.append(s.model)
        satir.append(f"{_kisa_sayi(s.tk_toplam)} token")
        # BAGLAM DOLULUGU. Limiti CLI bildirmiyor (init ve result alanlarinin
        # tamami tarandi), o yuzden modelin katalog degeri sabit yaziliyor -
        # bkz. config.BAGLAM_SINIRI. Kullanilan taraf ise gercek olcum.
        satir.append(f"{_kisa_sayi(s.tk_baglam)}/{config.baglam_siniri_kisa()} bağlam")
        # "0 kod blogu" yazmiyoruz: bilgi tasimayan gurultu, kullanici hakli
        # olarak "o ne, gereksizse sil" dedi. Sifirdan buyukse anlamli.
        if blok_sayisi:
            satir.append(f"{blok_sayisi} kod bloğu")

        ipucu = [
            "Claude Code aboneligi uzerinden calisiyor "
            "(API anahtari yok, ek ucret yok).",
            "",
            f"Baglam: {s.tk_baglam:,} / {config.BAGLAM_SINIRI:,} token",
            "  (girdi + onbellek; cikti baglama girmez)",
            "  Sinir modelin katalog degeri - CLI limiti bildirmiyor.",
            "",
            "Bu tur:",
            f"  girdi            {s.tk_girdi:>9,}",
            f"  onbellekten okuma{s.tk_onbellek_okuma:>9,}   (ucuz)",
            f"  onbellege yazma  {s.tk_onbellek_yazma:>9,}",
            f"  cikti            {s.tk_cikti:>9,}",
            f"  TOPLAM           {s.tk_toplam:>9,}",
            "",
            f"Bu sohbette toplam: {self._tk_toplam:,} token / {self._tur_sayisi} tur",
        ]
        if s.maliyet_usd:
            ipucu += ["",
                      f"API fiyatiyla yapilsaydi ~${s.maliyet_usd:.3f} tutardi -",
                      "abonelikte faturalanmaz."]
        if self.gunluk.dosya:
            ipucu += ["", f"Sohbet kaydi: {self.gunluk.dosya}"]

        log.ayik(" · ".join(satir))
        return " · ".join(satir), "\n".join(ipucu)
