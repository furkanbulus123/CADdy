"""The CADdy panel — a QDockWidget that sits in FreeCAD's main window.

Why NOT a Task panel (Gui.Control.showDialog): the Task panel occupies a
single slot, clashes with tools like Sketcher/PartDesign and closes itself
when the selection changes. The chat panel has to be persistent.

The pattern was taken from `src/Mod/Help/Help.py:481-503`: look the dock up
by objectName and reuse it if it exists — otherwise a new one piles up on
every call.
"""

from __future__ import annotations

import os
import time

from PySide import QtCore, QtGui, QtWidgets

from .. import config, kayitlar, locate, log
from ..conversation import ConversationController, _kisa_sayi
from .code_card import CodeCard

NESNE_ADI = "CaddyPanel"

# Icon edge of the icon button. The width of a text button was set by Qt's
# 80 px FLOOR (see _arac_cubugu); the icon button is not bound to that floor,
# we set its width ourselves.
#
# 20 -> 18: a fourth button ("History") was added to the top row and the
# user said "we'll make the buttons smaller". The height is NOT set here but
# in _yuksekligi_esitle (matched to the neighbouring boxes); this constant
# only gives the width and the icon's ceiling.
IKON_PX = 18


def _ikon(ad: str):
    """resources/icons/<ad> as a QIcon; None if it cannot be loaded.

    If None is returned the caller falls back to TEXT — a button with neither
    icon nor text would be an unclickable gap (same reasoning as in
    ust_menu._logo).
    """
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    yol = os.path.join(kok, "resources", "icons", ad)
    if not os.path.exists(yol):
        return None
    ikon = QtGui.QIcon(yol)
    return None if ikon.isNull() else ikon


def _ikon_dugmesi(ad: str, yedek_metin: str) -> QtWidgets.QPushButton:
    """A button with an icon; falls back to TEXT without one — the function is never lost.

    Because the label is not visible on an icon button, the caller has to
    write the button's name on the FIRST LINE of the tooltip: if the user
    does not recognise the icon, they cannot learn what it does anywhere
    else.
    """
    d = QtWidgets.QPushButton()
    ikon = _ikon(ad)
    if ikon is None:
        d.setText(yedek_metin)
        log.uyari(f"could not load icon ({ad}) — button fell back to text")
        return d
    d.setIcon(ikon)
    d.setIconSize(QtCore.QSize(IKON_PX, IKON_PX))
    # ONLY THE WIDTH is fixed. The height is left to the caller: fixing it
    # here made the button TALLER than its neighbours (New, the model/effort
    # boxes) and the row looked jagged — that was the user's complaint. The
    # height is matched to the neighbours with _yuksekligi_esitle.
    d.setFixedWidth(IKON_PX + 10)
    # ...BUT setFixedWidth ALONE IS NOT ENOUGH.
    #
    # MEASURED (the user's Report view, 2026-08-28 — not offscreen, see
    # MANTIK 45.4b): the hand-set minimum of all six QPushButtons came out
    # as 106 px, while the call here says 28. The cause is FreeCAD's theme
    # stylesheet: it defines `QPushButton { min-width: ... }` and Qt applies
    # it during polish by calling `setMinimumWidth()` on the widget — i.e.
    # it overwrites OUR line. The top row thus set a floor of 4x106 + boxes
    # = 651 px and the panel would not go down to 40% (512 px) no matter
    # what.
    #
    # Because the rule is set by a stylesheet, only a stylesheet removes it:
    # in the cascade the MORE SPECIFIC one (the widget's own stylesheet)
    # wins. The other theme rules (colour, border) stay in the cascade, only
    # the width is overridden. `min-width` measures the content box, so the
    # padding is trimmed here too, otherwise the theme padding would grow
    # the width back.
    d.setStyleSheet("QPushButton { min-width: %dpx; max-width: %dpx; "
                    "padding-left: 5px; padding-right: 5px; }"
                    % (IKON_PX, IKON_PX))
    return d


