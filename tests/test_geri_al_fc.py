"""AI'in kendi degisikligini geri almasi — denetimli yol.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_geri_al_fc.py

Aga CIKMAZ. Model yanitini taklit edip (`_turn_done` sentetik bir TurSonucu
ile surulur) isaretin dogru yerde tetiklendigi ve TETIKLENMEDIGI sinaniyor.

NEDEN VAR — olculdu, LOG/2026-08-20_baa70fa4.txt:

    15:32:51  AI : "Ilk adim kod degil: Ctrl+Z ile ... geri don."
    15:46:12  KUL: "geri aldim"
              -> 13 dk 21 sn, oturum tamamen durdu.

    16:04:52  AI : yine "Ctrl+Z ile bu son adimi geri al"
    16:05:20  AI : "Geri alindigini VARSAYIP devam ediyorum"
              -> ve o varsayimin uzerine kod uretti.

Ucuncusu bir hiz sorunu degil DOGRULUK sorunu: kullanicinin "tamam"i
"geri aldim" mi "devam et" mi belli degildi. Bu testin asil isi, reddetme
yolunun modele GERCEKTEN haber verdigini gostermek.

Rapor dosyaya satir satir yaziliyor (MANTIK 14.5).
"""

import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_geri_al.txt")
with open(RAPOR, "w", encoding="utf-8") as _f:
    _f.write("")

gecti = basarisiz = 0


def _yaz(m):
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


def bolum(ad):
    _yaz("")
    _yaz("--- %s %s" % (ad, "-" * max(0, 56 - len(ad))))


import FreeCAD as App
from PySide import QtCore

from caddy import conversation as cv
from caddy.conversation import ConversationController
from caddy.transport.transport import TurSonucu

_yaz("=" * 70)
_yaz("CADdy geri alma testleri")
_yaz("=" * 70)

app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(sys.argv[:1])

doc = App.newDocument("GeriAlTest")
doc.UndoMode = 1                      # konsolda varsayilan KAPALI
kontrol("ON KABUL: undo acik", doc.UndoMode == 1, doc.UndoMode)

ctl = ConversationController()
mesajlar = []
ctl.mesaj.connect(lambda r, m: mesajlar.append((r, m)))
gonderilen = []
ctl.transport.tur_gonder = lambda *a, **k: gonderilen.append(a[0] if a else "")

# --------------------------------------------------------------- isaret
bolum("isaret ayristirma")
kontrol("kendi satirinda tetikler",
        cv._UNDO_MARKER.search("Yanlis oldu.\nGERI-AL") is not None)
kontrol("Turkce yazim da tetikler",
        cv._UNDO_MARKER.search("bitti\nGERİ-AL\n") is not None)
kontrol("cumle icinde TETIKLEMEZ",
        cv._UNDO_MARKER.search("bunu geri-al demeye gerek yok") is None)
kontrol("bosluklu satirda tetikler",
        cv._UNDO_MARKER.search("\n   GERI-AL   \n") is not None)
kontrol("dongu siniri 2", cv._UNDO_LIMIT == 2, cv._UNDO_LIMIT)

# ----------------------------------------------------------- bos yigin
bolum("bos yiginda")
oldu, aciklama = ctl.geri_al()
kontrol("bos yiginda geri almiyor", not oldu, aciklama)
_yaz("       %s" % aciklama)

# ------------------------------------------------------- AI degisikligi
bolum("AI degisikligi geri aliniyor")
s = ctl.executor.calistir(
    'k = doc.addObject("Part::Box", "AiKutu")\nk.Length = 12\n', "kutu ekle")
kontrol("kod calisti", s.basarili, s.hata_izi[-200:])
kontrol("nesne eklendi", doc.getObject("AiKutu") is not None)
_yaz("       undo yigini: %s" % list(doc.UndoNames))
kontrol("tepe kaydi AI oneki tasiyor",
        doc.UndoNames and doc.UndoNames[0].startswith(cv._AI_PREFIX),
        list(doc.UndoNames))

oldu, aciklama = ctl.geri_al(ai_mi=True)
kontrol("geri alindi", oldu, aciklama)
kontrol("nesne gitti", doc.getObject("AiKutu") is None,
        [o.Name for o in doc.Objects])
kontrol("namespace temizlendi (bayat baglama = sert cokme)",
        ctl.executor._ns == {}, list(ctl.executor._ns)[:5])

