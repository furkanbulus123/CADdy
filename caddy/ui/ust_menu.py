"""CADdy'yi FreeCAD'in ust seridine KALICI olarak yerlestirir.

Sorun: CADdy bir *workbench*, yani ustteki acilir listeden secilmedigi
surece ortada yok. Kullanici "direkt ust tarafta bir sekme olarak ekleme
sansimiz var mi" diye sordu.

Workbench'in kendi appendToolbar/appendMenu'su bunu COZMEZ: onlar yalnizca
o workbench aktifken gorunur.

NE GORUNUYOR — kullanici istegiyle daraltildi
---------------------------------------------
Ilk surumde ust seritte bir "CADdy" MENUSU (metin) ve iki komutlu bir arac
cubugu vardi. Kullanici: *"freecad'de CADdy kotu gozukuyor, sadece logosu
gozuksun"* ve *"AI ile geri al falan gozukmesin."*

Bu yuzden ust seritte artik TEK BIR SEY var: paneli acan logo dugmesi.
  - Menu cubugu girdisi KALDIRILDI (metin oradan geliyordu)
  - "Son AI degisikligini geri al" ust seritten CIKARILDI

Ikisi de KAYBOLMADI: workbench'in kendi menusu ve arac cubugu (InitGui'deki
Initialize) ikisini de gosteriyor. Ust serit yalnizca "her yerden erisilen
kisayol"; oraya her komutu koymak kullanicinin sikayet ettigi kalabaligi
yapiyordu.

ASIL TUZAK — ilk denemede menu HIC GORUNMEDI, sebebi bu:
FreeCAD'in menu cubugu workbench sistemi tarafindan YONETILIYOR. Her
workbench degisiminde MenuManager menu cubugunu yeniden kuruyor ve
disaridan eklenmis menuleri SILIYOR. Yani bir kez eklemek yetmez; her
workbench degisiminde YENIDEN eklemek gerekiyor. Arac cubugu MenuManager'a
tabi degil, yani daha dayanikli — ama tazeleme yine de duruyor, cunku
cubugun kendisi de kullanici tarafindan gizlenebiliyor.

Uc katmanli savunma:
  1. workbenchActivated sinyaline baglan (varsa) -> her gecişte tazele
  2. Periyodik tazeleme (ilk dakika, 3 sn arayla) -> acilis yarisini ve
     sinyalin olmadigi surumleri karsilar
  3. objectName ile varlik kontrolu -> tekrar tekrar eklemeyi onler

QAction'IN YERI: PySide6'da QAction QtWidgets'tan QtGui'ye tasindi.
FreeCAD'in PySide shim'i surumden surume ikisinden birini veriyor, o
yuzden ikisi de deneniyor.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtGui, QtWidgets

from .. import log

ARAC_CUBUGU_ADI = "CADdy"
_ARAC_NESNE = "CADdyUstAracCubugu"

# Ust seritte YALNIZCA paneli acan komut. Bkz. modul basligi.
_KOMUT_ADLARI = ("CADdy_ShowPanel",)

_ILK_DENEME_MS = 1200
_EN_FAZLA_DENEME = 10
_TAZELEME_MS = 3000
_TAZELEME_SAYISI = 20        # ~1 dakika

# QAction hangi modulde? PySide6 = QtGui, PySide2 = QtWidgets.
QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction")

_durum = {"kuruldu": False, "tazeleme": 0, "zamanlayici": None}


def yerlestir() -> None:
    """Logo dugmesini ust serite ekler ve kalici kalmasini saglar."""
    _dene(0)


# --------------------------------------------------------------------------
# kurulum
# --------------------------------------------------------------------------

def _ana_pencere():
    try:
        import FreeCADGui as Gui
        return Gui.getMainWindow()
    except Exception:
        return None


def _logo():
    """CADdy logosu QIcon olarak; yuklenemezse None.

    None donerse cagiran taraf METNE geri doner — ikonsuz ve metinsiz bir
    dugme tiklanamaz bir bosluk olurdu.
    """
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    yol = os.path.join(kok, "resources", "icons", "caddy.svg")
    if not os.path.exists(yol):
        return None
    ikon = QtGui.QIcon(yol)
    return None if ikon.isNull() else ikon


def _dene(sayac: int) -> None:
    mw = _ana_pencere()
    if mw is None:
        if sayac < _EN_FAZLA_DENEME:
            QtCore.QTimer.singleShot(_ILK_DENEME_MS,
                                     lambda: _dene(sayac + 1))
        else:
            log.uyari("ana pencere bulunamadi, ust serit eklenmedi")
        return

    _tazele()

    if not _durum["kuruldu"]:
        _durum["kuruldu"] = True
        _sinyale_bagla(mw)
        _tazelemeyi_baslat()
        log.bilgi("ust serit kuruldu (logo dugmesi)")


def _sinyale_bagla(mw) -> None:
    """Workbench degisiminde tazele.

    Sinyalin adi surumden surume degisebildigi icin birkac aday deneniyor.
    """
    for ad in ("workbenchActivated", "workbenchActivated_"):
        sinyal = getattr(mw, ad, None)
        if sinyal is None:
            continue
        try:
            sinyal.connect(lambda *a: _tazele())
            log.ayik(f"ust serit: {ad} sinyaline baglandi")
            return
        except Exception:
            continue
    log.ayik("ust serit: workbench sinyali yok, periyodik tazeleme kullanilacak")


def _tazelemeyi_baslat() -> None:
    """Ilk dakika boyunca periyodik tazeleme.

    Sinyal yoksa ya da acilis sirasi tutmadiysa emniyet kemeri. Suresiz
    calistirmiyoruz: bir dakika sonra her sey oturmus olur, sonsuz timer
    bosuna is yapar.
    """
    z = QtCore.QTimer()
    z.setInterval(_TAZELEME_MS)

    def tik():
        _durum["tazeleme"] += 1
        _tazele()
        if _durum["tazeleme"] >= _TAZELEME_SAYISI:
            z.stop()

    z.timeout.connect(tik)
    z.start()
    _durum["zamanlayici"] = z      # referans tutulmazsa GC toplar


def _tazele() -> None:
    """Arac cubugu yoksa ekler; varsa dokunmaz."""
    mw = _ana_pencere()
    if mw is None:
        return
    try:
        _eski_menuyu_kaldir(mw)
    except Exception as e:
        log.ayik(f"eski menu kaldirilamadi: {e}")
    try:
        _arac_cubugunu_ekle(mw)
    except Exception as e:
        log.uyari(f"ust serit eklenemedi: {e}")


# --------------------------------------------------------------------------
# eylemler
# --------------------------------------------------------------------------

def _eylemler(ebeveyn) -> list:
    """Cubuga girecek eylemler.

    FreeCAD komutlarinin QAction'i ancak bir menuye eklendiginde olusuyor ve
    ona ulasmanin tasinabilir bir API'si yok; ana penceredeki QAction'lar
    objectName ile taraniyor (Gui.addCommand nesne adini komut adiyla ayni
    koyuyor). Bulunamazsa komutu Gui.runCommand ile calistiran kendi
    eylemimizi kuruyoruz - cubuk bos kalmasin.
    """
    import FreeCADGui as Gui

    mw = Gui.getMainWindow()
    mevcut = {}
    if mw is not None:
        for e in mw.findChildren(QAction):
            ad = e.objectName()
            if ad in _KOMUT_ADLARI:
                mevcut.setdefault(ad, e)

    logo = _logo()
    cikti = []
    for ad in _KOMUT_ADLARI:
        e = mevcut.get(ad)
        if e is None:
            e = _kendi_eylemimiz(ad, ebeveyn, logo)
        elif logo is not None and e.icon().isNull():
            # Komut kayitli ama ikonsuz gelmis: ikon-only cubukta gorunmez
            # bir dugme olurdu.
            e.setIcon(logo)
        cikti.append(e)
    return cikti


def _kendi_eylemimiz(komut_adi: str, ebeveyn, logo):
    baslik = {
        "CADdy_ShowPanel": "CADdy panelini aç",
    }.get(komut_adi, komut_adi)

    e = QAction(baslik, ebeveyn)
    e.setObjectName(komut_adi + "_yedek")
    if logo is not None:
        e.setIcon(logo)
    if komut_adi == "CADdy_ShowPanel":
        e.setShortcut("Ctrl+Shift+A")
    # Metin gizlense de fare ustune gelince ne oldugu anlasilsin.
    e.setToolTip(baslik)

    def calistir():
        try:
            import FreeCADGui as Gui
            Gui.runCommand(komut_adi, 0)
        except Exception:
            # Komut kayitli degilse paneli dogrudan ac.
            if komut_adi == "CADdy_ShowPanel":
                from .dock import paneli_goster
                paneli_goster()

    e.triggered.connect(calistir)
    return e


# --------------------------------------------------------------------------
# arac cubugu
# --------------------------------------------------------------------------

def _arac_cubugunu_ekle(mw) -> None:
    for c in mw.findChildren(QtWidgets.QToolBar):
        if c.objectName() == _ARAC_NESNE:
            if not c.isVisible():
                c.setVisible(True)
            return

    cubuk = QtWidgets.QToolBar(ARAC_CUBUGU_ADI, mw)
    cubuk.setObjectName(_ARAC_NESNE)

    eylemler = _eylemler(cubuk)

    # SADECE LOGO. Kullanici istegi (bkz. modul basligi). Metin gizlenince
    # dugmenin tek anlatimi ikon oluyor, o yuzden _eylemler() ikonsuz bir
    # eylemi asla dondurmuyor.
    cubuk.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)

    for e in eylemler:
        cubuk.addAction(e)
    mw.addToolBar(QtCore.Qt.TopToolBarArea, cubuk)
    cubuk.setVisible(True)


# --------------------------------------------------------------------------
# temizlik
# --------------------------------------------------------------------------

def _eski_menuyu_kaldir(mw) -> None:
    """Onceki surumun biraktigi "CADdy" MENUSUNU siler.

    Neden gerekli: menu cubugu girdisi FreeCAD'in user.cfg'sinde degil,
    calisma zamaninda kuruluyor — yani yeni surum onu eklemeyi birakinca
    kendiliginden kayboluyor. AMA ayni oturumda eski surum calistiysa menu
    ekranda durmaya devam eder. Bu, "eski surumden yeni surume gecerken
    ekranda iki CADdy" durumunu onluyor.
    """
    try:
        cubuk = mw.menuBar()
    except Exception:
        return
    for eylem in list(cubuk.actions()):
        m = eylem.menu()
        if m is not None and m.objectName() == "CADdyUstMenu":
            cubuk.removeAction(eylem)
            log.ayik("eski ust menu kaldirildi")
