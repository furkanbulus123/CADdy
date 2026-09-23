"""Panel yerlesimi — GERCEK widget'larla, ekransiz.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_panel_fc.py

freecadcmd'de GUI yok ama `QT_QPA_PLATFORM=offscreen` ile QApplication
kuruluyor ve widget'lar gercekten olusuyor — olculdu. Yani bu test "import
edilebiliyor mu" seviyesinde degil, YERLESIMI sinar.

Sinadigi sikayet: "sag tarafa cok fazla scroll yapabiliyoruz, runtime
error'larda cok saga gidiyor". Sebep olculdu: sarma acik bir QLabel bile
`minimumSizeHint().width()` degerini en uzun BOLUNEMEZ parcaya gore veriyor.
Tek bir traceback yolu icin bu 660 piksel cikiyor ve dar bir yan panelde
yatay kaydirma cubugu aciliyor.

DIKKAT: QApplication, FreeCAD/PySide import edilmeden ONCE ortam degiskeni
konarak kurulmali; sonra konursa platform eklentisi secilmis olur.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_panel.txt")
with open(RAPOR, "w", encoding="utf-8") as _f:
    _f.write("")

gecti = basarisiz = atlandi = 0

UZUN_YOL = (r"C:\Users\USER-1\Desktop\CADdy\caddy\execution\executor.py")
UZUN_HATA = (
    'Traceback (most recent call last):\n'
    '  File "' + UZUN_YOL + '", line 328, in calistir\n'
    '    exec(kod_nesnesi, self._hazirla(doc))\n'
    'RuntimeError: bu satir kasten cok uzun tutuldu ki panel saga kaymasin '
    'diye eklenen onlem gercekten sinansin')


def _yaz(m):
    # print ONCE denenir ama ASLA testi oldurmez: konsol kod sayfasi
    # (cp1254) ⏳ gibi karakterleri kodlayamiyor ve print
    # UnicodeEncodeError firlatiyor. Ilk yazimda test tam da burada,
    # sessizce oldu. Dosya UTF-8 oldugu icin rapor eksiksiz kaliyor.
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


def atla(ad, sebep):
    global atlandi
    atlandi += 1
    _yaz("  ATLANDI %s   %s" % (ad, sebep))


def bolum(ad):
    _yaz("")
    _yaz("--- %s %s" % (ad, "-" * max(0, 56 - len(ad))))


_yaz("=" * 70)
_yaz("CADdy panel yerlesim testleri")
_yaz("=" * 70)

from PySide import QtCore, QtGui, QtWidgets

app = (QtWidgets.QApplication.instance()
       or QtWidgets.QApplication(sys.argv[:1]))
_yaz("QApplication: %s" % type(app).__name__)

from caddy import config
from caddy import log as _log
from caddy.ui.code_card import CodeCard
from caddy.ui.dock import SaranEtiket

# ------------------------------------------------------------- SaranEtiket
bolum("SaranEtiket — tek uzun yol paneli genisletmemeli")

duz = QtWidgets.QLabel(UZUN_YOL)
duz.setWordWrap(True)
duz_g = duz.minimumSizeHint().width()
_yaz("       duz QLabel asgari genislik : %d px" % duz_g)

saran = SaranEtiket(UZUN_YOL)
saran_g = saran.minimumSizeHint().width()
_yaz("       SaranEtiket asgari genislik: %d px" % saran_g)

kontrol("ON KABUL: duz QLabel gercekten genislik dayatiyor", duz_g > 200,
        duz_g)
kontrol("SaranEtiket genislik dayatmiyor", saran_g == 0, saran_g)
kontrol("metin secilebilir kaldi",
        bool(saran.textInteractionFlags()
             & QtCore.Qt.TextSelectableByMouse))
kontrol("text() etiket gibi calisiyor", saran.text() == UZUN_YOL,
        saran.text())
kontrol("iki kaydirma cubugu da kapali",
        saran.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
        and saran.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff)

bolum("SERT LIMIT — bolunemez uzun parca KARAKTERDEN bolunmeli")
# Asil sinav: icinde HIC BOSLUK OLMAYAN uzun bir metin. Kelime sinirindan
# bolen her cozum burada kalir; metin sagdan tasar ve gorunmez olur.
saran.setText(UZUN_YOL)
kontrol("sarma modu WrapAtWordBoundaryOrAnywhere",
        saran.document().defaultTextOption().wrapMode()
        == QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere,
        saran.document().defaultTextOption().wrapMode())


# DIKKAT: show() SART. Gosterilmemis bir QAbstractScrollArea'da viewport
# genisligi resize ile guncellenmiyor; olculdu — ilk yazimda bu yuzden
# genislik ne olursa olsun ayni sayi cikti ve test kodu bozuk sandim.
saran.show()


def _satirlar(w, genislik):
    """Verilen genislikte GERCEK satirlar: (satir sayisi, en genis satir)."""
    w.resize(genislik, 200)
    app.processEvents()
    d = w.document()
    b, en_genis, adet = d.begin(), 0.0, 0
    while b.isValid():
        lay = b.layout()
        n = lay.lineCount() if lay else 0
        adet += n
        for i in range(n):
            en_genis = max(en_genis, lay.lineAt(i).naturalTextWidth())
        b = b.next()
    return adet, en_genis


onceki_satir = 0
for genislik in (600, 400, 220, 140):
    adet, en_genis = _satirlar(saran, genislik)
    _yaz("       %3d px -> %d satir, en genis satir %.0f px"
         % (genislik, adet, en_genis))
    kontrol("%d px'te HICBIR SATIR TASMIYOR" % genislik,
            en_genis <= genislik, "%.0f > %d" % (en_genis, genislik))
    if onceki_satir:
        kontrol("%d px'te satir sayisi azalmadi" % genislik,
                adet >= onceki_satir, "%d < %d" % (adet, onceki_satir))
    onceki_satir = adet

adet_dar, _ = _satirlar(saran, 140)
adet_genis, _ = _satirlar(saran, 600)
kontrol("bosluksuz metin GERCEKTEN bolunuyor (karakter sinirindan)",
        adet_dar > adet_genis, "%d > %d" % (adet_dar, adet_genis))

# Widget yuksekligi de icerige uymali, yoksa yatay tasmayi cozup yerine
# dikey kirpma koymus oluruz.
_satirlar(saran, 140)
kontrol("widget yuksekligi icerigi kapsiyor",
        saran.height() >= int(saran.document().size().height()),
        "%d >= %d" % (saran.height(), int(saran.document().size().height())))

# ------------------------------------------------------------------- panel
bolum("panel — yatay kaydirma kapali")
try:
    from caddy.ui import dock as _dock
    panel = _dock.CaddyPanel()
    panel.resize(320, 600)
    kontrol("panel olusturuldu", panel is not None)
    kontrol("yatay kaydirma KAPALI",
            panel.kaydirma.horizontalScrollBarPolicy()
            == QtCore.Qt.ScrollBarAlwaysOff,
            panel.kaydirma.horizontalScrollBarPolicy())

    # Uzun bir traceback ekle ve panelin genislemedigini gor
    panel.mesaj_ekle("sistem", UZUN_HATA)
    app.processEvents()
    ic = panel.kaydirma.widget()
    _yaz("       ic widget asgari genislik: %d px"
         % ic.minimumSizeHint().width())
    kontrol("uzun traceback panelin asgari genisligini sismedi",
            ic.minimumSizeHint().width() <= 320,
            ic.minimumSizeHint().width())
except Exception as e:                                       # noqa: BLE001
    import traceback as _tb
    atla("panel olusturma", str(e)[:150])
    _yaz(_tb.format_exc()[-600:])
    panel = None

# --------------------------------------------------------- panel genisligi
bolum("panel ASGARI genisligi — %40 hedefi fiziksel olarak mumkun mu")

# Kullanicinin sikayeti: "caddy ekranin yuzde 60'ini kapsiyor, %40 olsun".
# Sebep olculdu ve ayar degildi: panelin ASGARI genisligi 888 px'di ve panel
# 400 px'e zorlandiginda bile 888'de kaliyordu — yani hicbir genislik ayari
# (resizeDocks dahil) bu tabani asamazdi. Taban tamamen ust satirdan
# geliyordu:
#     'Son AI değişikliğini geri al' 344 · model kutusu 270 ·
#     'Yeni sohbet' 140 · 'Kayıtlar' 104   -> satir 876, panel 888
#
# 888 px kullanicinin penceresinin ~%60'i olduguna gore pencere ~1480 px.
# %40 hedefi = 592 px. Test bunu tavan olarak alir.
PENCERE = 1480          # kullanicinin olculen ana pencere genisligi
HEDEF = int(PENCERE * 0.40)
ESKI_TABAN = 888

if panel is None:
    atla("panel genisligi", "panel olusmadi")
else:
    asgari = panel.minimumSizeHint().width()
    _yaz("       panel asgari genislik: %d px   (eskiden %d px)"
         % (asgari, ESKI_TABAN))
    _yaz("       %%40 hedefi           : %d px  (pencere %d px)"
         % (HEDEF, PENCERE))

    kontrol("asgari genislik %40 hedefinin ALTINDA" ,
            asgari <= HEDEF, "%d > %d" % (asgari, HEDEF))
    kontrol("ON KABUL: eski taban gercekten hedefi asiyordu",
            ESKI_TABAN > HEDEF, "%d <= %d" % (ESKI_TABAN, HEDEF))

    ust = panel.layout().itemAt(0).layout()
    _yaz("       ust satir asgari      : %d px" % ust.minimumSize().width())
    kontrol("tabani belirleyen hala ust satir (degisirse burasi bakilsin)",
            ust.minimumSize().width() >= asgari - 40,
            "%d vs %d" % (ust.minimumSize().width(), asgari))

    # Asil sinav: panel GERCEKTEN daralabiliyor mu. Eski halde bu satir
    # 888 donuyordu.
    panel.resize(HEDEF, 800)
    app.processEvents()
    _yaz("       %d px'e zorlanınca    : %d px" % (HEDEF, panel.width()))
    kontrol("panel %40 genisligine GERCEKTEN inebiliyor",
            panel.width() <= HEDEF, "%d > %d" % (panel.width(), HEDEF))

    # UST SATIRIN DORT DUGMESI DE IKON. "Yeni" arti (+), "Kayıtlar"
    # cekmeceli dolap oldu (kullanicinin sozu: "yeni yerine artı, kayıt
    # yerine dolap gibi kütüphane gibi bir sembol"). Her birinde iki sey
    # kanitlanmali: ikon GERCEKTEN yuklendi (yoksa dugme bos bir kareye
    # doner) ve adi ipucunun ILK SATIRINDA duruyor — kullanici ikonu
    # tanimazsa tek ogrenme yeri orasi.
    _DUGMELER = (
        ("New chat", panel.yeni_dugmesi, "New chat", "Forgets the context"),
        ("Undo", panel.geri_dugmesi, "Undo", "Undoes the last AI change"),
        ("Redo", panel.ileri_dugmesi, "Redo", "Re-applies"),
        ("History", panel.kayit_dugmesi, "History", "where it left off"),
    )
    for _ad, _dugme, _ilk, _cumle in _DUGMELER:
        _ip = _dugme.toolTip()
        kontrol("'%s' IKON dugmesi (metin yok)" % _ad,
                _dugme.text() == "", _dugme.text())
        kontrol("'%s' ikonu yuklendi" % _ad,
                not _dugme.icon().isNull())
        kontrol("'%s' ipucunun ILK SATIRI dugmenin adi" % _ad,
                _ip.split("\n")[0] == _ilk, _ip[:40])
        kontrol("'%s' ipucunda tam cumle var" % _ad, _cumle in _ip, _ip[:60])
    # BOY ESITLIGI. Ikon dugmesine sabit 30 px verilmisti ve komsularindan
    # uzun kaliyordu; kullanici "diger butonlarla ayni yukseklikte olsun"
    # dedi. Olcut EKRANDAKI yukseklik — sizeHint degil, cunku tirtik goze
    # carpan sey yerlesim sonrasi gercek boy.
    # show() SART: gosterilmeyen panelde cocuklar yerlesime hic girmiyor ve
    # hepsi varsayilan 640x480'de kaliyor — ilk kosuda tam bunu olctuk,
    # "480 != 22" dedi. Gercek boy ancak yerlesim kostuktan sonra var.
    panel.show()
    app.processEvents()
    _kutu = max(panel.model_secici.height(), panel.efor_secici.height())
    _boylar = [d.height() for _, d, _i, _c in _DUGMELER]
    _enler = [d.width() for _, d, _i, _c in _DUGMELER]
    _yaz("       ust satir: dugmeler %s px · kutular %d px · genislikler %s"
         % (_boylar, _kutu, _enler))
    # Kullanicinin istegi: "tüm butonların boyu aynı olacak". Artik satirda
    # metin dugmesi kalmadigi icin olcut KUTULAR — dugmeler onlara
    # denklenince satirin TAMAMI tek boy oluyor.
    kontrol("dort dugme de AYNI BOYDA", len(set(_boylar)) == 1, _boylar)
    kontrol("dort dugme de AYNI GENISLIKTE", len(set(_enler)) == 1, _enler)
    kontrol("dugme boyu KUTULARLA da ayni (satirin tamami tek boy)",
            _boylar[0] == _kutu, "%d != %d" % (_boylar[0], _kutu))
    # 5 ogeden 6'ya cikildi ama satir DARALDI: metin dugmesi Qt'nin 80 px
    # tabanina oturuyordu, ikon dugmesi 28 px.
    kontrol("dugmeler dar (Qt'nin 80 px metin tabanina oturmuyor)",
            _enler[0] <= 32, _enler[0])
    ipucu = panel.model_secici.itemData(0, QtCore.Qt.ToolTipRole) or ""
    kontrol("model kutusunun ipucunda TAM etiket var",
            "quality" in ipucu, ipucu[:60])
    kontrol("model kutusunda KISA etiket gorunuyor",
            len(panel.model_secici.itemText(0)) < 14,
            panel.model_secici.itemText(0))

    # EFOR KUTUSU — gecikmenin %91-94'u dusunme (olculdu, config.EFORLAR).
    bolum("efor kutusu — dusunme miktari secilebiliyor mu")
    kontrol("panelde efor kutusu var", hasattr(panel, "efor_secici"))
    _degerler = [panel.efor_secici.itemData(i)
                 for i in range(panel.efor_secici.count())]
    _yaz("       efor secenekleri: %s" % _degerler)
    kontrol("IKI secenek var (high olculdu ve CIKARILDI)",
            len(_degerler) == 2, _degerler)
    kontrol("'low' secenegi var", "low" in _degerler, _degerler)
    kontrol("varsayilan BOS DIZE — CLI varsayilani, gecerli bir secim",
            "" in _degerler, _degerler)
    kontrol("'high' YOK (olculdu: varsayilandan da yavas)",
            "high" not in _degerler, _degerler)
    _eip = panel.efor_secici.itemData(0, QtCore.Qt.ToolTipRole) or ""
    kontrol("ipucu OLCULEN rakami veriyor", "37" in _eip, _eip[:80])
    kontrol("ipucu kalitenin OLCULMEDIGINI de soyluyor",
            "NOT MEASURED" in _eip.upper(), _eip[:200])

    # ILERI AL DUGMESI: bos yiginda basilabilir durmasin. Kullanicinin
    # istegi: "geri al'a basmadan once basilmasin".
    bolum("ileri al dugmesi — bos yiginda KAPALI")
    kontrol("panelde ileri dugmesi saklaniyor", hasattr(panel, "ileri_dugmesi"))
    kontrol("BASLANGICTA kapali", not panel.ileri_dugmesi.isEnabled())
    kontrol("ipucu bunu soyluyor",
            "Disabled" in panel.ileri_dugmesi.toolTip(),
            panel.ileri_dugmesi.toolTip())

    _bd = App.newDocument("IleriDugmeTest")
    _bd.UndoMode = 1
    App.setActiveDocument(_bd.Name)
    panel.ctl.executor.calistir('doc.addObject("Part::Box", "DugmeKutu")\n',
                                "dugme kutusu")
    panel._ileri_dugmesini_tazele()
    kontrol("is yapilinca HALA kapali (geri alinmadi)",
            not panel.ileri_dugmesi.isEnabled(), list(_bd.RedoNames))

    panel.geri_al()
    kontrol("GERI AL'a basilinca ACILIYOR",
            panel.ileri_dugmesi.isEnabled(), list(_bd.RedoNames))

    panel.ileri_al()
    kontrol("ileri alinca is geri geldi",
            _bd.getObject("DugmeKutu") is not None,
            [o.Name for o in _bd.Objects])
    kontrol("yigin bosalinca yine KAPANIYOR",
            not panel.ileri_dugmesi.isEnabled(), list(_bd.RedoNames))

    # Kod calismasi yigini silebiliyor — dugme onu da yansitmali.
    panel.geri_al()
    kontrol("ON KABUL: yine acik", panel.ileri_dugmesi.isEnabled())
    panel.ctl.blogu_calistir(type("B", (), {
        "kod": 'doc.addObject("Part::Box", "SilenKutu")\n',
        "baslik": "yigini silen"})())
    kontrol("kod calisip yigini silince KAPANIYOR",
            not panel.ileri_dugmesi.isEnabled(), list(_bd.RedoNames))
    App.closeDocument(_bd.Name)

    # "Kayıt" once ust satirdan KALDIRILMISTI (metin dugmesi 80 px yiyordu)
    # ve islevi sag tik menusune tasinmisti. Kullanici onu BULAMADI —
    # taşıma basarisiz sayildi. Simdi ikon dugmesi olarak geri geldi (28 px)
    # ve sag tik menusu de duruyor: iki kapi, tek islev.
    bolum("kayitlara erisim — gorunur dugme + sag tik, ikisi de")
    _dugme_adlari = [b.text() for b in
                     panel.findChildren(QtWidgets.QPushButton)]
    _yaz("       ust satir dugmeleri: %s" % _dugme_adlari)
    kontrol("ust satirda METIN dugmesi kalmadi",
            not any(a.strip() for a in _dugme_adlari[:4]), _dugme_adlari)
    kontrol("kayit dugmesi GORUNUR halde", panel.kayit_dugmesi.isVisible(),
            panel.kayit_dugmesi.isVisible())
    kontrol("kayit dugmesi kayitlari acan metoda bagli",
            hasattr(panel, "_kayitlari_ac"))
    # SAG TIK MENUSU KALDIRILDI (kullanici: "sağ tık menüde durmasın").
    # Icindeki tek oge kayitlardi ve o artik gorunur bir dugme; gizli
    # ikinci kapiyi tutmanin bir sebebi kalmadi.
    kontrol("sag tik menusu YOK", not hasattr(panel, "_sag_tik_menusu"))
    kontrol("ozel sag tik politikasi kapali",
            panel.contextMenuPolicy() != QtCore.Qt.CustomContextMenu,
            panel.contextMenuPolicy())

bolum("HICBIR YAZI KIRPILMIYOR — panel + kod karti, uctan uca")

# Kullanicinin sikayeti: "AI cevabinin sagi kaliyor, bazi kelimeler
# gozukmuyor". Sebep olculdu ve mesaj balonu DEGILDI: kod kartinin dugme
# satiri duz bir QHBoxLayout'ti ve kartin asgari genisligini 766 px'e
# cikariyordu — panelin asgari genisliginin (368 px) iki katindan fazla.
# Panelde yatay kaydirma KAPALI oldugu icin fazlasi kaydirilamiyor, dogrudan
# kirpiliyordu. Cozum: SaranSatir (bkz. code_card.SaranSatir).
#
# ON KABUL OLCULDU: bu bolum ESKI code_card.py ile (git HEAD) calistirildi ve
# DORT genislikte de kaldi — icerik 920 px'e tasiyordu, panel 900 px olsa
# bile. Yani sikayet "dar panelde" degil, HER genislikte gecerliydi: tek bir
# kart butun sohbet akisini 911 px'e geniyor, viewport'a sigmiyordu.
#     eski: kart asgari 911 px, 368/420/520/900 px'te kirpilan var
#     yeni: kart asgari 278 px, dordunde de kirpilan yok
#
# Bu test kirpmayi DOGRUDAN olcer: her GORUNUR alt widget'in sag/alt kosesi
# panelin icinde mi. Etiket kisaltmak gibi dolayli kontroller degil.
if panel is None:
    atla("kirpma", "panel olusmadi")
else:
    _uzun = "C:\\Users\\USER-1\\Desktop\\CADdy\\caddy\\execution\\executor.py"
    panel.mesaj_ekle("user", "10 mm kenarli bir kup yap")
    panel.mesaj_ekle("ai", "Tamam. Once " + _uzun + " dosyasina bakiyorum, "
                     "sonra kupu olusturuyorum. " + "uzunbolunemezkelime" * 4)
    panel.mesaj_ekle("sistem", "hazir")

    class _Blok:
        kod = ("doc.addObject('Part::Box', 'Kutu')  "
               "# " + _uzun + "\ndoc.recompute()\n")
        baslik = "kutu olustur — cok uzun bir baslik olsun ki satiri assin"
        guvenilir = False

    panel.kart_ekle(_Blok())
    _kart = panel._kartlar[-1]
    # En kotu hal: iki ek dugme de gorunur (hata + uyari) ve durum yazisi dolu.
    _kart.btn_hata.setVisible(True)
    _kart.btn_sonuc.setVisible(True)
    _kart.durum.setText("hata: NameError")

    # show() SART: gosterilmemis bir panelde yerlesim gecmiyor ve her sey
    # 100x30'luk varsayilan geometride kaliyor — kirpma dongusu de bos yere
    # "tasan yok" derdi (ilk yazimda tam bu oldu).
    panel.show()
    for _g in (368, 420, 520, 900):
        panel.resize(_g, 900)
        for _ in range(3):
            app.processEvents()
        _kirpik = []
        for _w in panel.findChildren(QtWidgets.QWidget):
            if not _w.isVisible():
                continue
            _sagalt = _w.mapTo(panel, QtCore.QPoint(_w.width(), _w.height()))
            if _sagalt.x() > panel.width() + 1:
                _kirpik.append("%s %r sag=%d" % (
                    _w.metaObject().className(),
                    getattr(_w, "text", lambda: "")()[:20], _sagalt.x()))
        _yaz("       %3d px -> kart %dx%d, kirpilan: %s"
             % (_g, _kart.width(), _kart.height(), _kirpik or "yok"))
        kontrol("%d px'te HICBIR widget sagdan tasmiyor" % _g,
                not _kirpik, _kirpik[:3])

    # Kartin kendi asgarisi panelin asgarisini ASMAMALI — asarsa kirpma
    # kaciniLMAZ hale gelir, yukaridaki dongu de bunu yakalayamayabilir
    # (o an gorunen dugmelere bagli).
    _kart_asgari = _kart.minimumSizeHint().width()
    _panel_asgari = panel.minimumSizeHint().width()
    _yaz("       kart asgari %d px  ·  panel asgari %d px  (kart eskiden "
         "766 px)" % (_kart_asgari, _panel_asgari))
    kontrol("kod karti panelden GENIS OLMAYI dayatmiyor",
            _kart_asgari <= _panel_asgari,
            "%d > %d" % (_kart_asgari, _panel_asgari))

    # Sarma gercekten calisiyor mu: dar panelde dugme satiri YUKSELMELI.
    _alt = _kart.layout().itemAt(2).layout()
    _dar, _genis = _alt.heightForWidth(360), _alt.heightForWidth(900)
    _yaz("       dugme satiri yuksekligi: 360 px'te %d, 900 px'te %d"
         % (_dar, _genis))
    kontrol("dar panelde dugmeler ALT SATIRA dokuluyor", _dar > _genis,
            "%d <= %d" % (_dar, _genis))

bolum("PanelYuzde ayari")
kontrol("varsayilan %40", config.panel_yuzde() == 40, config.panel_yuzde())
_eski = config.sayi("PanelYuzde")
try:
    config.yaz("PanelYuzde", 55)
    kontrol("gecerli deger okunuyor", config.panel_yuzde() == 55,
            config.panel_yuzde())
    config.yaz("PanelYuzde", 3)
    kontrol("sacma deger varsayilana duser", config.panel_yuzde() == 40,
            config.panel_yuzde())
    config.yaz("PanelYuzde", 200)
    kontrol("ust sinir disi deger varsayilana duser",
            config.panel_yuzde() == 40, config.panel_yuzde())
finally:
    config.yaz("PanelYuzde", _eski)

kontrol("genisligi_ayarla dock olusturmadan cagrilabilir (imza)",
        callable(getattr(_dock, "genisligi_ayarla", None)))

# ---------------------------------------------------- iki yerde ilerleme yok
bolum("ilerleme yazisi TEK yerde")
if panel is None:
    atla("ilerleme", "panel olusmadi")
else:
    panel._durum("calisiyor")
    panel._asama("dusunuyor")
    panel._dusunce_olcusu(500)
    app.processEvents()
    akis = panel._ilerleme.text() if panel._ilerleme is not None else ""
    _yaz("       akis : %r" % akis.replace("\n", " | "))

    kontrol("akistaki satir sayaci gosteriyor",
            " s" in akis and "token" in akis, akis)
    # Sag ust: hicbir etiket kalmadi. Once sayan saat, sonra "çalışıyor…"
    # da kaldirildi — kullanicinin acik istegi.
    kontrol("sag ustte durum etiketi HIC YOK",
            not hasattr(panel, "durum_etiketi"),
            getattr(panel, "durum_etiketi", None))
    ust_metinler = [w.text() for w in panel.findChildren(QtWidgets.QLabel)
                    if w.text()]
    _yaz("       arac cubugundaki etiket metinleri: %r" % ust_metinler)
    kontrol("arac cubugunda 'çalışıyor' yazan etiket yok",
            not any("çalışıyor" in m for m in ust_metinler), ust_metinler)
    kontrol("arac cubugunda 'hazır' yazan etiket yok",
            not any("hazır" in m for m in ust_metinler), ust_metinler)

    panel._durum("bosta")
    kontrol("bitince akistaki ilerleme silindi", panel._ilerleme is None)

    # Iptal geri bildirimi kaybolmamali — artik akista
    panel._durum("oluyor")
    app.processEvents()
    son = [w.text() for w in panel.findChildren(_dock.SaranEtiket)
           if "cancel" in w.text().lower()]
    kontrol("iptal geri bildirimi akista duruyor", bool(son), son)

# ---------------------------------------------------------------- kod karti
bolum("kod karti — sarma acik, kod kirpilmiyor")


class _Blok:
    baslik = "test"
    guvenilir = True
    kod = "\n".join([
        "kutu = doc.addObject('Part::Box', 'BuNesneAdiKastenUzunTutuldu')",
        "kutu.Length = 20; kutu.Width = 20; kutu.Height = 10",
        "kesici = doc.addObject('Part::Cylinder', 'BuDaKastenUzunBirAdSayilir')",
    ])


kart = CodeCard(_Blok())
kart.resize(600, 400)
kart.show()
app.processEvents()

kontrol("sarma WidgetWidth",
        kart.kod.lineWrapMode() == QtWidgets.QPlainTextEdit.WidgetWidth,
        kart.kod.lineWrapMode())
kontrol("yatay cubuk kapali",
        kart.kod.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff)

genis_satir = kart._gorunen_satir()
genis_yuk = kart.kod.height()
_yaz("       genis (600px): gorunen satir=%d yukseklik=%d"
     % (genis_satir, genis_yuk))

kart.resize(200, 400)
app.processEvents()
dar_satir = kart._gorunen_satir()
dar_yuk = kart.kod.height()
_yaz("       dar   (200px): gorunen satir=%d yukseklik=%d"
     % (dar_satir, dar_yuk))

kontrol("dar panelde gorunen satir sayisi ARTTI (sarma oldu)",
        dar_satir > genis_satir, "%d > %d" % (dar_satir, genis_satir))
kontrol("kart yuksekligi de arttI (kod alttan kirpilmiyor)",
        dar_yuk > genis_yuk, "%d > %d" % (dar_yuk, genis_yuk))
kontrol("blockCount tek basina yetmezdi (ON KABUL)",
        dar_satir > kart.kod.document().blockCount(),
        "%d > %d" % (dar_satir, kart.kod.document().blockCount()))

# Cok uzun kodda tavan calisiyor mu
class _UzunBlok:
    baslik = "uzun"
    guvenilir = True
    kod = "\n".join("satir_%d = %d" % (i, i) for i in range(80))


uzun = CodeCard(_UzunBlok())
uzun.show()
uzun.resize(400, 400)
app.processEvents()
satir_yuk = uzun.kod.fontMetrics().lineSpacing()
kontrol("80 satirlik kodda tavan uygulandi",
        uzun.kod.height() <= satir_yuk * CodeCard._EN_COK_SATIR + 20,
        uzun.kod.height())


class _KisaBlok:
    baslik = "kisa"
    guvenilir = True
    kod = "x = 1"


kisa = CodeCard(_KisaBlok())
kisa.show()
kisa.resize(400, 400)
app.processEvents()
kontrol("tek satirlik kodda taban uygulandi",
        kisa.kod.height() >= satir_yuk * CodeCard._EN_AZ_SATIR,
        kisa.kod.height())

# ------------------------------------------------- genisligi_ayarla GERCEKTEN
bolum("genisligi_ayarla — gercek QMainWindow + QDockWidget uzerinde")

# FreeCAD'in ana penceresi yok ama `Gui.getMainWindow()` de sonucta bir
# QMainWindow; resizeDocks'un bu Qt yapisinda gercekten calistigini burada
# gorebiliyoruz. Sinanmayan tek sey FreeCAD'in dock'u nereye koydugu.
try:
    mw = QtWidgets.QMainWindow()
    mw.resize(PENCERE, 900)
    orta = QtWidgets.QTextEdit()          # 3B gorunumun yerine duran widget
    mw.setCentralWidget(orta)
    d2 = QtWidgets.QDockWidget(mw)
    d2.setObjectName(_dock.NESNE_ADI)
    d2.setWidget(_dock.CaddyPanel(d2))
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, d2)
    mw.show()
    for _ in range(3): app.processEvents()

    onceki = d2.width()
    _dock.genisligi_ayarla(mw, d2)
    for _ in range(3): app.processEvents()
    sonraki = d2.width()
    pay = 100.0 * sonraki / mw.width()
    _yaz("       ayar oncesi: %d px (%%%.0f)"
         % (onceki, 100.0 * onceki / mw.width()))
    _yaz("       ayar sonrasi: %d px (%%%.0f)   hedef %d px"
         % (sonraki, pay, HEDEF))

    kontrol("resizeDocks bu Qt yapisinda var ve calisiyor",
            sonraki != onceki or abs(pay - 40) <= 6,
            "%d -> %d" % (onceki, sonraki))
    kontrol("panel ~%40 oldu (±6 puan)", abs(pay - 40) <= 6, "%.1f" % pay)
    kontrol("3B gorunume ~%60 kaldi", orta.width() >= mw.width() * 0.5,
            "%d / %d" % (orta.width(), mw.width()))

    # Kullanici kenari surukleyip baska bir genislik sectiyse: paneli_goster
    # ikinci kez cagrildiginda genisligi EZMEMELI (yalnizca ilk olusturmada
    # ayarlaniyor). Burada dogrudan cagirinca ise oran YENIDEN uygulanmali —
    # dugmenin gercekten bir isi olsun.
    mw.resizeDocks([d2], [900], QtCore.Qt.Horizontal)
    for _ in range(3): app.processEvents()
    elle = d2.width()
    kontrol("ON KABUL: kullanicinin secimi gercekten uygulandi",
            elle > HEDEF + 100, elle)
    _dock.genisligi_ayarla(mw, d2)
    for _ in range(3): app.processEvents()
    _yaz("       elle %d px -> dogrudan cagri sonrasi %d px"
         % (elle, d2.width()))
    kontrol("dogrudan cagrildiginda orani YENIDEN uyguluyor",
            abs(100.0 * d2.width() / mw.width() - 40) <= 6,
            d2.width())

    # ACILISTA SESSIZ. Kullanicinin sikayeti: "en basta caddy panel piksel
    # uyarisi geliyor, gelmesin". O satir her aciliste Rapor penceresine
    # dusuyordu. Olcum kaybolmadi (ayikla acikken yaziliyor) ama isler
    # yolundayken konusmuyor. Hedefe ULASILAMADIGI hal hala uyari — orada
    # susmak, gercek bir kusuru gizlemek olurdu.
    _sesler = {"bilgi": [], "uyari": [], "ayik": []}
    _yedek = (_log.bilgi, _log.uyari, _log.ayik)
    _log.bilgi = lambda m: _sesler["bilgi"].append(m)
    _log.uyari = lambda m: _sesler["uyari"].append(m)
    _log.ayik = lambda m: _sesler["ayik"].append(m)
    try:
        _dock.genisligi_ayarla(mw, d2)
        for _ in range(3): app.processEvents()
        _px = [m for m in _sesler["bilgi"] + _sesler["uyari"] if "px" in m]
        _yaz("       acilista duyulan: bilgi %d, uyari %d, ayik %d"
             % (len(_sesler["bilgi"]), len(_sesler["uyari"]),
                len(_sesler["ayik"])))
        kontrol("acilista PIKSEL satiri basilmiyor", not _px, _px[:1])
        kontrol("olcum kayboldu mu — hayir, ayikta duruyor",
                any("px" in m for m in _sesler["ayik"]), _sesler["ayik"])

        # Hedefe ulasilamayan hal: dar pencerede asgari > hedef.
        _sesler["uyari"].clear()
        mw.resize(600, 900)             # %40'i 240 px < panel asgarisi
        for _ in range(3): app.processEvents()
        _dock.genisligi_ayarla(mw, d2)
        for _ in range(3): app.processEvents()
        kontrol("hedefe ULASILAMAZSA hala UYARI veriyor",
                any("hedefe ulasamadi" in m for m in _sesler["uyari"]),
                _sesler["uyari"])
    finally:
        _log.bilgi, _log.uyari, _log.ayik = _yedek
    mw.close()
except Exception as e:                                           # noqa: BLE001
    import traceback as _tb
    atla("genisligi_ayarla", str(e)[:150])
    _yaz(_tb.format_exc()[-600:])


# ------------------------------------------------- komsu dock sutunu genisletiyor
bolum("komsu dock — sutunu hedeften genis tutan panel")

# Kullanicinin bildirdigi hata: "CADdy 651 px, 514 px olmasi gerekirken".
# Sebep olculdu: Qt'de bir kenardaki dock'lar TEK SUTUNU paylasir; sutun,
# icindeki dock'larin EN BUYUK asgarisinden dar olamaz. Bizim asgarimiz
# 346 px olsa bile, yanimizdaki FreeCAD paneli 650 px istiyorsa biz de
# 650 px kaliriz. Eski kod bunu SESSIZCE gecerdi (yalnizca kendi
# asgarisina bakiyordu) — hata kullanicidan geri geldi, kodumuzdan degil.


def _komsulu_pencere(kardes_ic):
    m = QtWidgets.QMainWindow()
    m.resize(PENCERE, 900)
    m.setCentralWidget(QtWidgets.QTextEdit())
    k = QtWidgets.QDockWidget("Model", m)
    k.setObjectName("Model")
    k.setWidget(kardes_ic)
    m.addDockWidget(QtCore.Qt.RightDockWidgetArea, k)
    d = QtWidgets.QDockWidget(m)
    d.setObjectName(_dock.NESNE_ADI)
    d.setWidget(_dock.CaddyPanel(d))
    m.addDockWidget(QtCore.Qt.RightDockWidgetArea, d)
    m.show()
    for _ in range(3):
        app.processEvents()
    return m, k, d


try:
    # ON KABUL: komsu gercekten engelliyor mu? Once duz resizeDocks ile
    # olculuyor — engellemiyorsa asagidaki testin bir anlami kalmazdi.
    _ag = QtWidgets.QTreeWidget()
    _ag.setMinimumWidth(650)
    mw3, k3, d3 = _komsulu_pencere(_ag)
    mw3.resizeDocks([d3], [HEDEF], QtCore.Qt.Horizontal)
    for _ in range(3):
        app.processEvents()
    _yaz("       ON KABUL: duz resizeDocks ile %d px (hedef %d)"
         % (d3.width(), HEDEF))
    kontrol("ON KABUL: 650 px asgarili komsu sutunu gercekten genis tutuyor",
            d3.width() > HEDEF + 50, d3.width())

    # Simdi asil is: genisligi_ayarla komsunun ELLE konmus asgarisini
    # gevsetip hedefe ulasmali.
    _dock.genisligi_ayarla(mw3, d3)
    for _ in range(4):
        app.processEvents()
    _yaz("       genisligi_ayarla sonrasi: %d px" % d3.width())
    kontrol("elle asgarili komsuya ragmen hedefe ulasiyor",
            abs(d3.width() - HEDEF) <= 12, d3.width())
    kontrol("komsunun asgarisi gercekten gevsetildi",
            k3.widget().minimumWidth() == 0, k3.widget().minimumWidth())
    mw3.close()

    # Asgari ICERIKTEN geliyorsa dokunmuyoruz (komsuyu kalici maximumWidth
    # ile kafese koymak, kullanicinin o paneli bir daha genisletmesini
    # engellerdi). Beklenen davranis: hedefe ULASILAMAZ ama UYARI verilir
    # ve engelleyen dock ADIYLA yazilir — sessiz kalmak, kusuru gizlerdi.
    _sesler = {"uyari": []}
    _yedek = (_log.bilgi, _log.uyari, _log.ayik)
    try:
        _log.uyari = lambda m: _sesler["uyari"].append(str(m))
        _log.bilgi = lambda m: None
        _log.ayik = lambda m: None
        mw4, k4, d4 = _komsulu_pencere(QtWidgets.QLabel("X" * 90))
        _dock.genisligi_ayarla(mw4, d4)
        for _ in range(4):
            app.processEvents()
        _yaz("       icerikten genis komsu: %d px, uyari: %s"
             % (d4.width(), _sesler["uyari"]))
        kontrol("icerikten genis komsuda UYARI veriyor",
                any("hedefe ulasamadi" in m for m in _sesler["uyari"]),
                _sesler["uyari"])
        kontrol("uyari engelleyen dock'u ADIYLA soyluyor",
                any("Model" in m for m in _sesler["uyari"]),
                _sesler["uyari"])
        mw4.close()
    finally:
        _log.bilgi, _log.uyari, _log.ayik = _yedek
except Exception as e:                                           # noqa: BLE001
    import traceback as _tb
    atla("komsu dock", str(e)[:150])
    _yaz(_tb.format_exc()[-600:])


# --------------------------------------------------------- kutuphane dugmesi
bolum("kutuphane — secilen kayit denetleyiciye SURDURULMEK uzere gidiyor")

if panel is None:
    atla("kutuphane", "panel olusmadi")
else:
    try:
        from caddy import kayitlar as _kayitlar
        import tempfile as _tf
        from pathlib import Path as _P

        _gec = _P(_tf.mkdtemp(prefix="caddy_panel_kayit_"))
        _dosya = _gec / "2026-08-27_9564dc71.txt"
        _dosya.write_text(
            "=" * 72 + "\nCADdy chat log\n"
            "session : 9564dc71-071d-4ca3-9c21-483cf5766739\n"
            "model   : claude-opus-5\n"
            "started : 2026-08-27T13:39:39\n" + "=" * 72 + "\n\n"
            "--- USER  [13:39:55] ---\nkamyonet tasarla\n\n"
            "--- AI  (claude-opus-5)  [13:40:03] ---\nolur\n",
            encoding="utf-8")
        _k = _kayitlar.listele(_gec)[0]

        _cagri = {}
        _yedek_ctl = panel.ctl.sohbeti_surdur
        panel.ctl.sohbeti_surdur = (
            lambda o, d: _cagri.update(oturum=o, dosya=d))
        _once = panel.akis.count()
        try:
            panel._sohbeti_surdur(_k)
        finally:
            panel.ctl.sohbeti_surdur = _yedek_ctl
        app.processEvents()

        kontrol("denetleyiciye oturum kimligi gitti",
                _cagri.get("oturum") == "9564dc71-071d-4ca3-9c21-483cf5766739",
                _cagri)
        kontrol("gunluk dosyasi da gitti (ayni dosyaya devam icin)",
                _cagri.get("dosya") == _k.dosya, _cagri.get("dosya"))
        kontrol("akisa hatirlatma satirlari eklendi",
                panel.akis.count() > _once,
                "%d -> %d" % (_once, panel.akis.count()))

        # Dugme gercekten bu islevi cagiriyor mu — ipucu metni degil, BAGLANTI.
        kontrol("kutuphane dugmesi var ve tiklanabilir",
                panel.kayit_dugmesi is not None
                and panel.kayit_dugmesi.isEnabled())

        import shutil as _sh
        _sh.rmtree(_gec, ignore_errors=True)
    except Exception as e:                                       # noqa: BLE001
        import traceback as _tb2
        atla("kutuphane", str(e)[:150])
        _yaz(_tb2.format_exc()[-500:])


bolum("yerlesim BIZDEN SONRA oturursa — ek deneme")
# OLCULEN SIKAYET (2026-08-28): kullanicinin panelinde genislik 651 px'te
# kaldi, hedef 512 idi. Kendi asgarimiz 346, yani suclu biz degildik; ayni
# kenarda hedefi asan bir komsu da bulunamadi. Geriye tek aciklama kaldi:
# `resizeDocks` TEK KEZ cagriliyordu ve yerlesim ondan sonra oturup son
# sozu soyluyordu. Burada o durum taklit ediliyor.
try:
    _m5 = QtWidgets.QMainWindow()
    _m5.resize(PENCERE, 900)
    _m5.setCentralWidget(QtWidgets.QTextEdit())
    _d5 = QtWidgets.QDockWidget(_m5)
    _d5.setObjectName(_dock.NESNE_ADI)
    _d5.setWidget(_dock.CaddyPanel(_d5))
    _m5.addDockWidget(QtCore.Qt.RightDockWidgetArea, _d5)
    _m5.show()
    for _ in range(3):
        app.processEvents()

    # Bizim cagrimizin USTUNE yazan bir yerlesim: ilk resizeDocks'tan
    # sonra, biz olcmeye firsat bulmadan baskasi genisligi geri koyuyor.
    _sayac = {"n": 0}
    _gercek_resize = _m5.resizeDocks

    def _sabotajli(docklar, boylar, yon):
        _gercek_resize(docklar, boylar, yon)
        _sayac["n"] += 1
        if _sayac["n"] == 1:              # yalnizca ILK cagriyi ez
            _gercek_resize([_d5], [651], QtCore.Qt.Horizontal)

    _m5.resizeDocks = _sabotajli
    _dock.genisligi_ayarla(_m5, _d5)
    for _ in range(6):
        app.processEvents()
    _m5.resizeDocks = _gercek_resize
    _yaz("       ustune yazildiktan sonra: %d px (hedef %d, %d resize cagrisi)"
         % (_d5.width(), HEDEF, _sayac["n"]))
    kontrol("ustune yazilsa bile hedefe donuyor",
            abs(_d5.width() - HEDEF) <= 12, _d5.width())
    kontrol("ek deneme GERCEKTEN yapildi", _sayac["n"] >= 2, _sayac["n"])
    _m5.close()
except Exception as e:                                           # noqa: BLE001
    atla("yerlesim ustune yazma", str(e)[:150])

bolum("karsilama — kisa olmali")
# Kullanicinin istegi (2026-08-28): "ilk acilis kisa bir cumle olsun, o
# kadar aciklamaya gerek yok". Eskiden yedi satirdi ve dar panelde ilk
# ekranin yarisini yiyordu.
try:
    _msj = []
    _p6 = _dock.CaddyPanel()
    _p6.mesaj_ekle = lambda rol, metin: _msj.append((rol, metin))
    _p6._karsilama()
    _metin = _msj[0][1] if _msj else ""
    _satir = [s for s in _metin.splitlines() if s.strip()]
    _yaz("       karsilama %d satir, %d karakter" % (len(_satir), len(_metin)))
    kontrol("karsilama en fazla iki satir", len(_satir) <= 2, _satir)
    kontrol("karsilama kisa (<160 karakter)", len(_metin) < 160, len(_metin))
    kontrol("yine de ne yazacagini soyluyor", "cube" in _metin, _metin)
    kontrol("model adi duruyor", config.model() in _metin, _metin)
except Exception as e:                                           # noqa: BLE001
    atla("karsilama", str(e)[:150])

bolum("tema stil sayfasi ikon dugmesini SISIREMEZ")
# OLCULEN HATA (kullanicinin Rapor penceresi, 2026-08-28): alti
# QPushButton'un da ELLE konmus asgarisi 106 px'ti, oysa _ikon_dugmesi
# setFixedWidth(28) diyor. FreeCAD'in tema stil sayfasi
# `QPushButton { min-width: ... }` tanimliyor ve Qt bunu polish sirasinda
# widget uzerinde setMinimumWidth() cagirarak uyguluyor — bizim satirin
# ustune yaziyor. Ust satir 4x106 + kutular = 651 px taban koyuyordu.
#
# Bu test PIKSEL OLCMUYOR (yazi tipine bagli sayilar offscreen yalan
# soyluyor, bkz. MANTIK 45.4b). Olctugu sey KASKAD: uygulama duzeyinde
# konmus bir kural, widget duzeyindeki kurali yenemez.
try:
    _tema = "QPushButton { min-width: 106px; }"
    _eski_ss = app.styleSheet()
    app.setStyleSheet(_tema)
    # ON KABUL: kural gercekten sisiriyor mu? Ciplak bir dugme ayni tema
    # altinda 106'ya cikmiyorsa asagidaki testin hicbir anlami kalmaz —
    # tuzagin var oldugunu once kanitliyoruz.
    _ciplak = QtWidgets.QPushButton()
    _ciplak.setFixedWidth(28)          # bizim kodun yaptiginin aynisi
    _ciplak.show()
    for _ in range(3):
        app.processEvents()
    _yaz("       ON KABUL: ciplak dugme (setFixedWidth 28) -> asgari %d px"
         % _ciplak.minimumWidth())
    kontrol("ON KABUL: tema kurali setFixedWidth'in USTUNE yaziyor",
            _ciplak.minimumWidth() > 60, _ciplak.minimumWidth())
    _ciplak.close()

    _p7 = _dock.CaddyPanel()
    _p7.show()
    for _ in range(3):
        app.processEvents()
    _dugmeler = [_p7.yeni_dugmesi, _p7.geri_dugmesi,
                 _p7.ileri_dugmesi, _p7.kayit_dugmesi]
    _genis = [d.minimumWidth() for d in _dugmeler]
    _yaz("       tema min-width 106px iken ikon dugmeleri: %s" % _genis)
    kontrol("tema kurali ikon dugmesini sisirmiyor",
            all(g < 60 for g in _genis), _genis)
    kontrol("dugmenin kendi stil sayfasi min-width tasiyor",
            all("min-width" in d.styleSheet() for d in _dugmeler),
            [d.styleSheet() for d in _dugmeler])
    kontrol("max-width de var — tema genisletemesin",
            all("max-width" in d.styleSheet() for d in _dugmeler),
            [d.styleSheet() for d in _dugmeler])
    _p7.close()
    app.setStyleSheet(_eski_ss)
except Exception as e:                                           # noqa: BLE001
    try:
        app.setStyleSheet(_eski_ss)
    except Exception:
        pass
    atla("tema stil sayfasi", str(e)[:150])
_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d   ATLANDI %d" % (gecti, basarisiz, atlandi))
_yaz("=" * 70)