# ------------------------------------------- KULLANICININ isi korunuyor
bolum("KULLANICININ isi korunuyor — asil emniyet")
s2 = ctl.executor.calistir(
    'k = doc.addObject("Part::Box", "AiKutu2")\n', "ai kutusu")
kontrol("ai kodu calisti", s2.basarili, s2.hata_izi[-200:])

# Kullanici ELLE bir sey yapiyor — GUI'de bu bir Gui islemi olurdu, burada
# ayni sonucu veren duz bir App islemi.
doc.openTransaction("Kullanici: elle kutu")
doc.addObject("Part::Box", "ElleKutu")
doc.commitTransaction()
doc.recompute()
_yaz("       undo yigini: %s" % list(doc.UndoNames))
kontrol("ON KABUL: tepede artik kullanicinin isi var",
        not doc.UndoNames[0].startswith(cv._AI_PREFIX), doc.UndoNames[0])

oldu, aciklama = ctl.geri_al()
kontrol("REDDEDILDI — kullanicinin isi silinmedi", not oldu, aciklama)
kontrol("kullanicinin nesnesi duruyor", doc.getObject("ElleKutu") is not None)
kontrol("AI'in nesnesi de duruyor", doc.getObject("AiKutu2") is not None)
_yaz("       %s" % aciklama)
kontrol("aciklama tepedeki islemin adini soyluyor",
        "elle kutu" in aciklama.lower(), aciklama)

# --------------------------------------------------- reddedilince model
bolum("reddedilince MODEL haberdar ediliyor")
mesajlar.clear()
gonderilen.clear()
ctl._undo_turns = 0
ctl._ai_undo()
kontrol("kullaniciya soylendi",
        any("not done" in m for _, m in mesajlar), mesajlar)
kontrol("MODELE de soylendi (varsayimla devam etmesin)",
        len(gonderilen) == 1, len(gonderilen))
if gonderilen:
    kontrol("mesaj 'varsayma' diyor", "NOT assume" in gonderilen[0],
            gonderilen[0][:200])
    kontrol("mesaj sebebi tasiyor", "elle kutu" in gonderilen[0].lower(),
            gonderilen[0][:200])

bolum("BASARILI halde tur HARCANMIYOR")
# Kullanicinin islemini geri alalim ki tepede yine AI kalsin
doc.undo()
doc.recompute()
_yaz("       undo yigini: %s" % list(doc.UndoNames))
mesajlar.clear()
gonderilen.clear()
ctl._undo_turns = 0
ctl._ai_undo()
kontrol("geri alindi", doc.getObject("AiKutu2") is None,
        [o.Name for o in doc.Objects])
kontrol("kullaniciya soylendi", any("AI undid" in m for _, m in mesajlar),
        mesajlar)
kontrol("modele TUR HARCANMADI (varsayimi zaten dogru)",
        gonderilen == [], gonderilen)

# ------------------------------------------------------------ dongu siniri
bolum("dongu siniri")
for i in range(3):
    ctl.executor.calistir(
        'doc.addObject("Part::Box", "Dongu%d")\n' % i, "dongu %d" % i)
mesajlar.clear()
gonderilen.clear()
ctl._undo_turns = 0
for i in range(3):
    ctl._ai_undo()
kontrol("sinir uygulandi", ctl._undo_turns == cv._UNDO_LIMIT,
        ctl._undo_turns)
kontrol("durduruldugu SOYLENIYOR",
        any("stopped" in m for _, m in mesajlar), mesajlar)
kontrol("ucuncu kutu HALA duruyor (sinir gercekten kesti)",
        doc.getObject("Dongu2") is not None or doc.getObject("Dongu0") is not None,
        [o.Name for o in doc.Objects])

bolum("gercek kullanici mesaji sayaci sifirliyor")
ctl._undo_turns = 2
gonderilen.clear()
ctl.gonder("yeni bir istek", kullanici_mi=True)
kontrol("sayac sifirlandi", ctl._undo_turns == 0, ctl._undo_turns)

# --------------------------------------------------------- tur ayristirma
bolum("tam tur: isaret yanittan ayikaniyor")
mesajlar.clear()
gonderilen.clear()
ctl._undo_turns = 0
ctl.executor.calistir('doc.addObject("Part::Box", "TurKutu")\n', "tur kutu")

