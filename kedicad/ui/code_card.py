"""A code suggestion card: code + Run/Copy + result.

Why there is no preview (diff): in CAD there is NO meaningful diff that shows
"what will happen" before running — the result is geometry, not text. The
honest primitive is: run it, look in 3D, and if you do not like it, one
Ctrl+Z. The card says exactly that.
"""

from __future__ import annotations

from PySide import QtCore, QtGui, QtWidgets


class SaranSatir(QtWidgets.QLayout):
    """A horizontal row — moves an item that DOES NOT FIT to THE NEXT LINE, never clips it.

    Why (measured, offscreen, real card): in a plain QHBoxLayout the card's
    minimum width was 766 px — more than twice the panel's minimum width
    (368 px). Horizontal scrolling is OFF in the panel, so the excess could
    not be scrolled and was simply CLIPPED: in a narrow panel the "Send
    warnings to AI" button and the status text to its right were invisible.

    There were two bad options: (1) shorten the labels — still not enough
    in a narrow panel, (2) turn on horizontal scrolling — text scrolled
    sideways in a narrow side column is unreadable (same reasoning as in
    dock._konusma_alani). Wrapping is the third way: whatever the width,
    every button's FULL label is visible, only the number of lines grows.

    Same pattern as Qt's FlowLayout example; height depends on width, so
    hasHeightForWidth/heightForWidth are required.
    """

    def __init__(self, parent=None, aralik: int = 6) -> None:
        super().__init__(parent)
        self._ogeler: list[QtWidgets.QLayoutItem] = []
        self.setSpacing(aralik)
        if parent is not None:
            self.setContentsMargins(0, 0, 0, 0)

    # -- QLayout contract
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
        # THE WIDEST SINGLE ITEM — not the whole row. This is exactly where
        # the card's width demand is broken.
        b = QtCore.QSize(0, 0)
        for o in self._ogeler:
            if o.isEmpty():        # a hidden button (btn_hata/btn_sonuc) takes no room
                continue
            b = b.expandedTo(o.minimumSize())
        k = self.contentsMargins()
        return b + QtCore.QSize(k.left() + k.right(), k.top() + k.bottom())

    # -- internal
    def _yerlestir(self, dikdortgen, yalniz_olc: bool) -> int:
        k = self.contentsMargins()
        alan = dikdortgen.adjusted(k.left(), k.top(), -k.right(), -k.bottom())
        x, y, satir_h = alan.x(), alan.y(), 0
        for o in self._ogeler:
            if o.isEmpty():        # a hidden button takes no room, does not wrap
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
    sonuc_gonder_istendi = QtCore.Signal(object)  # CalismaSonucu (with warnings)

    def __init__(self, blok, parent=None) -> None:
        super().__init__(parent)
        self.blok = blok
        self._sonuc = None

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        # The card's HEIGHT DEPENDS ON ITS WIDTH (wrapping button row). Qt's
        # default size policy keeps this OFF and the parent layout ignores
        # the extra lines of the narrow card — the buttons would be clipped
        # at the bottom. That would trade horizontal overflow for vertical
        # overflow; we turn it on explicitly.
        p = self.sizePolicy()
        p.setHeightForWidth(True)
        self.setSizePolicy(p)
        d = QtWidgets.QVBoxLayout(self)
        d.setContentsMargins(8, 6, 8, 6)
        d.setSpacing(5)

        # -- title row
        # The title row WRAPS too: the title text comes from the model, its
        # length is not up to us. If the badge does not fit it drops below.
        ust = SaranSatir(aralik=6)
        baslik = QtWidgets.QLabel(blok.baslik or "FreeCAD Python")
        # The title alone can overflow the row; let it wrap, not clip.
        baslik.setWordWrap(True)
        f = baslik.font()
        f.setBold(True)
        baslik.setFont(f)
        ust.addWidget(baslik)
        # NO addStretch — SaranSatir does not stretch, it lays out from the left.
        if not blok.guvenilir:
            rozet = QtWidgets.QLabel("format not verified")
            rozet.setStyleSheet("color:#a06000;")
            rozet.setToolTip(
                "The model did not use the `freecad-python` tag.\n"
                "The code can still run, but read it first.")
            ust.addWidget(rozet)
        d.addLayout(ust)

        # -- code
        self.kod = QtWidgets.QPlainTextEdit(blok.kod.rstrip())
        self.kod.setReadOnly(False)   # editable: the user can fix it by hand
        self.kod.setFont(QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.FixedFont))
        # WRAPPING ON. It used to be NoWrap and a long line scrolled the card
        # sideways; the panel is a narrow side column, so the user scrolled
        # instead of reading the code. Wrapping spoils the indentation but
        # hides nothing — scrolling hid that the line even existed.
        self.kod.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        # If no word boundary is found, break ANYWHERE. Code has many long
        # unbreakable pieces: file paths, long object names. Breaking only
        # at word boundaries would let them overflow on the right.
        self.kod.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.kod.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._yuksekligi_ayarla()
        d.addWidget(self.kod)

        # -- buttons. A WRAPPING row: in a narrow panel they flow to the next
        # line instead of being clipped (reason and measurement in SaranSatir).
        alt = SaranSatir(aralik=6)
        self.btn_calistir = QtWidgets.QPushButton("Run")
        self.btn_calistir.setDefault(True)
        self.btn_calistir.clicked.connect(self._calistir)
        alt.addWidget(self.btn_calistir)

        self.btn_kopyala = QtWidgets.QPushButton("Copy")
        self.btn_kopyala.clicked.connect(self._kopyala)
        alt.addWidget(self.btn_kopyala)

        self.btn_hata = QtWidgets.QPushButton("Send error to AI")
        self.btn_hata.setVisible(False)
        self.btn_hata.clicked.connect(
            lambda: self.hata_gonder_istendi.emit(self._sonuc))
        alt.addWidget(self.btn_hata)

        # The code ran but the FreeCAD console has orange/red lines: no
        # exception was raised so it looks "successful", but something is
        # off. A separate button shows these to the model.
        self.btn_sonuc = QtWidgets.QPushButton("Send warnings to AI")
        self.btn_sonuc.setVisible(False)
        self.btn_sonuc.clicked.connect(
            lambda: self.sonuc_gonder_istendi.emit(self._sonuc))
        alt.addWidget(self.btn_sonuc)

        # NO addStretch: a wrapping row has no place to stretch, items are
        # laid out from the left. The status text goes next to the last
        # button, or below it if it does not fit.
        self.durum = QtWidgets.QLabel("")
        self.durum.setWordWrap(True)
        alt.addWidget(self.durum)
        d.addLayout(alt)

    # -- internal ----------------------------------------------------------

    _EN_AZ_SATIR = 3
    _EN_COK_SATIR = 22

    def _gorunen_satir(self) -> int:
        """How many lines are visible AFTER wrapping.

        blockCount() is not enough: with wrapping on, one logical line can
        take several lines on screen. Counting only blocks would leave the
        card short and clip the bottom of the code — we would have traded
        horizontal scrolling for vertical clipping.
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
        # When the panel width changes the wrapping changes, and with it the
        # visible line count. Without recomputing the height the code gets
        # clipped at the bottom.
        super().resizeEvent(olay)
        self._yuksekligi_ayarla()

    def _kopyala(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self.kod.toPlainText())
        self.durum.setText("copied")

    def _calistir(self) -> None:
        # ASK FOR CONFIRMATION ON THE SECOND PRESS. The reason is in the
        # logs: in one session the same card ran twice, 5 seconds apart, and
        # produced 22 DUPLICATE OBJECTS (KulakBodySol + KulakBodySol001...);
        # another card ran four times. Running code is cumulative — a second
        # run does not "repeat", it ADDS ON TOP.
        #
        # We do not ask on the first press: asking on every run would slow
        # the main flow. The repeat is what is dangerous, not the first run.
        if self._sonuc is not None:
            c = QtWidgets.QMessageBox.question(
                self, "Run again?",
                "This code has already run once.\n\n"
                "Running it again does NOT delete anything, it adds on top "
                "— you get a second copy of the same geometry.\n\n"
                "Continue?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if c != QtWidgets.QMessageBox.Yes:
                return

        # The user may have edited the code by hand — what is on screen runs.
        self.blok.kod = self.kod.toPlainText()
        self.btn_calistir.setEnabled(False)
        self.durum.setText("running…")
        QtWidgets.QApplication.processEvents()
        self.calistir_istendi.emit(self.blok)

    # -- from outside ------------------------------------------------------

    def sonucu_goster(self, sonuc) -> None:
        self.btn_calistir.setEnabled(True)

        # BLOCKED: the code never ran, the repeat guard stopped it. We do NOT
        # change the card's state — neither "success" nor "error"; what
        # happened is a question. If the user presses again, the executor
        # lets it through this time.
        if getattr(sonuc, "engellendi", False):
            self.durum.setText("blocked — the same code just ran")
            self.durum.setStyleSheet("color:#a06000;")
            self.setToolTip(sonuc.hata_izi)
            return

        self._sonuc = sonuc
        self.btn_calistir.setText("Run again")
        self.durum.setText(sonuc.ozet)
        self.durum.setStyleSheet(
            "color:#0a7a26;" if sonuc.basarili else "color:#b00020;")
        self.btn_hata.setVisible(not sonuc.basarili)

        # If the console has orange/red lines or the code printed something,
        # there is something to pass to the model even on "success". Output
        # now goes AUTOMATICALLY; the button only remains for cases skipped
        # while that path was busy (another turn in progress).
        konsol = list(sonuc.konsol_hata) + list(sonuc.konsol_uyari)
        self.btn_sonuc.setVisible(
            bool(sonuc.basarili and (konsol or sonuc.uyarilar or sonuc.cikti)))
        if konsol:
            self.btn_sonuc.setText(
                f"Send warnings to AI ({len(konsol) + len(sonuc.uyarilar)})")
            self.durum.setStyleSheet("color:#a06000;")   # orange: attention

        if not sonuc.basarili:
            self.setToolTip(sonuc.hata_izi)
        else:
            ipucu = list(sonuc.uyarilar)
            ipucu += ["FreeCAD ERROR: " + u for u in sonuc.konsol_hata]
            ipucu += ["FreeCAD warning: " + u for u in sonuc.konsol_uyari]
            if ipucu:
                self.setToolTip("\n".join(ipucu))
