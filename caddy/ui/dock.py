"""CADdy paneli — FreeCAD ana penceresine yerlesen QDockWidget.

Neden Task panel (Gui.Control.showDialog) DEGIL: Task paneli tek bir yuvayi
isgal eder, Sketcher/PartDesign gibi araclarla catisir ve secim degisince
kendini kapatir. Sohbet paneli kalici olmali.

Desen `src/Mod/Help/Help.py:481-503`'ten alindi: dock'u objectName ile ara,
varsa yeniden kullan — yoksa her cagrida bir yenisi birikir.
"""

from __future__ import annotations

import os
import time

from PySide import QtCore, QtGui, QtWidgets

from .. import config, kayitlar, locate, log
from ..conversation import ConversationController, _short_num
from .code_card import CodeCard

NESNE_ADI = "CaddyPanel"

# Ikon dugmesinin ikon kenari. Metin dugmesinin genisligini Qt'nin 80 px'lik
# TABANI belirliyordu (bkz. _arac_cubugu); ikon dugmesi o tabana bagli degil,
# genisligini biz veriyoruz.
#
# 20 -> 18: ust satira dorduncu dugme ("Kayıtlar") eklendi ve kullanici
# "butonları küçülteceğiz" dedi. Yukseklik burada DEGIL, _yuksekligi_esitle'de
# belirleniyor (komsu kutulara denkleniyor); bu sabit yalnizca genisligi ve
# ikonun tavanini veriyor.
IKON_PX = 18


def _ikon(ad: str):
    """resources/icons/<ad> QIcon olarak; yuklenemezse None.

    None donerse cagiran taraf METNE geri doner — ikonsuz ve metinsiz bir
    dugme tiklanamaz bir bosluk olurdu (ayni gerekce ust_menu._logo'da).
    """
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    yol = os.path.join(kok, "resources", "icons", ad)
    if not os.path.exists(yol):
        return None
    ikon = QtGui.QIcon(yol)
    return None if ikon.isNull() else ikon


def _ikon_dugmesi(ad: str, yedek_metin: str) -> QtWidgets.QPushButton:
    """Ikonlu dugme; ikon yoksa METNE doner — islev hicbir halde kaybolmaz.

    Ikon dugmesinde etiket gorunmedigi icin cagiran taraf ipucunun ILK
    SATIRINA dugmenin adini yazmak zorunda: kullanici ikonu tanimazsa ne
    yaptigini baska yerden ogrenemez.
    """
    d = QtWidgets.QPushButton()
    ikon = _ikon(ad)
    if ikon is None:
        d.setText(yedek_metin)
        log.uyari(f"ikon yuklenemedi ({ad}) — dugme metne dondu")
        return d
    d.setIcon(ikon)
    d.setIconSize(QtCore.QSize(IKON_PX, IKON_PX))
    # YALNIZCA GENISLIK sabit. Yukseklik cagirana birakiliyor: burada
    # sabitlemek dugmeyi komsularindan (Yeni, model/efor kutulari) DAHA
    # UZUN yapiyordu ve satir tirtikli gorunuyordu — kullanicinin sikayeti
    # buydu. Yukseklik _yuksekligi_esitle ile komsulara denklenir.
    d.setFixedWidth(IKON_PX + 10)
    # ...AMA setFixedWidth TEK BASINA YETMIYOR.
    #
    # OLCULDU (kullanicinin Rapor penceresi, 2026-08-28 — offscreen degil,
    # bkz. MANTIK 45.4b): alti QPushButton'un da ELLE konmus asgarisi
    # 106 px cikti, oysa buradaki cagri 28 diyor. Sebep FreeCAD'in tema
    # stil sayfasi: `QPushButton { min-width: ... }` tanimliyor ve Qt bunu
    # polish sirasinda widget'in uzerinde `setMinimumWidth()` cagirarak
    # uyguluyor — yani bizim satirimizin USTUNE yaziyor. Ust satir boylece
    # 4x106 + kutular = 651 px taban koyuyordu ve panel %40'a (512 px) bir
    # turlu inmiyordu.
    #
    # Kural sayfayla konuldugu icin ancak sayfayla kalkar: kaskadda daha
    # OZEL olan (widget'in kendi stil sayfasi) kazanir. Diger tema
    # kurallari (renk, kenarlik) kaskadda duruyor, yalnizca genislik
    # eziliyor. `min-width` icerik kutusunu olctugu icin dolgu da burada
    # kisiliyor, yoksa tema dolgusu genisligi geri buyuturdu.
    d.setStyleSheet("QPushButton { min-width: %dpx; max-width: %dpx; "
                    "padding-left: 5px; padding-right: 5px; }"
                    % (IKON_PX, IKON_PX))
    return d


def _yuksekligi_esitle(dugmeler, olcutler) -> int:
    """Ikon dugmelerini KOMSU DUGMELERIN boyuna oturtur; kullanilan boyu doner.

    Neden olcerek: dugmenin dogal yuksekligi uslupa/temaya/yazi tipine gore
    degisir; sabit bir sayi yazmak (once 30 px yaziliydi) baska makinede yine
    tirtikli satir demek.

    Olcut ONCE metin dugmesiydi: satirda hem dugme hem kutu vardi ve Qt'nin
    dogal boylari esit degil (olculdu, offscreen: dugme 20 px, kutular
    22 px); ikon dugmesini kutuya denklersek metin dugmesinden ayrisirdi.
    ARTIK metin dugmesi kalmadi (dordu de ikon), o yuzden olcut KUTULAR —
    boylece satirin TAMAMI 22 px, tek boy. En UZUN olcut aliniyor.
    """
    h = max([o.sizeHint().height() for o in olcutler] or [0])
    for d in dugmeler:
        d.setFixedHeight(h)
        # Ikon dugmenin ICINE sigmali: cerceve payi dusulmezse Qt ikonu
        # kirpar/kucultur ve sekil bulaniklasir. 6 px pay iki yandan.
        if not d.icon().isNull():
            k = max(12, h - 6)
            d.setIconSize(QtCore.QSize(k, k))
    return h


_RENK = {
    "user": "#1a5fb4",
    "ai": "#2d2d2d",
    "sistem": "#a05000",
}


