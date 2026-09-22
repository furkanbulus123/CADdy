"""Uretilen FreeCAD Python'unu CANLI belge uzerinde calistirir.

Tasarimin kalbi burasi. Uc sey pazarlik disi:

1. **Tek temiz geri alma.** Kod ne kadar nesne uretirse uretsin, Ctrl+Z hepsini
   bir adimda geri almali. Bunu `App.setActiveTransaction(ad, persist=True)` +
   `closeActiveTransaction()` sagliyor. `persist=True` sart: FreeCAD 1.1'de
   bir Gui::Command yiginin DISINDA acilan islem, komut yigini bosalinca
   otomatik kapaniyor — bizim kod bir sinyal geri cagriminda calistigi icin
   tam da o duruma dusuyoruz.

2. **Hata = tam geri sarma.** Istisna cikarsa islem ABORT edilir; belge kodun
   yarisini uygulanmis halde kalmaz.

3. **Traceback kaynak satirini gostermeli.** `compile()` sonrasi linecache'e
   kaynagi elle koymazsak traceback "File "<caddy:...>", line 12" der ve
   SATIRI GOSTERMEZ; model neyi duzeltecegini tahmin etmek zorunda kalir.
   Tek satirlik kayit, otomatik onarim basarisini dogrudan yukseltiyor.

Dikkat: iptal yalnizca BELGEYI geri alir. Kod dosya yazdiysa ya da global bir
sey degistirdiyse o kalir — arayuz bunu kullaniciya soyluyor.
"""

from __future__ import annotations

import io
import linecache
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field

import FreeCAD as App

from .. import log
from . import dogrulama, islem, kesif, olcum

# Ayni kodun ikinci kez kosmasinin SORULACAGI pencere (saniye). Olculen
# kazalar 2 saniye arayliydi; bilincli bir tekrar ise genelde dakikalar
# sonra gelir. Bkz. CodeExecutor._tekrar_engeli.
TEKRAR_PENCERESI = 60.0

# Bu suredan uzun suren calistirmalarin ASAMA DOKUMU gunluge yazilir.
#
# NEDEN VAR. Olculdu (LOG/2026-08-25_dc91d6d7.txt, 10:05:15): tek bir
# Part::Box ureten ilk blok 17.1 sn surdu, ayni oturumdaki sonraki bloklar
# 0.1-0.3 sn. Gunlukte yalnizca TOPLAM sure vardi, o yuzden 17 saniyenin
# nereye gittigi sonradan cikarilamadi. Ayni yol baska bir makinede
# (FreeCAD 1.1.3, GUI, ayni kod) asama asama olculdu ve TAMAMI 0.02 sn
# cikti — yani suclu bu kod yolunda sabit duran bir sey degil, o ana ozgu
# bir sey (soguk disk, virus taramasi, GUI'de ilk `import Draft`).
#
# Tahmin etmek yerine bir dahaki sefere KENDISI soylesin diye asamalar
# olculuyor. Esik var cunku normal tur 0.1 sn: her satirda dokum yazmak
# gunlugu gurultuye bogar, bulunmasi gereken sey de icinde kaybolur.
YAVAS_ESIGI = 2.0


def isit() -> float:
    """`_hazirla`nin pahali importlarini ONCEDEN yapar. Doner: gecen saniye.

    Panel acilirken cagrilir (bkz. ui/dock). Kritik yolun disinda: kullanici
    o sirada modelin yanitini okuyor, burada gecen sure ona sure olarak
    gorunmuyor.

    Olculdu (bu makine, gercek GUI): `Draft` 0.19 sn, digerleri 0.00 sn.
    Yani buradaki kazanc kucuk — ama `calistir` icindeki o bolgede baska
    aday YOK ve maliyeti sifira yakin. Isitma 17.1 saniyeyi aciklamiyorsa
    asama dokumu (bkz. YAVAS_ESIGI) sucluyu isimle soyleyecek.

    ASLA patlamaz: eksik bir modul isi engellememeli, zaten `_hazirla` da
    her birini tek tek yakaliyor.
    """
    t0 = time.time()
    for ad in ("Part", "Sketcher", "Draft", "Mesh", "PartDesign"):
        try:
            __import__(ad)
        except Exception:                                        # noqa: BLE001
            pass
    gecen = time.time() - t0
    log.ayik(f"isitma: {gecen:.2f} sn")
    return gecen

# Bilgi TASIMAYAN son satirlar. OCC istisnalari mesajsiz gelebiliyor ve
# `str(e)` "No error" donuyor — gunlukte olculdu, tek hatanin ozeti kelimenin
# tam anlamiyla "HATA — No error" yaziyordu. Model dogru teshisi ancak kendi
# print'lerinden cikarabildi.
_BOS_HATA = {"no error", "none", "unknown", "bilinmeyen hata", ""}


