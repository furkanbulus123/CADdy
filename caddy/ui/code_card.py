"""Bir kod onerisi karti: kod + Calistir/Kopyala + sonuc.

Neden on-izleme (diff) yok: CAD'de calistirmadan once "ne olacagini" gosteren
anlamli bir diff YOKTUR — sonuc geometridir, metin degil. Durust ilkel sudur:
calistir, 3D'de bak, begenmezsen tek Ctrl+Z. Kart bunu soyluyor.
"""

from __future__ import annotations

from PySide import QtCore, QtGui, QtWidgets


class SaranSatir(QtWidgets.QLayout):
    """Yatay satir — SIGMAYAN ogeyi ALT SATIRA atar, kirpmaz.

    Neden gerekli (olculdu, offscreen, gercek kart): duz bir QHBoxLayout'ta
    kartin asgari genisligi 766 px'di — panelin asgari genisliginin (368 px)
    iki katindan fazla. Panelde yatay kaydirma KAPALI oldugu icin fazlasi
    kaydirilamiyor, dogrudan KIRPILIYORDU: dar panelde "Uyarıları AI'a
    gönder" dugmesi ve sagindaki durum yazisi gorunmuyordu.

    Iki kotu secenek vardi: (1) etiketleri kisaltmak — dar panelde yine
    yetmez, (2) yatay kaydirmayi acmak — dar bir yan sutunda saga kaydirilan
    metin okunmuyor (ayni gerekce dock._konusma_alani'nda). Sarma ucuncu yol:
    genislik ne olursa olsun her dugmenin TAM etiketi gorunur, yalnizca satir
    sayisi artar.

    Qt'nin FlowLayout ornegiyle ayni desen; yukseklik genislige bagli
    oldugu icin hasHeightForWidth/heightForWidth sart.
    """

    def __init__(self, parent=None, aralik: int = 6) -> None:
        super().__init__(parent)
        self._ogeler: list[QtWidgets.QLayoutItem] = []
        self.setSpacing(aralik)
        if parent is not None:
            self.setContentsMargins(0, 0, 0, 0)

    # -- QLayout sozlesmesi
    def addItem(self, oge) -> None:
        self._ogeler.append(oge)

    def count(self) -> int:
        return len(self._ogeler)

    def itemAt(self, i):
        return self._ogeler[i] if 0 <= i < len(self._ogeler) else None

    def takeAt(self, i):
        return self._ogeler.pop(i) if 0 <= i < len(self._ogeler) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, genislik: int) -> int:
        return self._yerlestir(QtCore.QRect(0, 0, genislik, 0), True)

    def setGeometry(self, dikdortgen) -> None:
        super().setGeometry(dikdortgen)
        self._yerlestir(dikdortgen, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        # EN GENIS TEK OGE — satirin tamami degil. Kartin genislik dayatmasi
        # tam olarak burada kiriliyor.
        b = QtCore.QSize(0, 0)
        for o in self._ogeler:
            if o.isEmpty():        # gizli dugme (btn_hata/btn_sonuc) yer tutmaz
                continue
            b = b.expandedTo(o.minimumSize())
        k = self.contentsMargins()
        return b + QtCore.QSize(k.left() + k.right(), k.top() + k.bottom())

    # -- ic
    def _yerlestir(self, dikdortgen, yalniz_olc: bool) -> int:
        k = self.contentsMargins()
        alan = dikdortgen.adjusted(k.left(), k.top(), -k.right(), -k.bottom())
        x, y, satir_h = alan.x(), alan.y(), 0
        for o in self._ogeler:
            if o.isEmpty():        # gizli dugme yer tutmaz, satir kaydirmaz
                continue
            b = o.sizeHint()
            if x > alan.x() and x + b.width() > alan.right() + 1:
                x = alan.x()
                y += satir_h + self.spacing()
                satir_h = 0
            if not yalniz_olc:
                o.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), b))
            x += b.width() + self.spacing()
            satir_h = max(satir_h, b.height())
        return y + satir_h - dikdortgen.y() + k.bottom()