ctl._turn_done(TurSonucu(metin="Bu adim yanlis oldu, geri aliyorum.\n"
                               "GERI-AL\n"))
ai_mesajlari = [m for r, m in mesajlar if r == "ai"]
_yaz("       ai mesaji: %r" % (ai_mesajlari[0] if ai_mesajlari else None))
kontrol("isaret kullaniciya GOSTERILMIYOR",
        ai_mesajlari and "GERI-AL" not in ai_mesajlari[0], ai_mesajlari)
kontrol("aciklama metni korundu",
        ai_mesajlari and "yanlis oldu" in ai_mesajlari[0], ai_mesajlari)
kontrol("geri alma GERCEKTEN oldu", doc.getObject("TurKutu") is None,
        [o.Name for o in doc.Objects])

bolum("isaret yoksa geri alma OLMAMALI")
ctl.executor.calistir('doc.addObject("Part::Box", "Kalsin")\n', "kalsin")
mesajlar.clear()
ctl._turn_done(TurSonucu(metin="Her sey yolunda gorunuyor."))
kontrol("isaretsiz yanitta geri alma yok",
        doc.getObject("Kalsin") is not None,
        [o.Name for o in doc.Objects])

# ------------------------------------------------------------ baglamda
bolum("baglamda undo yigini gorunuyor")
from caddy.context import serializer as sz

metin = sz.belge_metni(doc)
_yaz("       %s" % next((s for s in metin.splitlines()
                         if s.startswith("undo_stack=")), "(yok)"))
kontrol("undo_stack satiri var", "undo_stack=" in metin,
        metin[:400])
kontrol("tepedeki islem adi yaziyor", "Kalsin" in metin or "kalsin" in metin,
        metin[:400])

# ============================================================== ILERI AL
# OLCULEN SENARYO (LOG/2026-08-24_3ad4cef1.txt 12:09:33-12:09:58): kullanici
# "evet guzel oldu istedigim gibi" dedigi sonucu yanlislikla geri aldi, sonra
# eski kod blogunu iki kez calistirip ayni hatayi aldi ve oturum bitti. Ileri
# yiginda uc kayit hala duruyordu — ona uzanacak dugme yoktu.
bolum("ILERI AL — bos yiginda")
doc2 = App.newDocument("IleriAlTest")
doc2.UndoMode = 1
App.setActiveDocument(doc2.Name)
oldu, aciklama = ctl.ileri_al()
kontrol("bos ileri yigininda ileri almiyor", not oldu, aciklama)
kontrol("sebebini soyluyor", "new change" in aciklama, aciklama)
_yaz("       %s" % aciklama)

bolum("ILERI AL — geri alinan is GERI GELIYOR")
ctl.executor.calistir('doc.addObject("Part::Box", "Geri1")\n', "birinci")
ctl.executor.calistir('doc.addObject("Part::Box", "Geri2")\n', "ikinci")
kontrol("ON KABUL: iki nesne var",
        doc2.getObject("Geri1") is not None and doc2.getObject("Geri2") is not None,
        [o.Name for o in doc2.Objects])
ctl.geri_al()
ctl.geri_al()
kontrol("ikisi de geri alindi", [o.Name for o in doc2.Objects] == [],
        [o.Name for o in doc2.Objects])
_yaz("       ileri yigini: %s" % list(doc2.RedoNames))
kontrol("ileri yigininda IKI kayit var", len(doc2.RedoNames) == 2,
        list(doc2.RedoNames))

oldu, aciklama = ctl.ileri_al()
kontrol("ileri alindi", oldu, aciklama)
kontrol("EN SON geri alinan geri geldi (Geri1)",
        doc2.getObject("Geri1") is not None, [o.Name for o in doc2.Objects])
kontrol("digeri HENUZ gelmedi", doc2.getObject("Geri2") is None,
        [o.Name for o in doc2.Objects])
kontrol("namespace temizlendi (bayat baglama = sert cokme)",
        ctl.executor._ns == {}, list(ctl.executor._ns)[:5])
oldu, _ = ctl.ileri_al()
kontrol("ikinci ileri de calisti", oldu and doc2.getObject("Geri2") is not None,
        [o.Name for o in doc2.Objects])
kontrol("yigin bosaldi", len(doc2.RedoNames) == 0, list(doc2.RedoNames))