def _hata_ozeti(iz: str) -> str:
    """Traceback'ten TEK anlamli satir.

    Son satir normalde "TipAdi: mesaj" olur ve isi gorur. Mesaj bos ya da
    "No error" ise o satir hicbir sey soylemez; boyle durumda istisna TIPI
    ile birlikte traceback'te bilgi tasiyan son satiri veriyoruz.
    """
    satirlar = [s.strip() for s in (iz or "").strip().splitlines() if s.strip()]
    if not satirlar:
        return "hata"
    son = satirlar[-1]
    tip, _, mesaj = son.partition(":")
    if mesaj.strip().lower() not in _BOS_HATA:
        return son
    # Mesaj bos: tipin kendisi hala degerli (Part.OCCError gibi). Ustune
    # traceback'ten sucu isaret eden son satiri ekle.
    tip = (tip or son).strip() or "hata"
    for s in reversed(satirlar[:-1]):
        if s.startswith("File ") or s.startswith("Traceback"):
            continue
        return f"{tip} (mesajsiz) — son satir: {s}"
    return f"{tip} (mesajsiz)"


@dataclass
class CalismaSonucu:
    basarili: bool = False
    hata_izi: str = ""
    cikti: str = ""
    uyarilar: list[str] = field(default_factory=list)
    eklenen: list[str] = field(default_factory=list)
    sure_sn: float = 0.0
    islem_adi: str = ""

    # Deterministik geometri kontrolu. Gorsel kontrol ANLAMSAL hatayi
    # yakalar; bu, goze normal gorunen bozuk topolojiyi. Bkz. dogrulama.py.
    dogrulama: "dogrulama.Rapor | None" = None
    # Kodun DOKUNDUGU nesneler (eklenen + degisen). Eklenenden farkli:
    # "pad.Length = 20" hicbir sey eklemez ama modeli bozabilir.
    dokunulan: list[str] = field(default_factory=list)
    # Bu belgede ILK AI degisikliginden once alinan yedegin yolu. Yalnizca
    # yedek gercekten alindiginda dolu — panel bunu bir kez gosteriyor.
    yedek: str = ""

    # Kod HIC KOSMADI: tekrar korumasi durdurdu (bkz. Executor._tekrar_engeli).
    # Hatadan ayri tutulmasi sart — bu bir hata degil, bir soru; modele
    # "kodun patladi" diye gonderilmemeli.
    engellendi: bool = False

    # FreeCAD'in kendi konsolundan yakalananlar — Report view'daki
    # TURUNCU (uyari) ve KIRMIZI (hata) satirlar.
    konsol_uyari: list[str] = field(default_factory=list)
    konsol_hata: list[str] = field(default_factory=list)

    # Calistirmanin ICINDEKI asamalar: {"exec": 0.02, "recompute": 0.01, ...}.
    # Yalnizca teshis icin; modele GITMEZ (bkz. modele_metin) — modelin
    # duzeltebilecegi bir sey degil, gurultu olur.
    asamalar: dict[str, float] = field(default_factory=dict)

    @property
    def ozet(self) -> str:
        if self.engellendi:
            return "ENGELLENDI — ayni kod az once kosmustu"
        if not self.basarili:
            return f"HATA — {_hata_ozeti(self.hata_izi)}"
        p = []
        if self.eklenen:
            p.append(f"{len(self.eklenen)} nesne eklendi")
        n = len(self.uyarilar) + len(self.konsol_uyari) + len(self.konsol_hata)
        if n:
            p.append(f"{n} uyari")
        if self.dogrulama is not None and self.dogrulama.bulgular:
            p.append(f"{len(self.dogrulama.bulgular)} geometri bulgusu")
        p.append(f"{self.sure_sn:.1f} sn")
        return " · ".join(p)

    def asama_metni(self, esik: float = YAVAS_ESIGI) -> str:
        """Asama dokumu — YALNIZCA calistirma esikten uzun surduyse.

        Bos donmesi normal hal: 0.1 saniyelik bir turun dokumu kimseye bir
        sey soylemez, her satira yazmak da gunlugu bogar. Uzun suren tur
        ise bu projede bir kez oldu ve sebebi ogrenilemedi — bir daha
        olursa satiri burada bulacagiz.
        """
        if self.sure_sn < esik or not self.asamalar:
            return ""
        p = [f"{ad} {sn:.2f} sn"
             for ad, sn in sorted(self.asamalar.items(),
                                  key=lambda kv: -kv[1]) if sn >= 0.05]
        return " · ".join(p)

    def modele_metin(self) -> str:
        """Modele geri gonderilecek ozet - konsol satirlari dahil."""
        p = [f"sonuc: {'BASARILI' if self.basarili else 'HATA'} ({self.ozet})"]
        if self.eklenen:
            p.append("eklenen nesneler: " + ", ".join(self.eklenen))
        for u in self.uyarilar:
            p.append("uyari: " + u)
        for u in self.konsol_hata:
            p.append("FreeCAD HATA: " + u)
        for u in self.konsol_uyari:
            p.append("FreeCAD uyari: " + u)
        if self.dogrulama is not None:
            d = self.dogrulama.metin()
            if d:
                p.append(d)
        if self.cikti:
            p.append("cikti:\n" + self.cikti[:2000])
        if not self.basarili:
            p.append("hata izi:\n" + self.hata_izi.strip()[-2000:])
        return "\n".join(p)