class CodeCard(QtWidgets.QFrame):
    calistir_istendi = QtCore.Signal(object)     # blocks.KodBloku
    hata_gonder_istendi = QtCore.Signal(object)  # CalismaSonucu
    sonuc_gonder_istendi = QtCore.Signal(object)  # CalismaSonucu (uyarilarla)

    def __init__(self, blok, parent=None) -> None:
        super().__init__(parent)
        self.blok = blok
        self._sonuc = None

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        # Kartin YUKSEKLIGI GENISLIGE BAGLI (saran dugme satiri). Qt'nin
        # varsayilan boyut politikasi bunu KAPALI tutar ve ust yerlesim
        # kartin dar haldeki fazladan satirlarini hesaba katmaz — dugmeler
        # alttan kirpilirdi. Yatay tasmayi cozup yerine dikey tasma koymak
        # olurdu bu; acikca aciyoruz.
        p = self.sizePolicy()
        p.setHeightForWidth(True)
        self.setSizePolicy(p)
        d = QtWidgets.QVBoxLayout(self)
        d.setContentsMargins(8, 6, 8, 6)
        d.setSpacing(5)

        # -- baslik satiri
        # Baslik satiri da SARAN: baslik metni modelden geliyor, uzunlugu
        # bizim elimizde degil. Rozet sigmazsa alt satira duser.
        ust = SaranSatir(aralik=6)
        baslik = QtWidgets.QLabel(blok.baslik or "FreeCAD Python")
        # Baslik tek basina bile satiri asabilir; sarsin, kirpilmasin.
        baslik.setWordWrap(True)
        f = baslik.font()
        f.setBold(True)
        baslik.setFont(f)
        ust.addWidget(baslik)
        # addStretch YOK — SaranSatir esnemez, soldan dizer.
        if not blok.guvenilir:
            rozet = QtWidgets.QLabel("bicim dogrulanmadi")
            rozet.setStyleSheet("color:#a06000;")
            rozet.setToolTip(
                "Model sozlesmedeki `freecad-python` etiketini kullanmadi.\n"
                "Kod yine de calistirilabilir ama once okumakta fayda var.")
            ust.addWidget(rozet)
        d.addLayout(ust)

        # -- kod
        self.kod = QtWidgets.QPlainTextEdit(blok.kod.rstrip())
        self.kod.setReadOnly(False)   # duzenlenebilir: kullanici elle duzeltebilsin
        self.kod.setFont(QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.FixedFont))
        # SARMA ACIK. Eskiden NoWrap idi ve uzun bir satir karti saga dogru
        # kaydiriyordu; panel dar bir yan sutun oldugu icin kullanici kodu
        # okumak yerine kaydiriyordu. Sarma, girintiyi bozar ama kaybolmaz —
        # kaydirma ise satirin varligini bile gizliyordu.
        self.kod.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        # Kelime siniri bulunamazsa KARAKTERDEN bol. Kodda uzun bolunemez
        # parcalar sik: dosya yollari, uzun nesne adlari. Yalnizca kelime
        # sinirindan bolmek onlari sagdan tasirirdi.
        self.kod.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.kod.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._yuksekligi_ayarla()
        d.addWidget(self.kod)

        # -- dugmeler. SARAN satir: dar panelde alt satira dokulurler,
        # kirpilmazlar (gerekce ve olcum SaranSatir'in docstring'inde).
        alt = SaranSatir(aralik=6)
        self.btn_calistir = QtWidgets.QPushButton("Çalıştır")
        self.btn_calistir.setDefault(True)
        self.btn_calistir.clicked.connect(self._calistir)
        alt.addWidget(self.btn_calistir)

        self.btn_kopyala = QtWidgets.QPushButton("Kopyala")
        self.btn_kopyala.clicked.connect(self._kopyala)
        alt.addWidget(self.btn_kopyala)

        self.btn_hata = QtWidgets.QPushButton("Hatayı AI'a gönder")
        self.btn_hata.setVisible(False)
        self.btn_hata.clicked.connect(
            lambda: self.hata_gonder_istendi.emit(self._sonuc))
        alt.addWidget(self.btn_hata)

        # Kod calisti ama FreeCAD konsolunda turuncu/kirmizi satir var:
        # istisna firlamadigi icin "basarili" gorunuyor, ama bir sey ters.
        # Bunlari modele gostermek icin ayri dugme.
        self.btn_sonuc = QtWidgets.QPushButton("Uyarıları AI'a gönder")
        self.btn_sonuc.setVisible(False)
        self.btn_sonuc.clicked.connect(
            lambda: self.sonuc_gonder_istendi.emit(self._sonuc))
        alt.addWidget(self.btn_sonuc)

        # addStretch YOK: saran satirda esneme yeri yok, ogeler soldan
        # dizilir. Durum yazisi son dugmenin yanina, sigmazsa altina duser.
        self.durum = QtWidgets.QLabel("")
        self.durum.setWordWrap(True)
        alt.addWidget(self.durum)
        d.addLayout(alt)

    # -- ic ---------------------------------------------------------------

    _EN_AZ_SATIR = 3
    _EN_COK_SATIR = 22

    def _gorunen_satir(self) -> int:
        """Sarma SONRASI kac satir gorunuyor.

        blockCount() yetmiyor: sarma acikken bir mantiksal satir ekranda
        birkac satir kaplayabilir. Yalnizca blocklari saymak karti kisa
        birakir ve kodun alti kirpilir — yani yatay kaydirmayi kapatirken
        yerine dikey kirpma koymus olurduk.
        """
        try:
            toplam = 0
            b = self.kod.document().begin()
            while b.isValid():
                duzen = b.layout()
                toplam += max(1, duzen.lineCount() if duzen else 1)
                b = b.next()
            return toplam or self.kod.document().blockCount()
        except Exception:
            return self.kod.document().blockCount()

    def _yuksekligi_ayarla(self) -> None:
        satir = max(self._EN_AZ_SATIR,
                    min(self._EN_COK_SATIR, self._gorunen_satir()))
        yukseklik = int(QtGui.QFontMetrics(self.kod.font()).lineSpacing() * satir + 14)
        self.kod.setFixedHeight(yukseklik)

    def resizeEvent(self, olay):
        # Panel genisligi degisince sarma da degisir, yani gorunen satir
        # sayisi da. Yukseklik yeniden hesaplanmazsa kod alttan kirpilir.
        super().resizeEvent(olay)
        self._yuksekligi_ayarla()

    def _kopyala(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self.kod.toPlainText())
        self.durum.setText("kopyalandı")

    def _calistir(self) -> None:
        # IKINCI BASISTA ONAY SOR. Sebep gunlukte duruyor: 2026-08-19
        # oturumunda ayni kart 13:30:58 ve 13:31:03'te iki kez calisti ve
        # 22 KOPYA NESNE uretti (KulakBodySol + KulakBodySol001...); baska
        # bir kart dort kez kostu. Kod calistirmak birikimli bir islem —
        # ikinci calistirma "tekrarlamaz", USTUNE EKLER.
        #
        # Ilk basista sormuyoruz: her calistirmada onay istemek asil akisi
        # yavaslatir. Tehlikeli olan tekrar, ilk sefer degil.
        if self._sonuc is not None:
            c = QtWidgets.QMessageBox.question(
                self, "Tekrar çalıştır?",
                "Bu kod zaten bir kez çalıştı.\n\n"
                "Tekrar çalıştırmak nesneleri SİLMEZ, üstüne yenilerini "
                "ekler — aynı geometriden ikinci bir kopya oluşur.\n\n"
                "Devam edilsin mi?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if c != QtWidgets.QMessageBox.Yes:
                return

        # Kullanici kodu elle duzenlemis olabilir — ekranda ne varsa o calisir.
        self.blok.kod = self.kod.toPlainText()
        self.btn_calistir.setEnabled(False)
        self.durum.setText("çalışıyor…")
        QtWidgets.QApplication.processEvents()
        self.calistir_istendi.emit(self.blok)

    # -- disaridan ---------------------------------------------------------

    def sonucu_goster(self, sonuc) -> None:
        self.btn_calistir.setEnabled(True)

        # ENGELLENDI: kod hic kosmadi, tekrar korumasi durdurdu. Kartin
        # durumunu DEGISTIRMIYORUZ — ne "basarili" ne "hata"; olan sey bir
        # soru. Kullanici tekrar basarsa executor bu sefer gecirir.
        if getattr(sonuc, "engellendi", False):
            self.durum.setText("engellendi — aynı kod az önce çalıştı")
            self.durum.setStyleSheet("color:#a06000;")
            self.setToolTip(sonuc.hata_izi)
            return

        self._sonuc = sonuc
        self.btn_calistir.setText("Tekrar çalıştır")
        self.durum.setText(sonuc.ozet)
        self.durum.setStyleSheet(
            "color:#0a7a26;" if sonuc.basarili else "color:#b00020;")
        self.btn_hata.setVisible(not sonuc.basarili)

        # Konsolda turuncu/kirmizi varsa ya da kod bir sey yazdirdiysa,
        # "basarili" olsa bile modele iletilecek bir sey var. Cikti artik
        # KENDILIGINDEN gidiyor; dugme yalnizca o yol mesgulken (baska bir
        # tur suruyorken) atlanan durumlar icin duruyor.
        konsol = list(sonuc.konsol_hata) + list(sonuc.konsol_uyari)
        self.btn_sonuc.setVisible(
            bool(sonuc.basarili and (konsol or sonuc.uyarilar or sonuc.cikti)))
        if konsol:
            self.btn_sonuc.setText(
                f"Uyarıları AI'a gönder ({len(konsol) + len(sonuc.uyarilar)})")
            self.durum.setStyleSheet("color:#a06000;")   # turuncu: dikkat

        if not sonuc.basarili:
            self.setToolTip(sonuc.hata_izi)
        else:
            ipucu = list(sonuc.uyarilar)
            ipucu += ["FreeCAD HATA: " + u for u in sonuc.konsol_hata]
            ipucu += ["FreeCAD uyarı: " + u for u in sonuc.konsol_uyari]
            if ipucu:
                self.setToolTip("\n".join(ipucu))