bolum("ILERI AL — KULLANICININ isi de geri getirilebiliyor")
# Asimetri kasitli: geri alma is SILER (denetim var), ileri alma is GETIRIR.
doc2.openTransaction("Kullanici: elle")
doc2.addObject("Part::Box", "ElleGeri")
doc2.commitTransaction()
doc2.recompute()
doc2.undo()
doc2.recompute()
kontrol("ON KABUL: kullanicinin nesnesi geri alinmis",
        doc2.getObject("ElleGeri") is None, [o.Name for o in doc2.Objects])
kontrol("ON KABUL: ileri yigininin tepesi AI DEGIL",
        not doc2.RedoNames[0].startswith(cv._AI_PREFIX), list(doc2.RedoNames))
oldu, aciklama = ctl.ileri_al()
kontrol("REDDEDILMIYOR — is geri getiriliyor", oldu, aciklama)
kontrol("kullanicinin nesnesi geri geldi", doc2.getObject("ElleGeri") is not None,
        [o.Name for o in doc2.Objects])
kontrol("kimin isi oldugu soyleniyor", "elle" in aciklama.lower(), aciklama)

bolum("ILERI YIGINI ne zaman KAYBOLUYOR — olculen davranis")
# 1) DEGISIKLIK yapip patlayan kod yigini yakar.
ctl.executor.calistir('doc.addObject("Part::Box", "Yakan")\n', "yakan")
ctl.geri_al()
kontrol("ON KABUL: ileri yigini dolu", len(doc2.RedoNames) == 1,
        list(doc2.RedoNames))
mesajlar.clear()
ctl.blogu_calistir(type("B", (), {
    "kod": 'doc.addObject("Part::Box", "YarimKalan")\nraise ValueError("patla")\n',
    "baslik": "degisiklik yapip patlayan"})())
kontrol("ileri yigini SILINDI (olculdu: degisiklik + abort)",
        len(doc2.RedoNames) == 0, list(doc2.RedoNames))
kontrol("kullaniciya SOYLENDI (sessizce kaybolmuyor)",
        any("Redo history cleared" in m for _, m in mesajlar), mesajlar)

# 2) SALT-OKUNUR kod yigini KORUR — gunlukteki iki basarisiz calistirma
#    boyleydi, yani dugme o gun var olsaydi is geri gelirdi.
ctl.executor.calistir('doc.addObject("Part::Box", "Korunan")\n', "korunan")
ctl.geri_al()
kontrol("ON KABUL: ileri yigini yine dolu", len(doc2.RedoNames) == 1,
        list(doc2.RedoNames))
mesajlar.clear()
ctl.blogu_calistir(type("B", (), {
    "kod": 'raise RuntimeError("bunny veya Karin_dolgusu yok")\n',
    "baslik": "gunlukteki hatanin aynisi"})())
kontrol("HICBIR SEY DEGISTIRMEDEN patlayan kod yigini KORUYOR",
        len(doc2.RedoNames) == 1, list(doc2.RedoNames))
kontrol("bosuna uyari verilmedi",
        not any("Redo history cleared" in m for _, m in mesajlar), mesajlar)
oldu, _ = ctl.ileri_al()
kontrol("GUNLUKTEKI KAYIP GERI GELIYOR: is ileri alinabildi",
        oldu and doc2.getObject("Korunan") is not None,
        [o.Name for o in doc2.Objects])

bolum("ILERI AL — panel dugmesi bagli mi")
import inspect

from caddy.ui import dock as _dock

kaynak = inspect.getsource(_dock.CaddyPanel._arac_cubugu)
kontrol("arac cubugunda 'İleri al' dugmesi var", "İleri al" in kaynak, kaynak[:200])
kontrol("dugme ileri_al'a bagli", "self.ileri_al" in kaynak, kaynak[:400])
kontrol("panelde ileri_al metodu var", hasattr(_dock.CaddyPanel, "ileri_al"))
kontrol("panel metodu controller'i cagiriyor",
        "ctl.ileri_al" in inspect.getsource(_dock.CaddyPanel.ileri_al))
kontrol("ipucu ileri gecmisinin silinebilecegini soyluyor",
        "clears the redo" in kaynak, kaynak[:600])

_yaz("")
_yaz("=" * 70)
_yaz("GECTI %d   BASARISIZ %d" % (gecti, basarisiz))
_yaz("=" * 70)
if basarisiz:
    sys.exit(1)