def _katinin_meshi(o):
    """KATI nesnenin dilimleyicide gorunecek hali. Olmuyorsa None.

    0.1 mm sapma disa aktarimin varsayilaniyla ayni; amac tam da o dosyayi
    onceden gormek. Belgeye HICBIR nesne eklemez.
    """
    try:
        import MeshPart

        sekil = getattr(o, "Shape", None)
        if sekil is None or not sekil.Faces:
            return None
        return MeshPart.meshFromShape(Shape=sekil, LinearDeflection=0.1,
                                      AngularDeflection=0.4)
    except Exception:                                            # noqa: BLE001
        return None


def _baski_kontrol_yap(nesne=None) -> bool:
    """Modelin kodun icinden cagirabildigi baskiya-hazirlik kontrolu.

    NEDEN NAMESPACE'TE. Kullanici "su an hazir mi", "baskiya hazir mi" diye
    neredeyse her oturumda soruyor (gunluk incelemesi 2026-08-21, madde 3)
    ve model bunu KANAATLE cevapliyordu. Deterministik cevabi FreeCAD hazir
    veriyor; eksik olan tek sey modelin onu tek satirda sorabilmesiydi.

    Ciktisi print ile gidiyor ve print ciktisi artik modele otomatik
    donuyor — yani `baski_kontrol(kupa)` yazmak tek turda cevap demek.

    `nesne` verilmezse belgedeki TUM mesh'lere bakar. Doner: hepsi hazir mi.
    """
    nesneler = []
    if nesne is None:
        doc = App.ActiveDocument
        if doc is not None:
            nesneler = [o for o in doc.Objects
                        if dogrulama._mesh_al(o) is not None]
        if not nesneler:
            print("baski_kontrol: belgede mesh nesnesi yok. "
                  "Kati nesne icin once MeshPart.meshFromShape ile mesh'e "
                  "cevir (CLAUDE.md'deki disa aktarim tarifi).")
            return False
    else:
        nesneler = [nesne]

    hepsi = True
    for o in nesneler:
        m = dogrulama._mesh_al(o)
        if m is None:
            # KATI nesne: eskiden burada "mesh degil, kontrol edilmedi" deyip
            # duruyorduk. OLCULDU (LOG/2026-08-24_5f9d2adc.txt 14:20:44):
            # model `baski_kontrol(sonuc)`u birlestirmenin sonucuna cagirdi ve
            # tek aldigi cevap o satir oldu — oysa dilimleyiciye giden sey
            # zaten mesh, yani soru anlamliydi. Baski sorulari KATI icin de
            # cevaplanabilir: dilimleyicinin gorecegi mesh'i uretip ona bak.
            m = _katinin_meshi(o)
            if m is None:
                print(f"{getattr(o, 'Name', o)}: ne mesh ne kati — "
                      f"kontrol edilemedi")
                hepsi = False
                continue
            print(f"{getattr(o, 'Name', o)}: kati — dilimleyicinin gorecegi "
                  f"mesh uretilip kontrol edildi (0.1 mm sapma)")
        hazir, engeller, olcumler = dogrulama.baskiya_hazir_mesh(m)
        ad = getattr(o, "Name", "mesh")
        print(f"{ad}: baskiya hazir = {'EVET' if hazir else 'HAYIR'}"
              f"  ({' '.join(olcumler)})")
        for tur, ayrinti in engeller:
            print(f"    - {tur}: {ayrinti}")
        hepsi = hepsi and hazir
    return hepsi