class SaranEtiket(QtWidgets.QTextEdit):
    """Metin kutusu — icerigi panelin SAGINA TASAMAZ. Sert sinir.

    Neden QLabel DEGIL. Iki ayri sorun var ve QLabel yalnizca birincisini
    cozebiliyordu:

      1. Sarma acik bir QLabel bile `minimumSizeHint().width()` degerini en
         uzun BOLUNEMEZ parcaya gore verir. Olculdu: tek bir traceback yolu
         (C:\\Users\\...\\executor.py) icin 660 piksel. Dar bir yan panelde
         bu, QScrollArea'ya yatay kaydirma cubugu actiriyordu.
      2. Asgari genisligi sifirlasan bile QLabel o uzun parcayi BOLEMEZ:
         satira sigmayan yol sagdan tasar ve gorunmez olur. Kullanicinin
         ikinci sikayeti tam buydu — "biraz saga kayan metinleri
         goremiyorum".

    Ikincisinin Qt'deki tek dogru cozumu `QTextOption.
    WrapAtWordBoundaryOrAnywhere`: once bosluktan boler, olmuyorsa
    KARAKTERDEN boler. QLabel'da bu ayar YOK; QTextDocument'i olan bir
    widget gerekiyor. O yuzden gorunusu etikete benzetilmis bir QTextEdit:
    cercevesiz, saydam, salt okunur, iki kaydirma cubugu da kapali,
    yuksekligi icerige gore sabitlenmis.

    Tekerlek olayi bilincli olarak YUTULMUYOR: sohbeti kaydirirken imlec
    bir mesajin uzerine geldiginde kaydirmanin durmasi, cozdugumuz sorundan
    daha sinir bozucu olurdu.
    """

    def __init__(self, metin: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.viewport().setAutoFillBackground(False)

        secenek = QtGui.QTextOption()
        secenek.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(secenek)
        self.document().setDocumentMargin(0)

        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                           QtWidgets.QSizePolicy.Fixed)
        self._renk = "#2d2d2d"
        self._italik = False
        self._bicimle()
        self.setText(metin)

    # -- etiket gibi davranmasi icin ---------------------------------------

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, metin: str) -> None:
        self.setPlainText(metin or "")
        self._yuksekligi_ayarla()

    def bicim_ver(self, renk: str = "", italik: bool | None = None,
                  kalin: bool = False) -> None:
        if renk:
            self._renk = renk
        if italik is not None:
            self._italik = italik
        if kalin:
            f = self.font()
            f.setBold(True)
            self.setFont(f)
        self._bicimle()
        self._yuksekligi_ayarla()

    def _bicimle(self) -> None:
        self.setStyleSheet(
            f"QTextEdit{{color:{self._renk};background:transparent;border:0;"
            + ("font-style:italic;" if self._italik else "")
            + "}")

    # -- yukseklik ---------------------------------------------------------

    def _yuksekligi_ayarla(self) -> None:
        """Yuksekligi SARMA SONRASI gercek icerige gore sabitler.

        Dikey cubuk kapali oldugu icin yukseklik yanlissa metin alttan
        kirpilir — yani yatay tasmayi cozup yerine dikey tasma koymus
        olurduk.
        """
        d = self.document()
        d.setTextWidth(max(1, self.viewport().width()))
        h = int(d.size().height())
        self.setFixedHeight(max(h, self.fontMetrics().lineSpacing()) + 2)

    def resizeEvent(self, olay):
        super().resizeEvent(olay)
        self._yuksekligi_ayarla()

    def minimumSizeHint(self) -> QtCore.QSize:
        # Genislik dayatma: panelin ne kadar daralacagini icerik degil
        # kullanici belirlesin.
        return QtCore.QSize(0, self.height())

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, self.height())

    def wheelEvent(self, olay):
        # Kaydirma sohbetin isi; burada yutulursa imlec mesaja gelince
        # sohbet kaydirmasi duruyor.
        olay.ignore()