def _yuksekligi_esitle(dugmeler, olcutler) -> int:
    """Fits the icon buttons to the height of the NEIGHBOURING widgets; returns the height used.

    Why by measuring: a button's natural height changes with the
    style/theme/font; writing a fixed number (30 px was written before)
    means a jagged row on another machine again.

    The reference USED TO BE the text button: the row had both buttons and
    boxes and Qt's natural heights are not equal (measured, offscreen:
    button 20 px, boxes 22 px); matching the icon button to a box would
    have set it apart from the text button. There is NO text button left
    NOW (all four are icons), so the reference is the BOXES — that way the
    WHOLE row is 22 px, one height. The TALLEST reference is taken.
    """
    h = max([o.sizeHint().height() for o in olcutler] or [0])
    for d in dugmeler:
        d.setFixedHeight(h)
        # The icon has to fit INSIDE the button: if the frame margin is not
        # subtracted, Qt crops/shrinks the icon and the shape gets blurry.
        # 6 px margin across both sides.
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
    """A text box — its content CANNOT OVERFLOW to the RIGHT of the panel. A hard limit.

    Why NOT a QLabel. There are two separate problems and QLabel could only
    solve the first:

      1. Even a QLabel with wrapping on reports `minimumSizeHint().width()`
         based on its longest UNBREAKABLE piece. Measured: 660 pixels for a
         single traceback path (C:\\Users\\...\\executor.py). In a narrow
         side panel this made the QScrollArea open a horizontal scroll bar.
      2. Even with the minimum width zeroed, a QLabel CANNOT BREAK that long
         piece: a path that does not fit on the line overflows to the right
         and becomes invisible. That was exactly the user's second complaint
         — "I can't see the text that slides a bit to the right".

    The only correct fix for the second in Qt is `QTextOption.
    WrapAtWordBoundaryOrAnywhere`: it breaks at a space first, and if that
    does not work, it breaks AT A CHARACTER. QLabel does NOT have this
    option; it needs a widget with a QTextDocument. So this is a QTextEdit
    made to look like a label: frameless, transparent, read-only, both
    scroll bars off, height fixed to the content.

    The wheel event is deliberately NOT SWALLOWED: scrolling stopping when
    the cursor passes over a message while scrolling the chat would be more
    annoying than the problem we solved.
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

    # -- so it behaves like a label ----------------------------------------

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

    # -- height ------------------------------------------------------------

    def _yuksekligi_ayarla(self) -> None:
        """Fixes the height to the actual content AFTER WRAPPING.

        Since the vertical bar is off, a wrong height clips the text at the
        bottom — i.e. we would have solved horizontal overflow and put
        vertical overflow in its place.
        """
        d = self.document()
        d.setTextWidth(max(1, self.viewport().width()))
        h = int(d.size().height())
        self.setFixedHeight(max(h, self.fontMetrics().lineSpacing()) + 2)

    def resizeEvent(self, olay):
        super().resizeEvent(olay)
        self._yuksekligi_ayarla()

    def minimumSizeHint(self) -> QtCore.QSize:
        # Impose no width: the user decides how narrow the panel gets, not
        # the content.
        return QtCore.QSize(0, self.height())

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, self.height())

    def wheelEvent(self, olay):
        # Scrolling is the chat's job; if it were swallowed here, the chat
        # scroll would stop when the cursor reaches a message.
        olay.ignore()


class CaddyPanel(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ctl = ConversationController(self)
        self._kartlar: list[CodeCard] = []
        self._bekleyen: CodeCard | None = None
        # Temporary box shown while the reply streams. It is DELETED when the
        # turn ends and replaced by the properly parsed text + code cards -
        # otherwise the same reply would show up twice.
        self._canli: QtWidgets.QLabel | None = None
        self._canli_metin = ""
        self._dusunce: QtWidgets.QLabel | None = None

        # Progress indicator. A fixed "thinking…" text is not enough:
        # measured, on a hard request the model thinks for 131 s and during
        # that time NOTHING changed on screen — the user rightly thought it
        # was "stuck". A clock counting seconds + the thinking tokens from
        # the CLI's heartbeat is the cheapest way to say "alive".
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

        # WARM-UP. The only potentially expensive work inside `calistir` is
        # the imports `_hazirla` does (`Draft` in the GUI measured: 0.19 s).
        # It is done right after the panel opens, before the user has typed
        # — outside the critical path. singleShot(0): let the window paint
        # first, then warm up.
        QtCore.QTimer.singleShot(0, self._isit)

        # THE RIGHT-CLICK MENU WAS REMOVED. It had a single item ("Open chat
        # logs") and the only reason for that item was that there was no
        # room in the top row. History is now a visible ICON button (see
        # _arac_cubugu), so the menu was a second, HIDDEN door to the same
        # function; the user had already said they could not find it. One
        # visible door instead of two.

    def _isit(self) -> None:
        """Does the expensive imports without the user waiting. Fails silently.

        If it does not warm up nothing breaks: `_hazirla` does the same
        imports itself, only the bill goes to the first Run.
        """
        try:
            from ..execution.executor import isit

            isit()
        except Exception as e:                                   # noqa: BLE001
            log.ayik(f"warm-up failed: {e}")

    def closeEvent(self, olay):
        # The persistent process now stays up between turns; leaving it
        # behind when the panel closes means a claude.exe that outlives
        # FreeCAD.
        try:
            self.ctl.transport.kapat()
        except Exception:
            pass
        # A leaked DocumentObserver fires on EVERY document action of the
        # user and outlives the panel.
        try:
            self.ctl.executor.kapat()
        except Exception:
            pass
        super().closeEvent(olay)

    # -- setup -------------------------------------------------------------

    def _arac_cubugu(self) -> QtWidgets.QHBoxLayout:
        """The top row — LABELS ARE SHORT, the explanation is in the tooltip.

        Why short: this row set the panel's MINIMUM width. Measured
        (offscreen, real widgets): the row's minimum width 876 px, the
        panel's 888 px — and when the panel was forced to 400 px it stayed
        at 888. So the "make the panel narrower" request was PHYSICALLY
        IMPOSSIBLE without shortening the labels; not even `resizeDocks`
        can get below that floor.

        Measured share per label (the labels were Turkish at the time):
            "Undo last AI change"            344 px
            model box ("Opus (good quality)") 270 px
            "New chat"                       140 px
            "History"                        104 px

        No information is lost: each button's full sentence is in
        setToolTip, and the model box's measured speed/quality note was
        already in the tooltip.

        THEN "Redo" was added and the floor went 492 -> 602 px, i.e. ABOVE
        the 40% target (592 px). New measurement (offscreen, real widget):

            "New" 80 · "Undo" 92 · "Redo" 104 · "History" 104
            model box 186 · spacing 24                   -> row 590

        80 px is Qt's button FLOOR — the short labels were all 80 px, so
        shortening below that threshold is not free, it is useless. Room
        was made with "History" -> "Log" (104 -> 80); the undo/redo pair
        kept its full wording, because the bare short words read like
        navigation buttons.

        LAST the effort box was added (amount of thinking — 91-94% of the
        latency, see config.EFORLAR). Deleting the "Log" button ALONE was
        not enough:

            no Log + model(186) + effort(102)   -> panel 600, OVERFLOWS
            no Log + model(102) + effort( 90)   -> panel 504, fits

        So the model box got shorter too: "Opus · good" -> "Opus" (186 ->
        102). The quality note was not lost, it was already in the item's
        tooltip. The "Log" button's function first moved to the right-click
        menu; the user could not find it, so it has now come back as an
        icon button and the menu was removed.

        LATER "Undo"/"Redo" were changed FROM TEXT TO ICONS. The complaint:
        in a narrow panel the right side of the AI reply got clipped.
        Measured (the same offscreen test, real widgets):

            text buttons : top row 492 -> panel minimum 504 px
            icon buttons : top row 356 -> panel minimum 368 px

        A 136 px gain, because the text button sat on Qt's 80 px FLOOR; the
        icon button's width is set by us (30 px, see IKON_PX). The icons
        are the same as on the toolbar (resources/icons/caddy-undo.svg and
        its mirror caddy-redo.svg), so the user sees the same shape for the
        same function in two places. The loss of the label was made up for:
        the FIRST LINE of the tooltip is now the button's name.

        FINALLY the WHOLE row became icons and "History" came back. The
        user's words: "a plus (+) instead of new, a cabinet/library-like
        symbol instead of logs; all buttons the same height; we'll go from
        5 buttons to 6, so make the buttons smaller accordingly". Measured
        (offscreen, real widgets, after layout ran):

            before (New text + 2 icons) : top row 356 -> panel minimum 368 px
            now (4 icon buttons)        : top row 334 -> panel minimum 346 px

        So the NUMBER OF ITEMS WENT UP but the row got NARROWER: the text
        button sat on Qt's 80 px floor, the icon button is 28 px. The height
        is one too: all four buttons are 22 px, the model and effort boxes
        are 22 px as well — the whole row the same height (see
        _yuksekligi_esitle; the reference is now the BOXES because no text
        button is left).

        Why "History" came back: its function had been moved to the
        right-click menu and the user COULD NOT FIND it. An invisible menu
        item is a feature that does not exist. The right-click menu was
        removed too (the user's request): it was a hidden second door to
        the same function.
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
        # A button that can be pressed on an empty stack is lying. It is
        # enabled once there is something to redo (see
        # _ileri_dugmesini_tazele).
        i.setEnabled(False)
        self.ileri_dugmesi = i
        c.addWidget(i)

        # "History" CAME BACK — but as an ICON, not text. The text button had
        # been removed because it sat on Qt's 80 px floor (see above); the
        # icon button is not bound to that floor and takes a quarter of the
        # space. The user's words: "a cabinet/library-like symbol instead of
        # logs". The same function in the right-click menu stays — the user
        # COULD NOT FIND it, a visible button was needed.
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

        # ALL FOUR BUTTONS THE SAME HEIGHT. The user's request: "all buttons
        # the same height". There is no text button left in the top row
        # now, so the reference is the BOXES: matching the buttons to them
        # makes the whole row one height (measured: box 22 px). The width is
        # fixed here too — narrowed because we went from 5 buttons to 6.
        self.ikon_yuksekligi = _yuksekligi_esitle((b, g, i, k), (model, efor))
        # NO TEXT in the top right. First the counting clock was removed
        # ("it says thinking in 2 places"), then the remaining "working…"
        # too: the progress line in the stream and the enabled/disabled
        # state of the Send/Cancel buttons already tell the state. A third
        # place is noise.
        return c

    def _model_secici(self) -> QtWidgets.QComboBox:
        """Speed/reliability trade-off. The measured numbers are in config.MODELLER."""
        kutu = QtWidgets.QComboBox()
        simdiki = config.model()
        for i, (deger, kisa, tam, ipucu) in enumerate(config.MODELLER):
            # The box shows the SHORT label (for space, see _arac_cubugu);
            # the full label is on the first line of the tooltip.
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
        """AMOUNT OF THINKING — the real source of latency.

        Measured (2026-08-24, 22 turns of two real sessions): output speed is
        constant (~75 tokens/s), context does not determine latency, and
        91-94% of output tokens are THINKING. So nine tenths of the expected
        wait is here.

        The same prompt, 3 repeats: default median 116.1 s, `low` 37.0 s —
        3.1x, with working code in all three. Details in config.EFORLAR.

        Why a box SEPARATE FROM THE MODEL: two independent axes. "Think deep
        with Sonnet" and "take a quick look with Opus" are both meaningful
        requests; merging them into one list would make every combination a
        separate row.
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
        """A setting that affects the process arguments changed — ACTUALLY apply it.

        `--model` and `--effort` are given when the process starts, and the
        process stays up across turns. So the model box used to say
        "applies from the next message" but did NOTHING mid-session. Now the
        idle process is killed; the next turn starts with the new arguments
        via --resume, and no context is lost.
        """
        if self.ctl.transport.ayarlar_degisti():
            not_ = f"{ad}: {deger} — applies from the next message " \
                   "(context is kept)."
        else:
            not_ = f"{ad}: {deger} — applies once the current reply finishes " \
                   "(the streaming reply was not interrupted)."
        self.mesaj_ekle("sistem", not_)
        # It is written to the LOG too: the header shows the session's
        # STARTING value, so a change in the middle would be invisible to
        # anyone reviewing the log later.
        try:
            self.ctl.gunluk.sistem("SETTING CHANGED — " + not_)
        except Exception:                                        # noqa: BLE001
            pass

    def _konusma_alani(self) -> QtWidgets.QScrollArea:
        self.kaydirma = QtWidgets.QScrollArea()
        self.kaydirma.setWidgetResizable(True)
        # HORIZONTAL SCROLLING OFF. The panel is a narrow side column; text
        # scrolled to the right is unreadable, the user gets lost. Everything
        # inside (SaranEtiket, code card) HAS TO WRAP to the width — turning
        # the bar off makes that requirement concrete.
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
            s = "not found"
        # SHORT. There used to be seven lines here: subscription, document
        # protection, step-by-step work, stating assumptions. All true, but
        # none of it was needed AT THE FIRST MOMENT — the only thing the user
        # needs then is to know what to type. The panel is narrow already;
        # the welcome was eating half of the chat's first screen.
        self.mesaj_ekle(
            "sistem",
            f"CADdy ready · {config.model()} · claude {s}\n"
            "Describe what you want — e.g. “make a 10 mm cube”.")

    # -- events ------------------------------------------------------------

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
        # The logic is in ConversationController: the AI goes through the
        # same door and the danger is the same in both — whose work is on
        # top of the stack. There used to be an unconditional `doc.undo()`
        # here; even though the button's label was "Undo last AI change", it
        # also undid the user's own last manual operation.
        oldu, aciklama = self.ctl.geri_al()
        self.mesaj_ekle("sistem",
                        f"Undone: {aciklama}" if oldu else aciklama)
        self._ileri_dugmesini_tazele()

    def _ileri_dugmesini_tazele(self) -> None:
        """The Redo button is enabled if there IS something to redo.

        The user's request: "it shouldn't be pressable before Undo is
        pressed". A button that can be pressed on an empty stack promises an
        ability that does not exist.

        It is called from THREE places, because these are our three paths
        that change the stack: undo (fills it), redo (empties it) and running
        code (can clear it — see the measurement in
        ConversationController.ileri_al).

        ITS LIMIT: if the user presses FreeCAD's own Ctrl+Z we don't hear
        about it and the button stays disabled. For that path FreeCAD's own
        Ctrl+Y already works. We did not set up a timer or a
        DocumentObserver: one is needless constant work, the other leaked
        once in this project.
        """
        dugme = getattr(self, "ileri_dugmesi", None)
        if dugme is None:
            return
        try:
            dugme.setEnabled(self.ctl._ileri_sayisi() > 0)
        except Exception:                                        # noqa: BLE001
            pass

    def ileri_al(self) -> None:
        # Work undone by mistake is brought back. The logic is again in
        # ConversationController; the reasoning and the measured stack
        # behaviour are in the ConversationController.ileri_al docstring.
        oldu, aciklama = self.ctl.ileri_al()
        self.mesaj_ekle("sistem",
                        f"Redone: {aciklama}" if oldu else aciklama)
        self._ileri_dugmesini_tazele()

    def _bilgi_satiri(self, metin: str, ipucu: str = "") -> None:
        self.bilgi.setText(metin)
        self.bilgi.setToolTip(ipucu)

    # -- live stream -------------------------------------------------------

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

    # Advice given as the wait gets longer. The thresholds come from
    # MEASUREMENT: a simple request finishes in 8-12 s, a hard one takes
    # 77-183 s. So anything past 30 s means "big request" and the user needs
    # to know that.
    #
    # Why we look at time and not at the request's TEXT: guessing "is this
    # request hard" from free text would be fragile and misleading. The
    # elapsed time is a directly measured fact.
    _OGUT = (
        (150, "This request looks too big for one step. Cancel and ask "
              "for one part of it — e.g. fix the position/size first, add "
              "the shape later."),
        (75, "This is taking a while. You can Cancel and split the request; "
             "going step by step is usually faster overall."),
        (30, "Big request — the model is thinking hard, it is not stuck."),
    )

    def _ilerlemeyi_yaz(self) -> None:
        """Writes seconds + stage + thinking tokens INTO THE STREAM.

        The same text used to be both here and in the status label at the
        top right: "thinking · 27 s · ~500 tokens" in two places at once.
        The user's words: "it says thinking in 2 places, no need for that."
        The top label now only tells the STATE (ready / working /
        cancelling); the counting clock is in the single line in the stream.

        The stream version was picked because the advice line (30/75/150 s
        thresholds) is there too and the two complement each other; the top
        label only had numbers.
        """
        if not self._tiklayici.isActive():
            return
        gecen = int(time.monotonic() - self._t0)
        parca = [self._asama_ad or "working", f"{gecen} s"]
        if self._dusunce_tk:
            # "token", not "thought": what is measured is a token count, and
            # the user asked for it to be called that too.
            parca.append(f"~{_kisa_sayi(self._dusunce_tk)} token")
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
        # Showing code blocks raw while they stream is noise; the card is
        # coming anyway. We only show the plain text before the blocks live.
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
        """The library: lists old chats and RESUMES the chosen one.

        The user's complaint: "I guess there's no starting from the log, I
        only see the log, I can't start it in FreeCAD in that context". This
        button used to only open the folder — an archive to read, not work
        to go back to. Now the id is read from the log header and the next
        turn goes out with `claude --resume <session>`: we don't carry the
        history, the CLI loads it from its own session file, so no context
        is lost.
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
                # A log without an id can be read but not resumed. Showing it
                # and saying WHY is better than hiding it and leaving "why
                # didn't the button work".
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
        """Loads the chosen log: refreshes the screen, then hands over to the controller."""
        # We DO NOT CLEAR the screen: "New chat" does not clear it either,
        # and wiping the stream would also take away the code cards run so
        # far. A system line is enough as a separator.
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
        """The chat came back — the DOCUMENT should come too (PLAN S14).

        The user's complaint: "when it resumes where it left off, even if
        I'm not in that model it starts in that model... the model it left
        off in isn't that one." The chat was right, the document was wrong;
        code runs in whatever document is open at that moment and, if names
        clash (Box, Body, Base), silently changes the wrong model.

        FOUR BRANCHES, all decided in `kayitlar.belge_durumu`:
          open           -> silently switch to that tab
          closed         -> ASK, don't open
          missing        -> warn, don't open
          unsaved        -> warn + give the backup copy's path as info
          unknown        -> write nothing (old logs have no document line;
                            writing what we don't know as a warning would
                            devalue the real warnings too)

        WHY WE DON'T OPEN IT AUTOMATICALLY. Opening a document changes the
        user's screen and cannot be undone. If we guess wrong nothing
        breaks but it is annoying; asking costs one click.
        """
        try:
            durum = kayitlar.belge_durumu(kayit)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not read the document status: {e}")
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

        # DURUM_KAPALI — the one branch that asks a question.
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
                # Cancel kills the persistent process too — that can take
                # more than a second, and if nothing changes on screen in the
                # meantime people think "didn't it click". One line in the
                # stream.
                self.mesaj_ekle("sistem", "cancelling…")
        self.btn_gonder.setEnabled(not calisiyor)
        self.btn_iptal.setEnabled(calisiyor)

    def _calisma_sonucu(self, sonuc) -> None:
        # The code that ran may have cleared the redo stack (measured: an
        # aborted transaction that made a change clears it too). The button
        # should reflect that.
        self._ileri_dugmesini_tazele()
        if self._bekleyen is not None:
            self._bekleyen.sonucu_goster(sonuc)
            self._bekleyen = None
        # If the repeat guard stopped it, the only thing to show is the
        # EXPLANATION. No backup, no output, no verification — none of them
        # happened, the code did not run.
        if getattr(sonuc, "engellendi", False):
            self.mesaj_ekle("sistem", sonuc.hata_izi)
            return
        # Filled once per document: the copy from before the first AI change.
        if getattr(sonuc, "yedek", ""):
            self.mesaj_ekle("sistem",
                            "Backup saved before the first change:\n"
                            + sonuc.yedek)
        if sonuc.cikti:
            self.mesaj_ekle("sistem", sonuc.cikti)
        for u in sonuc.uyarilar:
            self.mesaj_ekle("sistem", "warning: " + u)
        # FreeCAD's own console (orange/red in the Report view).
        for u in sonuc.konsol_hata:
            self.mesaj_ekle("sistem", "FreeCAD ERROR: " + u)
        for u in sonuc.konsol_uyari:
            self.mesaj_ekle("sistem", "FreeCAD warning: " + u)
        # Deterministic geometry check. The panel shows ONLY the findings;
        # the full list of checks that ran goes to the model, but what
        # matters to the user is what is broken. With no findings nothing is
        # written — writing "clean" on every run is noise.
        d = getattr(sonuc, "dogrulama", None)
        if d is not None:
            for b in d.bulgular:
                self.mesaj_ekle("sistem", "geometry: " + str(b))
        if not sonuc.basarili:
            self.mesaj_ekle("sistem", sonuc.hata_izi.strip().splitlines()[-1])

    # -- adding to the stream ----------------------------------------------

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
        # Remember which card is waiting for the result — so it is written
        # to the right card when the signal comes back.
        for k in self._kartlar:
            if k.blok is blok:
                self._bekleyen = k
                break
        self.ctl.blogu_calistir(blok)


# --------------------------------------------------------------------------

# The layout can be off by a few pixels (border, splitter). A difference
# below this counts as "target reached"; above it is a real failure.
TOLERANS = 8


def _engelleyen_komsular(mw, dock, hedef: int) -> list:
    """Finds the neighbouring docks that keep the column wider than the target.

    Docks in the same dock area, visible, not floating and not us, whose
    minimum width is LARGER than the target. Returns `(dock, minimum,
    explicit_minimum)` triples; `explicit_minimum` is the minimumWidth set BY
    HAND on the inner widget (0 means the minimum comes from the content).
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
    """WHO sets the panel's minimum width — line by line.

    WHY IT EXISTS (2026-08-28). I measured this question offscreen twice and
    was wrong twice: under `QT_QPA_PLATFORM=offscreen` the panel's minimum
    came out as 346 px, in the user's real FreeCAD the same panel is
    **651 px**. The difference comes from the font — the fallback font
    offscreen is much narrower than FreeCAD's real UI font. So this
    measurement CANNOT BE SIMULATED, it can only be taken in a running
    FreeCAD.

    That is why the panel writes its own breakdown to the Report view: when
    the target cannot be reached, it shows there which widget sets how much
    of a floor. We look instead of guessing.
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
    """All docks on the SAME edge as the panel — for the diagnostic dump.

    Returns `(name, width, minimum, hand_set_minimum)` quadruples. NO
    filter: a neighbour that does not exceed the target is written too,
    because "none of them exceeds it but the panel is still wide" is also a
    diagnosis — it says the cause is NOT a neighbour.
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
            liste.append((d.objectName() or d.windowTitle() or "(unnamed)",
                          d.width(), d.minimumSizeHint().width(),
                          ic.minimumWidth() if ic else 0))
        except Exception:                                        # noqa: BLE001
            continue
    return liste


def _komsulari_gevset(mw, dock, hedef: int) -> list:
    """Removes the hand-set minimum width of the blocking neighbours.

    We only touch it if `minimumWidth` was set explicitly: setting it to 0
    drops the widget to its own content minimum (minimumSizeHint). We don't
    touch a minimum that comes from content — measured, the only trick
    there would be putting a permanent `maximumWidth` on the neighbour, and
    that would stop the user from ever widening that panel again; we don't
    cage FreeCAD's own panel for the sake of ours. So we behave honestly
    and write a WARNING.

    We DO NOT UNDO the loosening — measured: once it is put back the column
    instantly jumps back to its old width. Its only lasting effect is that
    that panel can be dragged narrower.

    Returns the names of what it loosened (so they get logged).
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
    """Sizes the panel to `PanelYuzde` percent of the main window.

    Why it is needed: Qt gives a dock as much room as its sizeHint, and the
    panel's sizeHint GROWS with its content. Measured — the long button
    labels in the top row pushed the panel's minimum width to 888 px; even
    when the panel was forced to 400 px it stayed at 888. First that floor
    was lowered (see CaddyPanel._arac_cubugu), this call sits on top of it.

    It is only called when the panel is FIRST CREATED: afterwards the user
    can drag the edge and choose their own width. Since the dock is rebuilt
    by our code in every FreeCAD session, the default applies again on
    every start.

    NEIGHBOURING DOCKS: in Qt the docks in the right area share A SINGLE
    COLUMN. The column can only be as narrow as the largest minimum of the
    docks in it — so even if our minimum is 346 px, if the Model tree next
    to us wants a 650 px minimum, our dock stays at 650 px too. Measured
    (offscreen, real widgets; scratchpad/panel_genislik2.py):

        sibling minimum 100 px -> target 514, actual 514   ✔
        sibling minimum 300 px -> target 514, actual 514   ✔
        sibling minimum 650 px -> target 514, actual 650   ✘

    The case the user reported is exactly this: "651 px, when it should be
    514". The old code let it pass SILENTLY, because it only checked OUR
    OWN minimum (346 < 514, assumed no problem).

    Fix: if the target could not be reached, we loosen the minimum width of
    the blocking neighbour's inner widget and try once more. We DO NOT UNDO
    the loosening — measured: once it is put back the column instantly
    jumps to 650 px. So the loosening is permanent; all it does is let the
    user (and us) drag that panel narrower. We log what we did.

    The result is written to the LOG. If the target still could not be
    reached, that is now a WARNING — saying "I set it" and moving on would
    hide that it was not set.
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
                # NO NEIGHBOUR IS BLOCKING but the panel is still wide. Only
                # one explanation is left: the layout settled AFTER US and
                # had the last word. FreeCAD saves the dock layout when it
                # closes; when the panel is added, Qt restores that saved
                # width and overwrites our one-off `resizeDocks` call. So we
                # try ONCE MORE.
                #
                # Why two attempts: the first lands after the layout's first
                # pass, the second after the restore. A third has not been
                # needed in any measurement so far; unlimited attempts would
                # also fight the user if they widened the panel by hand.
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
            # SILENT. This line used to show up in the Report view on every
            # start as a notice full of pixels, and the user said "I don't
            # want the pixel warning at the very start". The measurement was
            # not lost: it is still written when debug is on, and the case
            # that REALLY matters (target not reached) is still a WARNING
            # below. Talking while things are fine devalues talking when
            # they break.
            log.ayik(f"panel width: target {hedef}px ({yuzde}%), "
                     f"minimum {asgari}px, actual {g}px ({pay:.0f}%)")
            if gevsetilen:
                log.ayik("neighbouring docks whose minimum was loosened for "
                         "the panel: " + ", ".join(gevsetilen))
            if g > hedef + TOLERANS:
                # FULL DUMP ON FAILURE. Only the "blocking" neighbours used
                # to be written; when none exceeded the target, the line said
                # "unknown" and we were left with no diagnosis. Now EVERY
                # dock on the same edge is written — with its width and
                # minimum. Whichever is the cause shows up there.
                log.uyari(f"panel did not reach its target: target {hedef}px, "
                          f"actual {g}px, our own minimum {asgari}px, "
                          f"main window {mw.width()}px, "
                          f"{2 - _rapor.kalan} extra attempts made")
                for d, gen, asg, elle in _kenardaki_docklar(mw, dock):
                    log.uyari(f"  on the same edge: {d} — width {gen}px, "
                              f"minimum {asg}px"
                              + (f" (by hand {elle}px)" if elle > 0 else ""))
                # THE REAL QUESTION: if the floor is OUR OWN, which widget
                # sets it. This is a measurement that is only correct in a
                # real FreeCAD (see _asgari_dokumu).
                if asgari > hedef:
                    log.uyari("  the panel's own floor — widest items:")
                    for etkin, asg, elle, yol, etiket in _asgari_dokumu(
                            dock.widget()):
                        log.uyari("    %4dpx (hint %d, by hand %d) %s%s"
                                  % (etkin, asg, elle, yol,
                                     f"  text={etiket!r}" if etiket else ""))

        # The layout does not settle right after resizeDocks; we read the
        # real width once the event loop has gone round once.
        QtCore.QTimer.singleShot(0, _rapor)
    except Exception as e:
        log.uyari(f"could not set the panel width: {e}")


def paneli_goster():
    """Creates the dock, or brings it to the front if it exists."""
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
        log.bilgi("panel created")
    dock.show()
    dock.raise_()
    if yeni:
        # AFTER show(): on a dock that has not been shown, resizeDocks has no
        # effect on the layout.
        genisligi_ayarla(mw, dock)
    return dock