class _KonsolYakalayici:
    """FreeCAD'in konsol ciktisini yakalar — Report view'daki turuncu satirlar.

    Kullanicinin istegi: "uyari ve haber kodlarini da AI gorsun, yani turuncu
    kisimlari." Bu satirlarin cogu ISTISNA FIRLATMIYOR: recompute sessizce
    basarisiz olur, konsola bir sey yazar, kod "basarili" gorunur ve model
    neyin ters gittigini goremez.

    UC YOL DENENDI, ikisi elendi (olculdu, tahmin degil):

      1. `App.Console.AddObserver(...)`  -> FreeCAD 1.1'de YOK.
         Console modulunde yalnizca GetObservers/GetStatus/SetStatus ve
         Print* var; AddObserver kaldirilmis (AttributeError).
      2. `redirect_stdout` / `redirect_stderr` -> HICBIR SEY yakalamiyor.
         Console C++ tarafinda yaziyor, Python akislarina ugramiyor.
      3. Report view widget'ini okumak -> CALISIYOR ve asil istenen bu:
         kullanicinin ekranda gordugu satirlarin ta kendisi.

    Monkey-patch (Print* fonksiyonlarini sarmak) da CALISIYOR ama YETMIYOR:
    yalnizca Python'dan yapilan cagrilari yakaliyor. Olculdu - bos bir
    Part::Cut recompute edildiginde C++ uyarisi patch'e HIC ugramadi.
    O yuzden ikisi birlikte kullaniliyor: Report view asil kaynak,
    monkey-patch ise GUI yokken (testlerde) calisan yedek.

    Renk siniflandirmasi: Report view'da uyari turuncu, hata kirmizi.
    Metinde bunu ayirt edecek bir onek yok, o yuzden karakter bicimindeki
    on plan rengine bakiliyor. Renk okunamazsa satir "uyari" sayiliyor -
    kaybetmektense fazladan gostermek yeg.
    """

    SINIR = 40          # tek calistirmada saklanacak en fazla satir
    UZUNLUK = 400       # tek satirin en fazla uzunlugu

    def __init__(self) -> None:
        self.uyarilar: list[str] = []
        self.hatalar: list[str] = []
        self._metin_alani = None
        self._blok_sayisi = 0
        self._asil = {}

    # -- kurulum / sokum ---------------------------------------------------

    def bagla(self) -> None:
        self._report_view_bagla()
        self._patch_bagla()

    def coz(self) -> None:
        self._patch_coz()
        self._report_view_oku()

    # -- 1) Report view (asil kaynak, yalnizca GUI) ------------------------

    def _report_view_bul(self):
        try:
            import FreeCADGui as Gui
            from PySide import QtWidgets
        except Exception:
            return None
        try:
            mw = Gui.getMainWindow()
            if mw is None:
                return None
            # Report view'in objectName'i surumden surume degisebiliyor;
            # once ada, sonra dock basligina bakiyoruz.
            for ad in ("Report view", "ReportView", "Report View"):
                w = mw.findChild(QtWidgets.QTextEdit, ad)
                if w is not None:
                    return w
            for dock in mw.findChildren(QtWidgets.QDockWidget):
                baslik = (dock.windowTitle() or "").lower()
                if "report" in baslik or "rapor" in baslik:
                    w = dock.findChild(QtWidgets.QTextEdit)
                    if w is not None:
                        return w
        except Exception:
            return None
        return None

    def _report_view_bagla(self) -> None:
        self._metin_alani = self._report_view_bul()
        if self._metin_alani is None:
            return
        try:
            self._blok_sayisi = self._metin_alani.document().blockCount()
        except Exception:
            self._metin_alani = None

    def _report_view_oku(self) -> None:
        if self._metin_alani is None:
            return
        try:
            belge = self._metin_alani.document()
            for i in range(self._blok_sayisi, belge.blockCount()):
                blok = belge.findBlockByNumber(i)
                if blok is None or not blok.isValid():
                    continue
                metin = (blok.text() or "").strip()
                if not metin:
                    continue
                if self._hata_rengi_mi(blok):
                    self._ekle(self.hatalar, metin)
                elif self._uyari_rengi_mi(blok):
                    self._ekle(self.uyarilar, metin)
                # Siyah/gri = normal mesaj ve log: gurultu, alinmiyor.
        except Exception as e:
            log.uyari(f"Report view okunamadi: {e}")
        finally:
            self._metin_alani = None

    @staticmethod
    def _renk(blok):
        try:
            it = blok.begin()
            if it.atEnd():
                return None
            return it.fragment().charFormat().foreground().color()
        except Exception:
            return None

    @classmethod
    def _hata_rengi_mi(cls, blok) -> bool:
        r = cls._renk(blok)
        if r is None:
            return False
        # Kirmizi: kirmizi baskin, yesil ve mavi dusuk.
        return r.red() > 130 and r.green() < 90 and r.blue() < 90

    @classmethod
    def _uyari_rengi_mi(cls, blok) -> bool:
        r = cls._renk(blok)
        if r is None:
            # Renk okunamadi: kaybetmektense uyari say.
            return True
        # Turuncu/sari: kirmizi yuksek, yesil ORTA, mavi dusuk.
        return r.red() > 130 and 60 <= r.green() < 200 and r.blue() < 120

    # -- 2) Monkey-patch (yedek; GUI yokken tek calisan yol) ---------------

    def _patch_bagla(self) -> None:
        try:
            self._asil = {
                "PrintWarning": App.Console.PrintWarning,
                "PrintError": App.Console.PrintError,
            }

            def sar(liste, asil):
                def _f(*a, **k):
                    try:
                        metin = next((x for x in a if isinstance(x, str)), "")
                        self._ekle(liste, metin.strip())
                    except Exception:
                        pass          # yakalama, asil isi asla bozmasin
                    return asil(*a, **k)
                return _f

            App.Console.PrintWarning = sar(self.uyarilar,
                                           self._asil["PrintWarning"])
            App.Console.PrintError = sar(self.hatalar,
                                         self._asil["PrintError"])
        except Exception as e:
            log.uyari(f"konsol sarmalanamadi: {e}")
            self._asil = {}

    def _patch_coz(self) -> None:
        for ad, fn in self._asil.items():
            try:
                setattr(App.Console, ad, fn)
            except Exception:
                pass
        self._asil = {}

    # -- ortak -------------------------------------------------------------

    def _ekle(self, liste: list, metin: str) -> None:
        try:
            metin = (metin or "").strip()
            if not metin or len(liste) >= self.SINIR:
                return
            kisa = metin[:self.UZUNLUK]
            if kisa not in liste:      # Report view + patch ayni satiri
                liste.append(kisa)     # iki kez verebilir
        except Exception:
            pass