class CaddyPanel(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ctl = ConversationController(self)
        self._kartlar: list[CodeCard] = []
        self._bekleyen: CodeCard | None = None
        # Yanit akarken gosterilen gecici kutu. Tur bitince SILINIR ve yerine
        # duzgun ayristirilmis metin + kod kartlari konur - yoksa ayni yanit
        # iki kez gorunurdu.
        self._canli: QtWidgets.QLabel | None = None
        self._canli_metin = ""
        self._dusunce: QtWidgets.QLabel | None = None

        # Ilerleme gostergesi. Sabit bir "dusunuyor…" yazisi yetmiyor:
        # olculdu, zor bir istekte model 131 sn dusunuyor ve bu sure boyunca
        # ekranda HICBIR SEY degismiyordu — kullanici hakli olarak "takildi"
        # sandi. Saniye saydiran bir saat + CLI'in nabzindan gelen dusunme
        # tokeni, "yasiyor" demenin en ucuz yolu.
        self._ilerleme: QtWidgets.QLabel | None = None
        self._t0 = 0.0
        self._asama_ad = ""
        self._dusunce_tk = 0
        self._tiklayici = QtCore.QTimer(self)
        self._tiklayici.setInterval(1000)
        self._tiklayici.timeout.connect(self._ilerlemeyi_yaz)

        d = QtWidgets.QVBoxLayout(self)
        d.setContentsMargins(6, 6, 6, 6)
        d.setSpacing(6)

        d.addLayout(self._arac_cubugu())
        d.addWidget(self._konusma_alani(), 1)
        d.addLayout(self._giris_alani())

        self.bilgi = QtWidgets.QLabel("")
        self.bilgi.setStyleSheet("color:#666;")
        d.addWidget(self.bilgi)

        self.ctl.mesaj.connect(self.mesaj_ekle)
        self.ctl.oneri.connect(self.kart_ekle)
        self.ctl.calisma_sonucu.connect(self._calisma_sonucu)
        self.ctl.durum.connect(self._durum)
        self.ctl.bilgi_satiri.connect(self._bilgi_satiri)
        self.ctl.akis_basladi.connect(self._akis_basladi)
        self.ctl.akis_parcasi.connect(self._akis_parcasi)
        self.ctl.dusunce_parcasi.connect(self._dusunce_parcasi)
        self.ctl.dusunce_olcusu.connect(self._dusunce_olcusu)
        self.ctl.akis_bitti.connect(self._akis_bitti)
        self.ctl.asama.connect(self._asama)

        self._karsilama()

        # ISITMA. `calistir` icindeki tek pahali olabilecek is, `_hazirla`nin
        # yaptigi importlar (GUI'de `Draft` olculdu: 0.19 sn). Panel acildiktan
        # hemen sonra, kullanici daha yazmadan yapiliyor — kritik yolun
        # disinda. singleShot(0): once pencere cizilsin, sonra isinsin.
        QtCore.QTimer.singleShot(0, self._isit)

        # SAG TIK MENUSU KALDIRILDI. Icinde tek bir oge vardi ("Sohbet
        # kayıtlarını aç") ve o ogenin sebebi ust satirda yer olmamasiydi.
        # Kayitlar artik gorunur bir IKON dugmesi (bkz. _arac_cubugu), yani
        # menu ayni islevin ikinci ve GIZLI kapisiydi; kullanici zaten
        # bulamadigini soylemisti. Iki kapi yerine gorunen tek kapi.

    def _isit(self) -> None:
        """Pahali importlari kullanici beklemeden yapar. Sessizce basarisiz olur.

        Isinmazsa hicbir sey bozulmaz: `_hazirla` ayni importlari zaten
        kendisi yapiyor, yalnizca faturasi ilk Calistir'a kesiliyor.
        """
        try:
            from ..execution.executor import isit

            isit()
        except Exception as e:                                   # noqa: BLE001
            log.ayik(f"isitma yapilamadi: {e}")

    def closeEvent(self, olay):
        # Kalici surec artik turlar arasi ayakta duruyor; panel kapanirken
        # onu birakmak, FreeCAD'den sonra da yasayan bir claude.exe demek.
        try:
            self.ctl.transport.kapat()
        except Exception:
            pass
        # Sizan bir DocumentObserver kullanicinin HER belge hareketinde
        # atesler ve panel kapandiktan sonra da yasar.
        try:
            self.ctl.executor.kapat()
        except Exception:
            pass
        super().closeEvent(olay)

    # -- kurulum -----------------------------------------------------------

    def _arac_cubugu(self) -> QtWidgets.QHBoxLayout:
        """Ust satir — ETIKETLER KISA, aciklama ipucunda.

        Neden kisa: bu satir panelin ASGARI genisligini belirliyordu.
        Olculdu (offscreen, gercek widget'lar): satirin asgari genisligi
        876 px, panelinki 888 px — ve panel 400 px'e zorlandiginda 888'de
        kaliyordu. Yani "paneli daralt" istegi, etiketler kisalmadan
        FIZIKSEL OLARAK imkansizdi; `resizeDocks` bile bu tabani asamaz.

        Etiket basina olculen pay:
            "Son AI değişikliğini geri al"  344 px
            model kutusu ("Opus (iyi kalite)") 270 px
            "Yeni sohbet"                   140 px
            "Kayıtlar"                      104 px

        Bilgi kaybi yok: her dugmenin tam cumlesi setToolTip'te duruyor,
        model kutusunun olculmus hiz/kalite notu zaten ipucundaydi.

        SONRA "Ileri al" eklendi ve taban 492 -> 602 px'e cikti, yani %40
        hedefinin (592 px) USTUNE. Yeni olcum (offscreen, gercek widget):

            "Yeni" 80 · "Geri al" 92 · "İleri al" 104 · "Kayıtlar" 104
            model kutusu 186 · araliklar 24            -> satir 590

        80 px Qt'nin dugme TABANI — "Geri"/"İleri"/"Kayıt" hepsi 80 px, yani
        o esigin altinda kisaltmak bedava degil, faydasiz. Yer "Kayıtlar" ->
        "Kayıt" ile acildi (104 -> 80); geri/ileri ciftinin "al"i duruyor,
        cunku "Geri"/"İleri" tek basina gezinme dugmesi gibi okunuyor.

        EN SON efor kutusu eklendi (dusunme miktari — gecikmenin %91-94'u,
        bkz. config.EFORLAR). "Kayıt" dugmesini silmek TEK BASINA yetmedi:

            Kayıt yok + model(186) + efor(102)   -> panel 600, TASAR
            Kayıt yok + model(102) + efor( 90)   -> panel 504, sigar

        Yani model kutusu da kisaldi: "Opus · iyi" -> "Opus" (186 -> 102).
        Kalite notu kaybolmadi, zaten oge ipucundaydi. "Kayıt" dugmesinin
        islevi once sag tik menusune tasindi; kullanici bulamadi, bu yuzden
        simdi ikon dugmesi olarak geri geldi ve menu kaldirildi.

        EN SON "Geri al"/"İleri al" METINDEN IKONA cevrildi. Sikayet: dar
        panelde AI yanitinin sag tarafi kirpiliyor. Olculdu (ayni offscreen
        test, gercek widget'lar):

            metin dugmeleri : ust satir 492 -> panel asgari 504 px
            ikon dugmeleri  : ust satir 356 -> panel asgari 368 px

        136 px kazanc, cunku metin dugmesi Qt'nin 80 px'lik TABANINA
        oturuyordu; ikon dugmesinin genisligini biz veriyoruz (30 px, bkz.
        IKON_PX). Ikonlar arac cubugundakinin aynisi (resources/icons/
        caddy-undo.svg ve aynasi caddy-redo.svg), yani kullanici ayni sekli
        iki yerde ayni islev icin goruyor. Etiket kaybi telafi edildi:
        ipucunun ILK SATIRI artik dugmenin adi.

        EN SON satirin TAMAMI ikona cevrildi ve "Kayıtlar" geri geldi.
        Kullanicinin sozu: "yeni yerine artı (+), kayıt yerine dolap gibi
        kütüphane gibi bir sembol; tüm butonların boyu aynı olacak; 5
        butondan 6 butona çıkacağız, ona göre butonları küçülteceğiz".
        Olculdu (offscreen, gercek widget'lar, yerlesim kostuktan sonra):

            once (Yeni metin + 2 ikon) : ust satir 356 -> panel asgari 368 px
            simdi (4 ikon dugme)       : ust satir 334 -> panel asgari 346 px

        Yani OGE SAYISI ARTTI ama satir DARALDI: metin dugmesi Qt'nin 80
        px'lik tabanina oturuyordu, ikon dugmesi 28 px. Boy da tek: dort
        dugme de 22 px, model ve efor kutulari da 22 px — satirin tamami
        ayni yukseklikte (bkz. _yuksekligi_esitle, olcut artik KUTULAR
        cunku metin dugmesi kalmadi).

        "Kayıtlar" neden geri geldi: islevi sag tik menusune tasinmisti ve
        kullanici onu BULAMADI. Gorunmeyen bir menu ogesi, olmayan bir
        ozelliktir. Sag tik menusu de kaldirildi (kullanicinin istegi):
        ayni islevin gizli ikinci kapisiydi.
        """
        c = QtWidgets.QHBoxLayout()
        b = _ikon_dugmesi("caddy-yeni.svg", "New")
        b.setToolTip("New chat\n"
                     "Forgets the context and starts fresh.\n"
                     "Does NOT touch the document — only the conversation is reset.")
        b.clicked.connect(self.ctl.yeni_sohbet)
        self.yeni_dugmesi = b
        c.addWidget(b)

        g = _ikon_dugmesi("caddy-undo.svg", "Undo")
        g.setToolTip("Undo\n"
                     "Undoes the last AI change.\n"
                     "Never touches your own manual edits — if yours is on "
                     "top of the stack, it stops and tells you.")
        g.clicked.connect(self.geri_al)
        self.geri_dugmesi = g
        c.addWidget(g)

        i = _ikon_dugmesi("caddy-redo.svg", "Redo")
        i.setToolTip("Redo\n"
                     "Re-applies a change you undid.\n"
                     "Brings your work back if you undid it by mistake.\n"
                     "Disabled until you press Undo.\n"
                     "NOTE: running new code after an undo clears the redo "
                     "history — the panel will tell you.")
        i.clicked.connect(self.ileri_al)
        # Bos yiginda basilabilir bir dugme yalan soyler. Ileri alinacak
        # bir sey olustugunda aciliyor (bkz. _ileri_dugmesini_tazele).
        i.setEnabled(False)
        self.ileri_dugmesi = i
        c.addWidget(i)

        # "Kayıt" GERI GELDI — ama metin degil IKON olarak. Metin dugmesi
        # Qt'nin 80 px tabanina oturdugu icin kaldirilmisti (bkz. yukarisi);
        # ikon dugmesi o tabana bagli degil, dortte biri kadar yer tutuyor.
        # Kullanicinin sozu: "kayıt yerine dolap gibi kütüphane gibi bir
        # sembol". Sag tik menusundeki ayni islev duruyor — kullanici onu
        # BULAMADI, gorunur bir dugme gerekiyordu.
        k = _ikon_dugmesi("caddy-kayitlar.svg", "History")
        k.setToolTip("History\n"
                     "Lists past chats. Pick one and press Resume to "
                     "continue it where it left off, with its context; "
                     "you can also open the log folder from here.")
        k.clicked.connect(self._kayitlari_ac)
        self.kayit_dugmesi = k
        c.addWidget(k)

        c.addStretch(1)
        model = self._model_secici()
        efor = self._efor_secici()
        c.addWidget(model)
        c.addWidget(efor)

        # DORT DUGME DE AYNI BOYDA. Kullanicinin istegi: "tüm butonların
        # boyu aynı olacak". Artik ust satirda metin dugmesi kalmadi, o
        # yuzden olcut KUTULAR: dugmeleri onlara denkleyince satirin tamami
        # tek boy oluyor (olculdu: kutu 22 px). Genislik de burada
        # sabitleniyor — 5 dugmeden 6'ya cikildigi icin daraltildi.
        self.ikon_yuksekligi = _yuksekligi_esitle((b, g, i, k), (model, efor))
        # Sag ustte METIN YOK. Once sayan saat kaldirildi ("2 yerde
        # düşünüyor yazısı var"), sonra geriye kalan "çalışıyor…" da:
        # durumu zaten akistaki ilerleme satiri ve Gonder/Iptal
        # dugmelerinin etkin/pasif hali soyluyor. Ucuncu bir yer gurultu.
        return c

    def _model_secici(self) -> QtWidgets.QComboBox:
        """Hiz/guvenilirlik takasi. Olculmus rakamlar config.MODELLER'de."""
        kutu = QtWidgets.QComboBox()
        simdiki = config.model()
        for i, (deger, kisa, tam, ipucu) in enumerate(config.MODELLER):
            # Kutuda KISA etiket duruyor (yer sebebi, bkz. _arac_cubugu);
            # tam etiket ipucunun ilk satirinda.
            kutu.addItem(kisa, deger)
            kutu.setItemData(i, tam + "\n" + ipucu, QtCore.Qt.ToolTipRole)
            if deger == simdiki:
                kutu.setCurrentIndex(i)
        kutu.setToolTip("Speed / reliability trade-off.\n"
                        "Applies from the next message "
                        "(context is kept).")
        kutu.currentIndexChanged.connect(self._model_degisti)
        self.model_secici = kutu
        return kutu

    def _model_degisti(self, i: int) -> None:
        config.modeli_ayarla(self.model_secici.itemData(i))
        self._ayar_uygula("Model", self.model_secici.currentText())

    def _efor_secici(self) -> QtWidgets.QComboBox:
        """DUSUNME MIKTARI — gecikmenin asil kaynagi.

        Olculdu (2026-08-24, iki gercek oturumun 22 turu): cikti hizi sabit
        (~75 token/sn), baglam gecikmeyi belirlemiyor, ve cikti token'inin
        %91-94'u DUSUNME. Yani beklenen surenin onda dokuzu burada.

        Ayni istem, 3 tekrar: varsayilan ortanca 116.1 sn, `low` 37.0 sn —
        3.1 kat, ucunde de calisan kod. Ayrintisi config.EFORLAR'da.

        Neden MODELDEN AYRI kutu: iki bagimsiz eksen. "Sonnet ile derin
        dusun" da "Opus ile hizli bak" da anlamli istekler; tek listede
        birlestirmek her kombinasyonu ayri satir yapardi.
        """
        kutu = QtWidgets.QComboBox()
        simdiki = config.efor()
        for i, (deger, kisa, tam, ipucu) in enumerate(config.EFORLAR):
            kutu.addItem(kisa, deger)
            kutu.setItemData(i, tam + "\n" + ipucu, QtCore.Qt.ToolTipRole)
            if deger == simdiki:
                kutu.setCurrentIndex(i)
        kutu.setToolTip(
            "How much the model thinks.\n"
            "Measured: 91-94% of the wait is thinking, not writing.\n"
            "Fast = 3.1x quicker (116 s → 37 s).\n"
            "Quality difference NOT measured — what Fast loses is unknown.\n"
            "Applies from the next message (context is kept).")
        kutu.currentIndexChanged.connect(self._efor_degisti)
        self.efor_secici = kutu
        return kutu

    def _efor_degisti(self, i: int) -> None:
        config.eforu_ayarla(self.efor_secici.itemData(i))
        self._ayar_uygula("Thinking", self.efor_secici.currentText())

    def _ayar_uygula(self, ad: str, deger: str) -> None:
        """Surec argumanini etkileyen ayar degisti — GERCEKTEN uygula.

        `--model` ve `--effort` surec baslarken veriliyor ve surec turlar
        boyunca ayakta kaliyor. Bu yuzden model kutusu eskiden "sonraki
        mesajdan itibaren gecerli" diyor ama oturum ortasinda HICBIR SEY
        yapmiyordu. Artik bostaki surec olduruluyor; sonraki tur --resume
        ile yeni argumanlarla basliyor, baglam kaybolmuyor.
        """
        if self.ctl.transport.ayarlar_degisti():
            not_ = f"{ad}: {deger} — applies from the next message " \
                   "(context is kept)."
        else:
            not_ = f"{ad}: {deger} — applies once the current reply finishes " \
                   "(the streaming reply was not interrupted)."
        self.mesaj_ekle("sistem", not_)
        # GUNLUGE de yaziliyor: baslik oturumun BASLANGIC degerini gosterir,
        # ortada degistirilirse logu sonradan inceleyen bunu goremezdi.
        try:
            self.ctl.gunluk.sistem("AYAR DEGISTI — " + not_)
        except Exception:                                        # noqa: BLE001
            pass

    def _konusma_alani(self) -> QtWidgets.QScrollArea:
        self.kaydirma = QtWidgets.QScrollArea()
        self.kaydirma.setWidgetResizable(True)
        # YATAY KAYDIRMA KAPALI. Panel dar bir yan sutun; saga dogru
        # kaydirilan metin okunmuyor, kullanici kaybolyor. Icerideki her sey
        # (SaranEtiket, kod karti) genislige gore SARMAK zorunda — cubugu
        # kapatmak o zorunlulugu somutlastiriyor.
        self.kaydirma.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        ic = QtWidgets.QWidget()
        self.akis = QtWidgets.QVBoxLayout(ic)
        self.akis.setContentsMargins(2, 2, 2, 2)
        self.akis.setSpacing(8)
        self.akis.addStretch(1)
        self.kaydirma.setWidget(ic)
        return self.kaydirma

    def _giris_alani(self) -> QtWidgets.QHBoxLayout:
        c = QtWidgets.QHBoxLayout()
        self.giris = QtWidgets.QPlainTextEdit()
        self.giris.setPlaceholderText(
            "What do you want to build?   (Ctrl+Enter to send)")
        self.giris.setFixedHeight(64)
        self.giris.installEventFilter(self)
        c.addWidget(self.giris, 1)

        dikey = QtWidgets.QVBoxLayout()
        self.btn_gonder = QtWidgets.QPushButton("Send")
        self.btn_gonder.clicked.connect(self.gonder)
        dikey.addWidget(self.btn_gonder)

        self.btn_iptal = QtWidgets.QPushButton("Cancel")
        self.btn_iptal.setEnabled(False)
        self.btn_iptal.clicked.connect(self.ctl.iptal)
        dikey.addWidget(self.btn_iptal)
        c.addLayout(dikey)
        return c

    def _karsilama(self) -> None:
        try:
            s = locate.surum()
        except Exception:
            s = "bulunamadi"
        # KISA. Eskiden burada yedi satır vardı: abonelik, belge koruma,
        # adım adım çalışma, varsayım bildirme. Hepsi doğruydu ama hiçbiri
        # ILK ANDA gerekli değildi — kullanıcının o an ihtiyacı olan tek
        # şey ne yazacağını bilmek. Panel zaten dar; karşılama, sohbetin
        # ilk ekranının yarısını yiyordu.
        self.mesaj_ekle(
            "sistem",
            f"CADdy ready · {config.model()} · claude {s}\n"
            "Describe what you want — e.g. “make a 10 mm cube”.")

    # -- olaylar -----------------------------------------------------------

    def eventFilter(self, nesne, olay):
        if (nesne is self.giris
                and olay.type() == QtCore.QEvent.KeyPress
                and olay.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)
                and olay.modifiers() & QtCore.Qt.ControlModifier):
            self.gonder()
            return True
        return super().eventFilter(nesne, olay)

    def gonder(self) -> None:
        metin = self.giris.toPlainText().strip()
        if not metin:
            return
        self.giris.clear()
        self.ctl.gonder(metin)

    def geri_al(self) -> None:
        # Mantik ConversationController'da: AI de ayni kapidan geciyor ve
        # tehlike ikisinde de ayni — yiginin tepesinde kimin isi var.
        # Eskiden burada kosulsuz `doc.undo()` vardi; dugmenin etiketi "Son
        # AI degisikligini geri al" oldugu halde kullanicinin kendi elle
        # yaptigi son islemi de geri aliyordu.
        oldu, aciklama = self.ctl.geri_al()
        self.mesaj_ekle("sistem",
                        f"Undone: {aciklama}" if oldu else aciklama)
        self._ileri_dugmesini_tazele()

    def _ileri_dugmesini_tazele(self) -> None:
        """Ileri al dugmesi, ileri alinacak bir sey VARSA acik.

        Kullanicinin istegi: "geri al'a basmadan once basilmasin". Bos
        yiginda basilabilir duran bir dugme, olmayan bir yetenek vaat eder.

        UC yerden cagriliyor, cunku yigini degistiren bizim uc yolumuz bu:
        geri alma (doldurur), ileri alma (bosaltir) ve kod calistirma
        (silebilir — bkz. ConversationController.ileri_al'daki olcum).

        SINIRI: kullanici FreeCAD'in kendi Ctrl+Z'sine basarsa bundan
        haberimiz olmaz ve dugme kapali kalir. O yol icin FreeCAD'in kendi
        Ctrl+Y'si zaten calisiyor. Saat ya da DocumentObserver kurmadik:
        biri gereksiz surekli is, digeri bu projede bir kez sizmisti.
        """
        dugme = getattr(self, "ileri_dugmesi", None)
        if dugme is None:
            return
        try:
            dugme.setEnabled(self.ctl._redo_count() > 0)
        except Exception:                                        # noqa: BLE001
            pass

    def ileri_al(self) -> None:
        # Yanlislikla geri alinan is geri getiriliyor. Mantik yine
        # ConversationController'da; gerekcesi ve olculen yigin davranisi
        # ConversationController.ileri_al docstring'inde.
        oldu, aciklama = self.ctl.ileri_al()
        self.mesaj_ekle("sistem",
                        f"Redone: {aciklama}" if oldu else aciklama)
        self._ileri_dugmesini_tazele()

    def _bilgi_satiri(self, metin: str, ipucu: str = "") -> None:
        self.bilgi.setText(metin)
        self.bilgi.setToolTip(ipucu)

    # -- canli akis --------------------------------------------------------

    _ASAMA_ADI = {
        "baglaniyor": "connecting",
        "istek gonderildi": "request sent",
        "dusunuyor": "thinking",
        "yaziyor": "writing",
    }

    def _asama(self, asama: str) -> None:
        self._asama_ad = self._ASAMA_ADI.get(asama, asama)
        self._ilerlemeyi_yaz()

    def _dusunce_olcusu(self, tk: int) -> None:
        self._dusunce_tk = tk
        self._ilerlemeyi_yaz()

    # Bekleyis uzadikca verilen ogut. Esikler OLCUMDEN geliyor: basit bir
    # istek 8-12 sn'de biter, zor bir istek 77-183 sn surer. Yani 30 sn'yi
    # gecen her sey "buyuk istek" demektir ve kullanicinin bunu bilmesi lazim.
    #
    # Neden zamana bakiyoruz da istegin METNINE bakmiyoruz: "bu istek zor mu"
    # diye Turkce metinden tahmin yurutmek kirilgan ve yaniltici olur.
    # Gecen sure ise dogrudan olculen gercek.
    _OGUT = (
        (150, "This request looks too big for one step. Cancel and ask "
              "for one part of it — e.g. fix the position/size first, add "
              "the shape later."),
        (75, "This is taking a while. You can Cancel and split the request; "
             "going step by step is usually faster overall."),
        (30, "Big request — the model is thinking hard, it is not stuck."),
    )

    def _ilerlemeyi_yaz(self) -> None:
        """Saniye + asama + dusunme tokenini AKISA yazar.

        Eskiden ayni metin hem burada hem sag ustteki durum etiketinde
        duruyordu: "düşünüyor · 27 sn · ~500 token" iki yerde birden.
        Kullanicinin sozu: "2 yerde düşünüyor yazısı var, ona gerek yok."
        Ust etiket artik yalnizca DURUMU soyluyor (hazır / çalışıyor /
        iptal ediliyor); sayan saat akistaki tek satirda.

        Akistaki hali secildi cunku ogut satiri (30/75/150 sn esikleri) da
        orada ve ikisi birbirini tamamliyor; ust etikette yalnizca sayilar
        vardi.
        """
        if not self._tiklayici.isActive():
            return
        gecen = int(time.monotonic() - self._t0)
        parca = [self._asama_ad or "working", f"{gecen} s"]
        if self._dusunce_tk:
            # "düşünce" degil "token": olculen sey token sayisi, kullanici
            # da oyle adlandirilmasini istedi.
            parca.append(f"~{_short_num(self._dusunce_tk)} token")
        metin = " · ".join(parca)

        if self._ilerleme is None:
            return

        ogut = "Press Cancel to stop"
        for esik, yazi in self._OGUT:
            if gecen >= esik:
                ogut = yazi
                break
        self._ilerleme.setText(f"⏳ {metin}\n{ogut}")

    def _ilerlemeyi_baslat(self) -> None:
        self._t0 = time.monotonic()
        self._asama_ad = "connecting"
        self._dusunce_tk = 0
        if self._ilerleme is None:
            self._ilerleme = SaranEtiket("")
            self._ilerleme.bicim_ver("#7a8794", italik=True)
            self._ekle(self._ilerleme)
        self._tiklayici.start()
        self._ilerlemeyi_yaz()

    def _ilerlemeyi_durdur(self) -> None:
        self._tiklayici.stop()
        if self._ilerleme is not None:
            self.akis.removeWidget(self._ilerleme)
            self._ilerleme.deleteLater()
            self._ilerleme = None

    def _akis_basladi(self) -> None:
        self._canli_metin = ""
        self._canli = SaranEtiket("")
        self._canli.bicim_ver(_RENK["ai"])
        self._ekle(self._canli)

    def _akis_parcasi(self, parca: str) -> None:
        if self._canli is None:
            self._akis_basladi()
        self._canli_metin += parca
        # Kod bloklarini akarken ham gostermek gurultu; kart zaten gelecek.
        # Yalnizca bloklardan onceki duz metni canli gosteriyoruz.
        gorunen = self._canli_metin.split("```")[0].rstrip()
        if len(self._canli_metin.split("```")) > 1:
            gorunen += "\n… (writing code)"
        self._canli.setText(gorunen)
        self._en_alta()

    def _dusunce_parcasi(self, parca: str) -> None:
        if self._dusunce is None:
            self._dusunce = SaranEtiket("")
            self._dusunce.bicim_ver("#7a8794", italik=True)
            self._ekle(self._dusunce)
        self._dusunce.setText((self._dusunce.text() + parca)[-1500:])
        self._en_alta()

    def _akis_bitti(self) -> None:
        for w in (self._canli, self._dusunce):
            if w is not None:
                self.akis.removeWidget(w)
                w.deleteLater()
        self._canli = None
        self._dusunce = None
        self._canli_metin = ""

    def _klasoru_ac(self) -> None:
        import os
        import subprocess

        klasor = kayitlar.kok()
        klasor.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(klasor))          # noqa: S606  (Windows)
        except Exception:
            subprocess.Popen(["explorer", str(klasor)])

    def _kayitlari_ac(self) -> None:
        """Kutuphane: eski sohbetleri listeler ve secileni SURDURUR.

        Kullanicinin sikayeti: "logdan baslatma yok galiba, sadece logu
        goruyorum, o baglamda FreeCAD'de baslatamiyorum". Eskiden bu dugme
        yalnizca klasoru aciyordu — okunacak bir arsiv, donulecek bir is
        degil. Artik kimlik gunluk basligindan okunuyor ve sonraki tur
        `claude --resume <oturum>` ile gidiyor: gecmisi biz tasimiyoruz,
        CLI kendi oturum dosyasindan yukluyor, yani baglam kaybi yok.
        """
        d = QtWidgets.QDialog(self)
        d.setWindowTitle("History — past chats")
        d.resize(620, 420)
        y = QtWidgets.QVBoxLayout(d)
        y.addWidget(QtWidgets.QLabel(
            "Pick a chat and press <b>Resume</b> to continue where it "
            "left off.<br>The model selection stays as it is; the FreeCAD "
            "document is not touched."))

        liste = QtWidgets.QListWidget(d)
        liste.setAlternatingRowColors(True)
        kayit_listesi = kayitlar.listele()
        for k in kayit_listesi:
            oge = QtWidgets.QListWidgetItem(k.etiket())
            oge.setData(QtCore.Qt.UserRole, k)
            if not k.surdurulebilir:
                # Kimliksiz gunluk okunur ama surdurulemez. Gizlemek yerine
                # gosterip SEBEBINI yazmak, "dugme neden calismadi"dan iyi.
                oge.setToolTip("This log has no session id — "
                               "it can be read but not resumed.")
                oge.setForeground(QtGui.QColor("#888888"))
            liste.addItem(oge)
        if not kayit_listesi:
            liste.addItem(QtWidgets.QListWidgetItem("(no history)"))
        y.addWidget(liste, 1)

        dugmeler = QtWidgets.QDialogButtonBox(d)
        devam = dugmeler.addButton("Resume",
                                   QtWidgets.QDialogButtonBox.AcceptRole)
        dugmeler.addButton("Open folder", QtWidgets.QDialogButtonBox.ActionRole
                           ).clicked.connect(self._klasoru_ac)
        dugmeler.addButton("Close", QtWidgets.QDialogButtonBox.RejectRole
                           ).clicked.connect(d.reject)
        devam.setEnabled(False)
        y.addWidget(dugmeler)

        def _secim_degisti():
            k = liste.currentItem().data(QtCore.Qt.UserRole) \
                if liste.currentItem() else None
            devam.setEnabled(bool(k) and k.surdurulebilir)

        liste.currentItemChanged.connect(lambda *a: _secim_degisti())
        liste.itemDoubleClicked.connect(lambda *a: devam.isEnabled()
                                        and d.accept())
        devam.clicked.connect(d.accept)

        if d.exec_() != QtWidgets.QDialog.Accepted:
            return
        oge = liste.currentItem()
        k = oge.data(QtCore.Qt.UserRole) if oge else None
        if k is None or not k.surdurulebilir:
            return
        self._sohbeti_surdur(k)

    def _sohbeti_surdur(self, kayit) -> None:
        """Secilen kaydi yukler: ekrani tazeler, sonra denetleyiciye devreder."""
        # Ekrani TEMIZLEMIYORUZ: "Yeni sohbet" de temizlemiyor ve akisi
        # silmek, o ana kadar calistirilan kod kartlarini da goturur.
        # Ayrac olarak sistem satiri yeterli.
        self.mesaj_ekle("sistem",
                        "Resumed chat: %s\n(%s)"
                        % (kayit.etiket(), kayit.dosya.name))
        for rol, metin in kayitlar.son_mesajlar(kayit.dosya):
            self.mesaj_ekle("user" if rol == "kullanici" else "ai", metin)
        self.mesaj_ekle("sistem",
                        "The messages above are a reminder read from the log; "
                        "the model itself has the full conversation.")
        self._belgeyi_eslestir(kayit)
        self.ctl.sohbeti_surdur(kayit.oturum, kayit.dosya)

    def _belgeyi_eslestir(self, kayit) -> None:
        """Sohbet geldi — BELGE de gelsin (PLAN S14).

        Kullanicinin sikayeti: "kaldigi yerden basladiginda ve o modelin
        icinde degilsem bile o modelde basliyor... kaldigi model o degil."
        Sohbet dogru, belge yanlisti; kod o an acik olan belgede kosuyor ve
        adlar cakisirsa (Kutu, Govde, Taban) sessizce yanlis modeli
        degistirir.

        DORT DAL, hepsi karar `kayitlar.belge_durumu`'nda:
          acik           -> sessizce o sekmeye gec
          kapali         -> SOR, acma
          kayip          -> uyar, acma
          kaydedilmemis  -> uyar + yedek kopyanin yolunu bilgi olarak ver
          bilinmiyor     -> hicbir sey yazma (eski gunluklerde belge satiri
                            yok; bilmedigimizi uyari diye yazmak gercek
                            uyarilari da degersizlestirir)

        NEDEN OTOMATIK ACMIYORUZ. Belge acmak kullanicinin ekranini
        degistiren, geri alinmasi olmayan bir hareket. Yanlis tahmin
        edersek is bozulmaz ama can sikar; sormanin maliyeti tek tik.
        """
        try:
            durum = kayitlar.belge_durumu(kayit)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"belge durumu okunamadi: {e}")
            return

        d = durum["durum"]
        if d == kayitlar.DURUM_BILINMIYOR:
            return

        if d == kayitlar.DURUM_ACIK:
            doc, hata = kayitlar.belgeyi_ac(durum["yol"])
            self.mesaj_ekle("sistem", durum["mesaj"] if not hata
                            else durum["mesaj"] + "\n" + hata)
            return

        if d in (kayitlar.DURUM_KAYIP, kayitlar.DURUM_KAYDEDILMEMIS):
            self.mesaj_ekle("sistem", durum["mesaj"])
            return

        # DURUM_KAPALI — tek soru soran dal.
        cevap = QtWidgets.QMessageBox.question(
            self, "Chat document",
            durum["mesaj"] + "\n\nOpen the document? "
            "(Your open document stays open; this opens in a new tab.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if cevap != QtWidgets.QMessageBox.Yes:
            self.mesaj_ekle("sistem",
                            "Document not opened — code will run in the "
                            "currently open document.")
            return
        doc, hata = kayitlar.belgeyi_ac(durum["yol"])
        if doc is None:
            self.mesaj_ekle("sistem", hata + "\nCode will run in the currently "
                                             "open document.")
        else:
            self.mesaj_ekle("sistem", "Document opened: %s" % durum["yol"])

    def _durum(self, durum: str) -> None:
        calisiyor = durum == "calisiyor"
        if calisiyor:
            self._ilerlemeyi_baslat()
        else:
            self._ilerlemeyi_durdur()
            if durum == "oluyor":
                # Iptal, kalici sureci de olduruyor — bu bir saniyeden uzun
                # surebiliyor ve o sirada ekranda hicbir sey degismezse
                # "tiklamadi mi" sanilir. Akista tek satir.
                self.mesaj_ekle("sistem", "cancelling…")
        self.btn_gonder.setEnabled(not calisiyor)
        self.btn_iptal.setEnabled(calisiyor)

    def _calisma_sonucu(self, sonuc) -> None:
        # Calisan kod ileri yiginini silmis olabilir (olculdu: degisiklik
        # yapip iptal edilen islem de siliyor). Dugme onu yansitsin.
        self._ileri_dugmesini_tazele()
        if self._bekleyen is not None:
            self._bekleyen.sonucu_goster(sonuc)
            self._bekleyen = None
        # Tekrar korumasi durdurduysa gosterilecek tek sey ACIKLAMA. Ne
        # yedek, ne cikti, ne dogrulama — hicbiri olusmadi, kod kosmadi.
        if getattr(sonuc, "engellendi", False):
            self.mesaj_ekle("sistem", sonuc.hata_izi)
            return
        # Belge basina bir kez dolu gelir: ilk AI degisikliginden onceki kopya.
        if getattr(sonuc, "yedek", ""):
            self.mesaj_ekle("sistem",
                            "Backup saved before the first change:\n"
                            + sonuc.yedek)
        if sonuc.cikti:
            self.mesaj_ekle("sistem", sonuc.cikti)
        for u in sonuc.uyarilar:
            self.mesaj_ekle("sistem", "warning: " + u)
        # FreeCAD'in kendi konsolu (Report view'daki turuncu/kirmizi).
        for u in sonuc.konsol_hata:
            self.mesaj_ekle("sistem", "FreeCAD ERROR: " + u)
        for u in sonuc.konsol_uyari:
            self.mesaj_ekle("sistem", "FreeCAD warning: " + u)
        # Deterministik geometri kontrolu. Panelde YALNIZCA bulgular
        # gosteriliyor; kosan kontrollerin tam listesi modele gidiyor ama
        # kullaniciyi ilgilendiren sey neyin bozuk oldugu. Bulgu yoksa
        # hicbir sey yazilmiyor — her calistirmada "temiz" yazmak gurultu.
        d = getattr(sonuc, "dogrulama", None)
        if d is not None:
            for b in d.bulgular:
                self.mesaj_ekle("sistem", "geometry: " + str(b))
        if not sonuc.basarili:
            self.mesaj_ekle("sistem", sonuc.hata_izi.strip().splitlines()[-1])

    # -- akisa ekleme ------------------------------------------------------

    def _ekle(self, w: QtWidgets.QWidget) -> None:
        self.akis.insertWidget(self.akis.count() - 1, w)
        QtCore.QTimer.singleShot(0, self._en_alta)

    def _en_alta(self) -> None:
        cubuk = self.kaydirma.verticalScrollBar()
        cubuk.setValue(cubuk.maximum())

    def mesaj_ekle(self, role: str, metin: str) -> None:
        e = SaranEtiket(metin)
        e.bicim_ver(_RENK.get(role, "#2d2d2d"), kalin=(role == "user"))
        self._ekle(e)

    def kart_ekle(self, blok) -> None:
        k = CodeCard(blok, self)
        k.calistir_istendi.connect(self._kart_calistir)
        k.hata_gonder_istendi.connect(self.ctl.hatayi_gonder)
        k.sonuc_gonder_istendi.connect(self.ctl.sonucu_gonder)
        self._kartlar.append(k)
        self._ekle(k)

    def _kart_calistir(self, blok) -> None:
        # Hangi kartin sonucu bekledigini tut — sinyal geri geldiginde
        # dogru karta yazilsin.
        for k in self._kartlar:
            if k.blok is blok:
                self._bekleyen = k
                break
        self.ctl.blogu_calistir(blok)


# --------------------------------------------------------------------------

# Yerlesim birkac piksel sapabilir (kenarlik, ayirici). Bunun altindaki
# fark "hedefe ulasildi" sayilir; ustu gercek bir basarisizliktir.
TOLERANS = 8


def _engelleyen_komsular(mw, dock, hedef: int) -> list:
    """Sutunu hedeften genis tutan komsu dock'lari bulur.

    Ayni dock alanindaki, gorunur, yuzmeyen ve bizden farkli dock'lardan
    asgari genisligi hedeften BUYUK olanlar. `(dock, asgari, acik_asgari)`
    uclusu dondurur; `acik_asgari` ic widget'a ELLE konmus minimumWidth
    (0 ise asgari icerikten geliyor demektir).
    """
    engel = []
    try:
        alan = mw.dockWidgetArea(dock)
    except Exception:                                            # noqa: BLE001
        return engel
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d is dock or not d.isVisible() or d.isFloating():
            continue
        try:
            if mw.dockWidgetArea(d) != alan:
                continue
            asgari = d.minimumSizeHint().width()
            if asgari <= hedef:
                continue
            ic = d.widget()
            engel.append((d, asgari, ic.minimumWidth() if ic else 0))
        except Exception:                                        # noqa: BLE001
            continue
    return engel


def _asgari_dokumu(kok, adet: int = 10) -> list:
    """Panelin asgari genisligini KIM belirliyor — satir satir.

    NEDEN VAR (2026-08-28). Bu soruyu iki kez offscreen olctum ve iki kez
    yanildim: `QT_QPA_PLATFORM=offscreen` altinda panelin asgarisi 346 px
    cikiyordu, kullanicinin gercek FreeCAD'inde ayni panel **651 px**.
    Fark yazi tipinden geliyor — offscreen'deki yedek font, FreeCAD'in
    gercek arayuz fontundan cok daha dar. Yani bu olcum SIMULE EDILEMEZ,
    yalnizca calisan FreeCAD'de alinabilir.

    Bu yuzden panel kendi dokumunu Rapor penceresine yaziyor: hedefe
    ulasilamadiginda hangi widget'in ne kadar taban koydugu orada gorunur.
    Tahmin etmek yerine bakiyoruz.
    """
    bulunan = []

    def gez(w, yol):
        for c in w.findChildren(QtWidgets.QWidget, "",
                                QtCore.Qt.FindDirectChildrenOnly):
            if not c.isVisible():
                continue
            ad = c.objectName() or c.__class__.__name__
            try:
                asg = c.minimumSizeHint().width()
                elle = c.minimumWidth()
            except Exception:                                    # noqa: BLE001
                continue
            etiket = ""
            try:
                if isinstance(c, (QtWidgets.QAbstractButton, QtWidgets.QLabel)):
                    etiket = (c.text() or "")[:24]
                elif isinstance(c, QtWidgets.QComboBox):
                    etiket = (c.currentText() or "")[:24]
            except Exception:                                    # noqa: BLE001
                pass
            bulunan.append((max(asg, elle), asg, elle,
                            yol + "/" + ad, etiket))
            gez(c, yol + "/" + ad)

    try:
        gez(kok, "")
    except Exception:                                            # noqa: BLE001
        return []
    bulunan.sort(key=lambda t: -t[0])
    return bulunan[:adet]


def _kenardaki_docklar(mw, dock) -> list:
    """Panelle AYNI kenardaki tum dock'lar — teshis dokumu icin.

    `(ad, genislik, asgari, elle_asgari)` dortlusu dondurur. Filtre YOK:
    hedefi asmayan komsu da yazilir, cunku "hicbiri asmiyor ama panel yine
    genis" bilgisi de bir teshistir — sebebin komsu OLMADIGINI soyler.
    """
    liste = []
    try:
        alan = mw.dockWidgetArea(dock)
    except Exception:                                            # noqa: BLE001
        return liste
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d is dock or not d.isVisible() or d.isFloating():
            continue
        try:
            if mw.dockWidgetArea(d) != alan:
                continue
            ic = d.widget()
            liste.append((d.objectName() or d.windowTitle() or "(adsiz)",
                          d.width(), d.minimumSizeHint().width(),
                          ic.minimumWidth() if ic else 0))
        except Exception:                                        # noqa: BLE001
            continue
    return liste


def _komsulari_gevset(mw, dock, hedef: int) -> list:
    """Engelleyen komsularin ELLE konmus asgari genisligini kaldirir.

    Yalnizca `minimumWidth` acikca konmussa dokunuyoruz: 0 yapinca widget
    kendi icerik asgarisine (minimumSizeHint) duser. Icerikten gelen
    asgariye dokunmuyoruz — olculdu, oradaki tek numara komsuya kalici
    `maximumWidth` koymak olurdu ve o, kullanicinin o paneli bir daha
    genisletmesini engellerdi; bizim panelimiz icin FreeCAD'in kendi
    panelini kafese koymayiz. O halde durust davranip UYARI yaziyoruz.

    Gevsetmeyi geri ALMIYORUZ — olculdu: geri konunca sutun aninda eski
    genisligine sicriyor. Kalici etkisi yalnizca o panelin daha dar
    cekilebilmesi.

    Gevsettiklerinin adlarini dondurur (gunluge yazilsin diye).
    """
    gevsetilen = []
    for d, _asgari, acik in _engelleyen_komsular(mw, dock, hedef):
        if acik <= 0:
            continue
        try:
            d.widget().setMinimumWidth(0)
            gevsetilen.append("%s (%dpx)"
                              % (d.objectName() or d.windowTitle(), acik))
        except Exception:                                        # noqa: BLE001
            continue
    return gevsetilen


def genisligi_ayarla(mw, dock) -> None:
    """Paneli ana pencerenin `PanelYuzde` kadarina getirir.

    Neden gerekli: Qt bir dock'a sizeHint kadar yer verir ve panelin
    sizeHint'i icerigine gore SISER. Olculdu — ust satirdaki uzun dugme
    etiketleri panelin asgari genisligini 888 px'e cikariyordu; panel
    400 px'e zorlandiginda bile 888'de kaliyordu. Once o taban dusuruldu
    (bkz. CaddyPanel._arac_cubugu), bu cagri onun uzerine oturuyor.

    Yalnizca panel ILK OLUSTURULURKEN cagriliyor: sonradan kullanici
    kenarini surukleyip kendi genisligini secebilsin diye. Dock her FreeCAD
    oturumunda bizim kodumuzla yeniden kuruldugu icin varsayilan her acilista
    yeniden gecerli olur.

    KOMSU DOCK'LAR: Qt'de sag alandaki dock'lar TEK BIR SUTUNU paylasir.
    Sutunun genisligi, icindeki dock'larin en buyuk asgarisi kadar dar
    olabilir — yani bizim asgarimiz 346 px olsa bile, yanimizdaki Model
    agaci 650 px asgari istiyorsa bizim dock da 650 px kalir. Olculdu
    (offscreen, gercek widget'lar; scratchpad/panel_genislik2.py):

        kardes asgari 100 px -> hedef 514, gercek 514   ✔
        kardes asgari 300 px -> hedef 514, gercek 514   ✔
        kardes asgari 650 px -> hedef 514, gercek 650   ✘

    Kullanicinin bildirdigi hal tam bu: "651 px, 514 olmasi gerekirken".
    Eski kod bunu SESSIZCE gecirdi, cunku yalnizca KENDI asgarimizi
    kontrol ediyordu (346 < 514, sorun yok sanildi).

    Cozum: hedefe ulasilamadiysa, engelleyen komsunun ic widget'inin
    asgari genisligini gevsetip bir kez daha deniyoruz. Gevsetmeyi GERI
    ALMIYORUZ — olculdu: geri konunca sutun aninda 650 px'e sicriyor.
    Yani gevsetme kalici; yaptigi tek sey kullanicinin (ve bizim) o
    paneli daha dar cekebilmesi. Ne yaptigimizi gunluge yaziyoruz.

    Sonuc GUNLUGE yaziliyor. Hedefe hala ulasilamadiysa bu artik UYARI —
    "ayarladim" deyip gecmek, ayarlamadigini gizlerdi.
    """
    try:
        yuzde = config.panel_yuzde()
        hedef = int(mw.width() * yuzde / 100.0)
        if hedef <= 0:
            return
        asgari = dock.minimumSizeHint().width()
        mw.resizeDocks([dock], [hedef], QtCore.Qt.Horizontal)

        def _rapor():
            g = dock.width()
            if g > hedef + TOLERANS:
                gevsetilen = _komsulari_gevset(mw, dock, hedef)
                if gevsetilen:
                    mw.resizeDocks([dock], [hedef], QtCore.Qt.Horizontal)
                    QtCore.QTimer.singleShot(0, lambda: _son_rapor(gevsetilen))
                    return
                # KOMSU ENGELLEMIYOR ama panel yine genis. Geriye tek
                # aciklama kaliyor: yerlesim BIZDEN SONRA oturdu ve son
                # sozu o soyledi. FreeCAD kapanirken dock duzenini
                # kaydediyor; panel eklendiginde Qt o kayitli genisligi
                # geri yukluyor ve tek seferlik `resizeDocks` cagrimizin
                # ustune yaziyor. Bu yuzden bir kez DAHA deniyoruz.
                #
                # Neden iki deneme: birincisi yerlesimin ilk turundan,
                # ikincisi geri yuklemeden sonra dusuyor. Ucuncusu bugune
                # kadar hicbir olcumde gerekmedi; sinirsiz denemek de
                # kullanici paneli elle genisletirse onunla kavga ederdi.
                if _rapor.kalan > 0:
                    _rapor.kalan -= 1
                    mw.resizeDocks([dock], [hedef], QtCore.Qt.Horizontal)
                    QtCore.QTimer.singleShot(0, _rapor)
                    return
            _son_rapor([])

        _rapor.kalan = 2

        def _son_rapor(gevsetilen):
            g = dock.width()
            pay = (100.0 * g / mw.width()) if mw.width() else 0.0
            # SESSIZ. Bu satir her aciliste Rapor penceresinde piksel dolu
            # bir bildirim olarak cikiyordu ve kullanici "en basta gelen
            # piksel uyarisi gelmesin" dedi. Olcum kaybolmadi: ayikla
            # acikken yine yaziliyor, ve ASIL onemli olan hal (hedefe
            # ulasilamadi) asagida hala UYARI olarak duruyor. Isler
            # yolundayken konusmak, bozuldugunda konusmayi degersizlestirir.
            log.ayik(f"panel genisligi: hedef {hedef}px (%{yuzde}), "
                     f"asgari {asgari}px, gercek {g}px (%{pay:.0f})")
            if gevsetilen:
                log.ayik("panel icin asgarisi gevsetilen komsu dock'lar: "
                         + ", ".join(gevsetilen))
            if g > hedef + TOLERANS:
                # BASARISIZLIKTA TAM DOKUM. Once yalnizca "engelleyen"
                # komsular yazilirdi; hicbiri hedefi asmayinca satir
                # "bilinmiyor" diyordu ve elimizde tesghis kalmiyordu.
                # Artik ayni kenardaki HER dock yaziliyor — genisligi ve
                # asgarisiyle. Sebep hangisiyse orada gorunur.
                log.uyari(f"panel hedefe ulasamadi: hedef {hedef}px, "
                          f"gercek {g}px, kendi asgarimiz {asgari}px, "
                          f"ana pencere {mw.width()}px, "
                          f"{2 - _rapor.kalan} ek deneme yapildi")
                for d, gen, asg, elle in _kenardaki_docklar(mw, dock):
                    log.uyari(f"  ayni kenarda: {d} — genislik {gen}px, "
                              f"asgari {asg}px"
                              + (f" (elle {elle}px)" if elle > 0 else ""))
                # ASIL SORU: taban KENDIMIZDEYSE hangi widget koyuyor.
                # Bu, yalnizca gercek FreeCAD'de dogru cikan bir olcum
                # (bkz. _asgari_dokumu).
                if asgari > hedef:
                    log.uyari("  panelin kendi tabani — en genis ogeler:")
                    for etkin, asg, elle, yol, etiket in _asgari_dokumu(
                            dock.widget()):
                        log.uyari("    %4dpx (hint %d, elle %d) %s%s"
                                  % (etkin, asg, elle, yol,
                                     f"  metin={etiket!r}" if etiket else ""))

        # Yerlesim resizeDocks'tan hemen sonra oturmuyor; gercek genisligi
        # olay dongusu bir tur donunce okuyoruz.
        QtCore.QTimer.singleShot(0, _rapor)
    except Exception as e:
        log.uyari(f"panel genisligi ayarlanamadi: {e}")


def paneli_goster():
    """Dock'u olusturur ya da varsa one getirir."""
    import FreeCADGui as Gui

    mw = Gui.getMainWindow()
    dock = mw.findChild(QtWidgets.QDockWidget, NESNE_ADI)
    yeni = dock is None
    if yeni:
        dock = QtWidgets.QDockWidget(mw)
        dock.setObjectName(NESNE_ADI)
        dock.setWindowTitle("CADdy")
        dock.setWidget(CaddyPanel(dock))
        mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        log.bilgi("panel olusturuldu")
    dock.show()
    dock.raise_()
    if yeni:
        # show()'dan SONRA: gosterilmemis bir dock'ta resizeDocks'un etkisi
        # yerlesime islemiyor.
        genisligi_ayarla(mw, dock)
    return dock