class _NamespaceKorumasi:
    """Belgede bir nesne SILINDIGINDE kalici namespace'i bosaltir.

    NEDEN VAR. Kalici namespace bilincli bir karar: model 1. turda
    `body = doc.addObject(...)` yazip 2. turda `body.Tip` demeye egilimli.
    Riski de belgeli — silinmis bir C++ nesnesini gosteren ad, istisna
    degil SERT COKME uretir (MANTIK 7).

    Onlem olarak `namespace_temizle()` vardi ama YALNIZCA panelden/AI'dan
    gelen geri almada cagriliyordu. Kullanici FreeCAD'in KENDI Ctrl+Z'sine
    bastiginda — ki normal yol budur — hicbir sey temizlenmiyordu. Yani en
    olagan senaryoda korumasizdik.

    Neden nesne nesne degil TOPTAN temizlik: namespace'teki hangi adin
    silinen nesneye baktigini anlamak icin degerlerin `.Name`'ine bakmak
    gerekir — ve o degerlerden bazilari zaten bayat olabilir; tam da
    kacindigimiz seye dokunmus oluruz. Toptan temizligin maliyeti ise
    yalnizca degisken sureklililigi, ki sozlesme zaten "her blokta
    nesneleri isimle yeniden coz" diyor.

    KENDI CALISTIRMAMIZ SIRASINDA ERTELENIR. `exec` calisirken namespace
    exec'in globals'i olarak duruyor; ortasinda bosaltmak her adi birden
    NameError yapardi. O yuzden bayrak konur, calistirma bitince temizlenir.
    """

    def __init__(self, sahip: "CodeExecutor") -> None:
        self._sahip = sahip
        self._acik = False

    # FreeCAD'in cagirdigi ad — degistirilemez. Istisna FIRLATMAMALI:
    # bildirim zincirinde calisiyor.
    def slotDeletedObject(self, nesne):
        try:
            self._sahip.silme_bildir()
        except Exception:
            pass

    def bagla(self) -> None:
        if self._acik:
            return
        try:
            App.addDocumentObserver(self)
            self._acik = True
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"namespace korumasi baglanamadi: {e}")

    def coz(self) -> None:
        if not self._acik:
            return
        try:
            App.removeDocumentObserver(self)
        except Exception:
            pass
        self._acik = False


class CodeExecutor:
    """Bir sohbet oturumu boyunca yasayan calistirici."""

    def __init__(self) -> None:
        self._ns: dict = {}
        self._sayac = 0
        self._oturum = "0"
        # Yedegi alinmis belgeler (doc.Name). Belge basina BIR kez.
        self._yedekli: set[str] = set()
        self._calisiyor = False
        self._silme_bekliyor = False
        # Tekrar korumasi: kod metni -> son BASARILI kosma zamani, ve
        # engellendikten sonra kullanicinin tekrar basarak onayladiklari.
        self._son_kosan: dict[str, float] = {}
        self._tekrar_onayli: set[str] = set()
        self._koruma = _NamespaceKorumasi(self)
        self._koruma.bagla()

    def oturumu_ayarla(self, oturum: str) -> None:
        self._oturum = (oturum or "0")[:8]

    def kapat(self) -> None:
        """Panel kapanirken. Sizan gozlemci her belge olayinda atesler."""
        self._koruma.coz()

    def silme_bildir(self) -> None:
        """Gozlemciden gelir: belgede bir nesne silindi."""
        if self._calisiyor:
            # Kendi kodumuz calisiyor; namespace su an exec'in globals'i.
            self._silme_bekliyor = True
            return
        if self._ns:
            self.namespace_temizle("nesne silindi")

    def namespace_temizle(self, sebep: str = "") -> None:
        """Undo/redo/silme sonrasi cagrilir.

        Sebep: onceki blokta `body = doc.addObject(...)` diye baglanan bir ad,
        kullanici Ctrl+Z yaptiktan sonra SILINMIS bir C++ nesnesini gosterir.
        Ona dokunmak istisna degil SERT COKME uretir. Bagi kesmek en ucuz
        savunma; sistem promptunda ayrica "her blokta nesneleri isimle yeniden
        coz" kurali var.
        """
        self._ns.clear()
        log.ayik("namespace temizlendi" + (f" ({sebep})" if sebep else ""))

    # -- yedek -------------------------------------------------------------

    def _yedek_al(self, doc) -> str:
        """Bu belgedeki ILK AI degisikliginden once bir kopya birakir.

        MANTIK 6'nin ikinci katmani. Uzun bir seansta model kendi hasarini
        ustune ustune biriktirebiliyor (olculdu: 2026-08-19 oturumunda
        ithal STEP'in bozuk BRep'i uzerine kurulan boolean zinciri) ve
        Ctrl+Z yigini o kadar geriye yetmeyebiliyor.

        ASLA isi engellemez: yedek alinamazsa uyarilir ve devam edilir.
        Yedek almak icin belgenin kaydedilmis olmasi gerekmiyor.
        """
        try:
            ad = doc.Name
        except Exception:
            return ""
        if ad in self._yedekli:
            return ""
        # Bir kez denendi say: her turda basarisiz bir yedegi tekrar
        # denemek her turu yavaslatir.
        self._yedekli.add(ad)

        try:
            from .. import config

            damga = time.strftime("%Y-%m-%d_%H%M%S")
            yol = config.yedek_dizini() / f"{ad}_{damga}.FCStd"
            doc.saveCopy(str(yol))
            log.bilgi(f"yedek alindi: {yol}")
            return str(yol)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"yedek alinamadi ({e}); is devam ediyor")
            return ""

    # -- tekrar korumasi ---------------------------------------------------

    def _tekrar_engeli(self, kod: str) -> str:
        """Ayni kod kisa sure icinde ikinci kez kosuyorsa BIR KEZ durdurur.

        NEDEN BURADA, KARTTA DEGIL. Bu koruma once panelde vardi
        (code_card: "ikinci basista onay sor") ve YETMEDI — gunlukte, onay
        penceresi VARKEN olculdu:

            baa70fa4  16:05:24  "Sadece 2 yama merkezini duzelt"  BASARILI
                      16:05:26  ayni kod, aynen                   BASARILI
                      16:05:28  ayni kod, aynen                   BASARILI

        Mesh her seferinde yeniden yamandi, oturum orada bitti. Kartin
        korumasi kendi `_sonuc` alanina bakiyor; yeni bir kart nesnesi
        olusursa ya da sonuc yanlis karta yazilirsa (dock: `k.blok is blok`
        kimlik eslesmesi) koruma bosa dusuyor. Kod calistirmak BIRIKIMLI bir
        islem: ikinci calistirma "tekrarlamaz", USTUNE EKLER. O yuzden
        koruma tiklamanin oldugu yerde degil, HASARIN oldugu yerde durmali —
        hangi yoldan gelirse gelsin buradan geciyor.

        Kullanicinin kendi ifadesi (2026-08-19 dcd21af7): "yanlislikla cok
        calistirdim tekrar calistira bastim yeniden ilk haline al".

        ONAY MEKANIZMASI TEKRARDIR: engellenen kod isaretlenir, kullanici
        yine calistirmak isterse ikinci basista koser. Burada Qt yok
        (MANTIK 12), soru soramayiz — ama "tekrar bas" bir onay kadar acik.

        Yalnizca BASARILI kosular sayiliyor: patlayan kod belgeye hicbir sey
        yazmadi, tekrari zararsiz ve otomatik onarim yolunu tikamamali.
        """
        anahtar = (kod or "").strip()
        if not anahtar:
            return ""

        zaman = self._son_kosan.get(anahtar)
        if zaman is None or (time.time() - zaman) > TEKRAR_PENCERESI:
            return ""
        if anahtar in self._tekrar_onayli:
            self._tekrar_onayli.discard(anahtar)
            return ""

        self._tekrar_onayli.add(anahtar)
        gecen = time.time() - zaman
        log.uyari(f"ayni kod {gecen:.0f} sn once kosmustu, engellendi")
        return (f"Bu kod {gecen:.0f} saniye once AYNEN calisti ve "
                f"engellendi.\n\nKod calistirmak birikimlidir: tekrar "
                f"calistirmak isi TEKRARLAMAZ, ustune bir kopya daha ekler "
                f"(ikinci bir govde, ikinci bir yama, ikinci bir delik).\n\n"
                f"Gercekten tekrar calistirmak istiyorsan Calistir'a bir kez "
                f"daha bas — bu sefer koser.")

    def _tekrar_kaydet(self, kod: str) -> None:
        anahtar = (kod or "").strip()
        if not anahtar:
            return
        self._son_kosan[anahtar] = time.time()
        # Sinirsiz buyumesin: eski kayitlar zaten pencerenin disinda kaliyor.
        if len(self._son_kosan) > 40:
            eski = sorted(self._son_kosan.items(), key=lambda kv: kv[1])
            for k, _ in eski[:20]:
                self._son_kosan.pop(k, None)

    # -- ana giris ---------------------------------------------------------

    def calistir(self, kod: str, baslik: str = "") -> CalismaSonucu:
        doc = App.ActiveDocument
        if doc is None:
            return CalismaSonucu(
                hata_izi="Acik belge yok. Once File > New ile bir belge ac.",
                islem_adi="")

        self._sayac += 1
        ad = (baslik or "degisiklik").strip().replace("\n", " ")[:60]
        islem_adi = f"AI: {ad}"

        engel = self._tekrar_engeli(kod)
        if engel:
            return CalismaSonucu(hata_izi=engel, engellendi=True,
                                 islem_adi=islem_adi)
        dosya_adi = f"<caddy:{self._oturum}:tur{self._sayac}>"

        # Derleme HATASI islem acmadan yakalanmali — bos bir undo girdisi
        # birakmanin anlami yok.
        try:
            kod_nesnesi = compile(kod, dosya_adi, "exec")
        except SyntaxError:
            return CalismaSonucu(hata_izi=traceback.format_exc(),
                                 islem_adi=islem_adi)

        # Traceback'in kaynak satirini gosterebilmesi icin (bkz. modul basligi)
        linecache.cache[dosya_adi] = (
            len(kod), None, kod.splitlines(True), dosya_adi)

        # ILK degisiklikten ONCE yedek. Islemi acmadan once, cunku yedek
        # kodun degil belgenin BUGUNKU halinin kopyasi olmali.
        #
        # Cagri yeri de korumali: _yedek_al kendi icinde yakaliyor ama bu
        # SOZ yapisal olmali, gozle dogrulanan bir sey degil. Emniyet
        # mekanizmasinin asil isi engellemesi, engellemeye calistigi seyden
        # kotu olurdu.
        try:
            yedek_yolu = self._yedek_al(doc)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"yedek alinamadi ({e}); is devam ediyor")
            yedek_yolu = ""

        onceki = {o.Name for o in doc.Objects}
        cikti, hata_akisi = io.StringIO(), io.StringIO()
        konsol = _KonsolYakalayici()
        izleyici = dogrulama.Izleyici()
        # Blogun kendi `cakisma_kontrol` ciktisi ile dogrulama taramasinin
        # BULGU satirlari ayni cifti iki kez yaziyordu; kayit her blokta
        # sifirdan baslar (bkz. olcum._bildirilen_gecisler).
        olcum.bildirilen_gecisleri_sifirla()
        # Asama saati. Toplam sureyi bilmek yetmiyordu: 17.1 saniyenin
        # nereye gittigi gunlukten cikarilamadi (bkz. YAVAS_ESIGI).
        asamalar: dict[str, float] = {}
        t0 = _onceki_asama = time.time()

        def _asama(ad: str) -> None:
            nonlocal _onceki_asama
            simdi = time.time()
            asamalar[ad] = simdi - _onceki_asama
            _onceki_asama = simdi

        App.setActiveTransaction(islem_adi, True)
        _asama("islem ac")
        konsol.bagla()
        izleyici.bagla()
        _asama("gozlemci bagla")
        self._calisiyor = True
        self._silme_bekliyor = False
        try:
            with redirect_stdout(cikti), redirect_stderr(hata_akisi):
                # `_hazirla` exec'in argumaninda degil AYRI satirda: ilk
                # turda pahali olabilen importlar orada ve kendi asamasi
                # olmadan `exec`in icinde gorunmez halde kaliyordu.
                ns = self._hazirla(doc)
                _asama("hazirla")
                exec(kod_nesnesi, ns)
                _asama("exec")
                doc.recompute()
                _asama("recompute")
            App.closeActiveTransaction(False)          # islensin
            basarili, iz = True, ""
        except BaseException:
            App.closeActiveTransaction(True)           # iptal -> tek temiz geri alma
            basarili, iz = False, traceback.format_exc()
        finally:
            # Sizan bir gozlemci kullanicinin her hareketinde atesler.
            izleyici.coz()
            konsol.coz()
            self._calisiyor = False
            # Kod patladiysa yukaridaki asamalarin bir kismi hic kaydedilmedi;
            # kalan sure buraya yaziliyor ki dokumun toplami sure_sn olsun.
            _asama("kapanis")
            sure = time.time() - t0

        # Kod (ya da iptal) bir nesne sildiyse namespace artik guvenilmez.
        # exec bittigi icin simdi bosaltmak zararsiz.
        if self._silme_bekliyor:
            self._silme_bekliyor = False
            self.namespace_temizle("calistirma sirasinda silme")

        sonuc = CalismaSonucu(
            basarili=basarili,
            hata_izi=iz,
            cikti=(cikti.getvalue() + hata_akisi.getvalue()).strip(),
            sure_sn=sure,
            islem_adi=islem_adi,
            yedek=yedek_yolu,
            asamalar=asamalar,
        )

        # Yavas tur: dokum Report view'a da dusuyor. Gunluge sohbet_log
        # yaziyor; ikisi ayri kanal, ikisinde de olmasi lazim cunku
        # kullanici sikayet ettiginde once Report view'a bakiyor.
        dokum = sonuc.asama_metni()
        if dokum:
            log.uyari(f"yavas calistirma ({sure:.1f} sn): {dokum}")

        # FreeCAD'in KENDI konsolu (Report view'daki turuncu/kirmizi satirlar).
        # Bunlar cogu zaman istisna FIRLATMAZ — recompute sessizce basarisiz
        # olur, "Links go out of the allowed scope" yazar ve kod "basarili"
        # gorunur. Modelin bunlari gormesi lazim.
        sonuc.konsol_uyari = konsol.uyarilar
        sonuc.konsol_hata = konsol.hatalar

        if basarili:
            # Yalnizca basarili kosu tekrar korumasina sayilir: patlayan kod
            # belgeye hicbir sey yazmadi.
            self._tekrar_kaydet(kod)
            sonuc.eklenen = [o.Name for o in doc.Objects if o.Name not in onceki]
            # Dokunulan = gozlemcinin gordukleri + eklenenler. Gozlemci
            # baglanamadiysa (eski surum, tuhaf kurulum) en azindan
            # eklenenler kontrol edilsin — dogrulama tamamen susmasin.
            mevcut = {o.Name for o in doc.Objects}
            sonuc.dokunulan = sorted((izleyici.adlar | set(sonuc.eklenen))
                                     & mevcut)
            sonuc.uyarilar = self._yumusak_hatalar(doc, sonuc.eklenen, kod)
            try:
                sonuc.dogrulama = dogrulama.dogrula(doc, sonuc.dokunulan)
            except Exception as e:                       # noqa: BLE001
                # Dogrulama, basarili bir isin ustune kosuyor. Burada
                # patlamak iyi biten bir isi kotu bitirmek olur.
                log.uyari(f"dogrulama kosmadi: {e}")
            log.bilgi(f"{islem_adi} — {sonuc.ozet}")
        else:
            log.hata(f"{islem_adi} calismadi, islem geri alindi")

        return sonuc

    # -- ic ---------------------------------------------------------------

    def _hazirla(self, doc) -> dict:
        """Kalici namespace'i her calistirmada tazeler.

        Kalici olmasi bilincli: model 1. turda `body = ...` yazip 2. turda
        `body.Tip` demeye egilimli. Ama bayat baglama riskine karsi
        namespace_temizle() ve sistem promptu kurali var.
        """
        import Part

        ns = self._ns
        ns.update({
            "__name__": "__caddy__",
            "App": App,
            "FreeCAD": App,
            "Part": Part,
            "doc": doc,
            "Vector": App.Vector,
            "Placement": App.Placement,
            "Rotation": App.Rotation,
        })

        # Bunlar her kurulumda olmayabilir ya da yuklenmesi pahali olabilir;
        # yoklugu calistirmayi engellememeli.
        for ad in ("Sketcher", "Draft", "Mesh", "PartDesign"):
            if ad in ns:
                continue
            try:
                ns[ad] = __import__(ad)
            except Exception:
                pass

        try:
            import FreeCADGui
            ns["Gui"] = ns["FreeCADGui"] = FreeCADGui
        except Exception:
            pass

        import math
        ns.setdefault("math", math)
        # Olcum yardimcilari. Kullanicinin sozu: "caddy direkt olcse daha
        # iyi olur". Mesh'te yuz/kenar olmadigi icin olcu hesaplanmak
        # zorunda; bunlar o hesabi tek cagriya indiriyor. Bkz. olcum.py.
        ns["baski_kontrol"] = _baski_kontrol_yap
        ns["olc"] = olcum.olc
        ns["kesit_capi"] = olcum.kesit_capi
        ns["duvar_kalinligi"] = olcum.duvar_kalinligi
        ns["mesafe"] = olcum.mesafe
        ns["olcu"] = olcum.olcu
        # "Degiyor mu, icinden geciyor mu" — goruntuye SORULMAYACAK soru.
        # Olculdu (MANTIK 39): model 3 kareye bakip "cakisma yok" dedi ve
        # yanildi; ayni cakismayi ayni model elle yazdigi ucluyle buldu.
        ns["cakisma_kontrol"] = olcum.cakisma_kontrol
        # Modelin gunluklerde ELLE yazdigi iki kalip. Sayildi (PLAN S8):
        # isValid 156, isSolid 125, hasSelfIntersections 96, Solids 86 kez;
        # "simetri" 5 ayri gunlukte 38 kez. Ikisi de yeni geometri degil,
        # FreeCAD'in kendi cagrilarinin sarmalayicisi.
        ns["saglik"] = olcum.saglik
        ns["simetri"] = olcum.simetri
        # Mevcut isin uzerine calisirken ILK adim: her seyi olc.
        ns["kesif"] = kesif.kesif
        # FreeCAD'in hazir yetenekleri. Modelin elle geometri yazmasinin
        # yerini aliyorlar; bkz. islem.py modul basligi.
        for _ad in ("mesh_onar", "kati_yap", "icini_bosalt", "olcu_tablosu",
                    "bagla", "yazi", "vida_disi", "agirlik", "baskiya_bol",
                    "dizi_polar", "dizi_dogrusal", "tabana_otur",
                    "birlestir", "kesit_konturu"):
            ns[_ad] = getattr(islem, _ad)
        return ns

    def _yumusak_hatalar(self, doc, eklenen: list[str], kod: str) -> list[str]:
        """Kod PATLAMADI ama sonuc yine de bozuk olabilir.

        Bunlar hata sayilmaz (islem islendi), ama sonraki tura baglam olarak
        gider — model kendi cikardigi cop'u gormeli.

        SEKIL kontrolleri burada DEGIL: onlar dogrulama.py'ye tasindi, cunku
        orada hem daha genis bir kumeye (dokunulan, yalnizca eklenen degil)
        hem de daha derinine (hacim isareti, kapali kabuk) bakiliyor. Burada
        kalanlar sekille ilgisi olmayan seyler: nesne durumu ve politika.
        Ikisinde birden raporlamak modele ayni seyi iki kez soylerdi.
        """
        u: list[str] = []

        for ad in eklenen:
            o = doc.getObject(ad)
            if o is None:
                continue
            durum = " ".join(getattr(o, "State", []) or [])
            if "Invalid" in durum or "Error" in durum:
                u.append(f"{ad}: gecersiz durum ({durum})")

        # Parametrik politika ihlali: olu sekil uretimi. Bu eklentinin butun
        # amaci insanin sonradan duzenleyebilecegi geometri birakmak.
        if "Part::Feature" in kod or "Part.show(" in kod:
            u.append("olu sekil (Part::Feature/Part.show) uretildi — "
                     "insan bunu parametrik olarak duzenleyemez")

        try:
            kalan = [o.Name for o in doc.Objects if o.MustExecute]
            if kalan:
                u.append(f"hala hesaplanmamis nesne var: {', '.join(kalan[:5])}")
        except Exception:
            pass

        return u
