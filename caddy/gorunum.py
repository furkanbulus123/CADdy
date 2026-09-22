"""3B gorunumu PNG olarak yakalar.

Neden burada, ui/ altinda degil: `conversation.py` bunu cagirmak zorunda
(gorsel kontrol turunu o yonetiyor) ve KATMAN KURALI geregi conversation
ui/'yi import edemez. Bu modul widget uretmez, yalnizca goruntu dondurur.

Neden PNG BAYTI donduruyor da dosya yolu degil: goruntu modele stream-json
girdisinde base64 `image` blogu olarak gidiyor (bkz. transport). Diske kalici
bir dosya birakmanin gereksi yok - gecici dosya okunup hemen siliniyor.

FreeCAD'de gorunum yakalamanin iki yolu var ve ikisi de GUI oturumu ister;
freecadcmd'de ActiveView yoktur, bu yuzden burasi BASSIZ TEST EDILEMEZ
(tests/_probe_goruntu.py bunu dogruladi: Gui.getMainWindow bile yok).
O yuzden her adim tek tek korunuyor ve basarisizlikta None donuyor -
gorsel kontrol calismazsa sohbet yine de yurumeli.
"""

from __future__ import annotations

import os
import tempfile

from . import log

# Panelde gosterilecek makul bir boyut. Buyutmek token maliyetini dogrudan
# artirir (olculdu: 200x120'lik bir test resmi bile ~2.3k token'lik bir
# istege dönüştü), kucultmek detayi kaybettirir.
GENISLIK = 900
YUKSEKLIK = 640


def yakalanabilir_mi() -> bool:
    """GUI oturumu var mi ve aktif bir 3B gorunum acik mi."""
    try:
        import FreeCADGui as Gui
    except Exception:
        return False
    try:
        return (Gui.ActiveDocument is not None
                and Gui.ActiveDocument.ActiveView is not None)
    except Exception:
        return False


def yakala(genislik: int = GENISLIK, yukseklik: int = YUKSEKLIK) -> bytes | None:
    """Aktif 3B gorunumu PNG bayti olarak dondurur; olmazsa None."""
    try:
        import FreeCADGui as Gui
    except Exception as e:
        log.uyari(f"gorunum yakalanamadi (GUI yok): {e}")
        return None

    try:
        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:
        log.uyari(f"aktif 3B gorunum yok: {e}")
        return None

    # Gecici dosyayi ONCE kapatiyoruz: Windows'ta acik bir dosyaya baska bir
    # surec/kutuphane yazamaz, saveImage sessizce basarisiz olur.
    tut = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    yol = tut.name
    tut.close()

    try:
        try:
            # "Current" = kullanicinin ekranda gordugu arka plan. Kullanici
            # "mevcut gorunum" dedi: ayni seye baksinlar.
            gorunum.saveImage(yol, genislik, yukseklik, "Current")
        except TypeError:
            # Bazi surumlerde arka plan argumani yok.
            gorunum.saveImage(yol, genislik, yukseklik)

        with open(yol, "rb") as f:
            veri = f.read()
        if not veri:
            log.uyari("gorunum yakalandi ama dosya bos")
            return None
        return veri
    except Exception as e:
        log.uyari(f"saveImage basarisiz: {e}")
        return _widget_ile_yakala()
    finally:
        try:
            os.unlink(yol)
        except Exception:
            pass


def yakala_cok(genislik: int = GENISLIK,
               yukseklik: int = YUKSEKLIK) -> list[bytes]:
    """Uc aciyi yakalar: KULLANICININ ACISI + on + ust.

    NEDEN UC KARE. Tek kare, tek acidan bakmak demek ve gunlukte bunun
    bedeli olculdu (2026-08-20 baa70fa4): model tek kareden ust uste IKI
    yanlis teshis koydu ("kulp havada duruyor", "iki karanlik delik var")
    ve ikincisinin onerdigi duzeltme hasari buyuttu. Baska bir oturumda
    (b2938bd0) kullanici sahneyi kendisi cevirip "ben cevirdim sen direkt
    al goruntu bak" demek zorunda kaldi — yani kameraman kullanici oldu.

    NEDEN ILK KARE HALA KULLANICININ ACISI. "Ayni seye baksinlar" kurali
    (bkz. yakala) bilincli bir karardi ve korunuyor; on ve ust ONA EK.
    Ikisi birlikte X-Y ve Y-Z iliskisini kapatiyor — "kulp govdeye degiyor
    mu" sorusunun cevabi tam olarak burada.

    NEDEN HER ZAMAN DEGIL. Uc kare ~3x token ve modelin uc resmi okumasi
    demek; hizli bir bakis icin gereksiz. Cagiran karar veriyor
    (bkz. conversation: once tek kare, cozulmediyse uc kare).

    Kamera GERI YUKLENIYOR: kullanicinin baktigi yer bizim yuzumuzden
    degismemeli. Yuklenemezse en azindan uyari birakiliyor. Geri yukleme
    `finally` icinde ve ONCESINDE animasyon kapatiliyor — gerekcesi asagida,
    "sacma bir yere gidiyor" sikayetinin sebebi tam olarak oydu.
    """
    try:
        import FreeCADGui as Gui

        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:
        log.uyari(f"cok acili yakalama yapilamadi: {e}")
        tek = yakala(genislik, yukseklik)
        return [tek] if tek else []

    kamera = None
    try:
        kamera = gorunum.getCamera()
    except Exception as e:
        log.uyari(f"kamera durumu okunamadi ({e}); acilar denenmeyecek")

    kareler: list[bytes] = []
    ilk = yakala(genislik, yukseklik)          # kullanicinin gordugu aci
    if ilk:
        kareler.append(ilk)

    if kamera is None:
        return kareler

    # ANIMASYON KAPATILIYOR. Sikayet: "3 acidan sonra sacma bir yere gidiyor,
    # kullanicinin ilk baktigi acida kalmiyor". Sebep: viewFront/viewTop
    # FreeCAD'de CANLANDIRMALI gecis yapar — kamera bir sure boyunca hareket
    # eder. setCamera ile eski aciyi geri koysak bile SUREN animasyon onu
    # tekrar hedefe (ust gorunume) tasiyor, yani geri yukleme sessizce
    # eziliyordu. Ayrica animasyon ortasinda alinan kare de yamuk aciyi
    # gosterir. Kapatmak ucuz: tek bayrak, gecisler aninda oluyor.
    animasyon = None
    try:
        animasyon = gorunum.isAnimationEnabled()
        gorunum.setAnimationEnabled(False)
    except Exception as e:                                       # noqa: BLE001
        # Surumde yoksa devam: geri yukleme yine de denenir.
        log.ayik(f"animasyon bayragi ayarlanamadi: {e}")

    try:
        for ad in ("viewFront", "viewTop"):
            try:
                getattr(gorunum, ad)()
                gorunum.fitAll()
                _cizimi_bitir()
                kare = yakala(genislik, yukseklik)
                if kare:
                    kareler.append(kare)
            except Exception as e:                               # noqa: BLE001
                log.uyari(f"{ad} yakalanamadi: {e}")
    finally:
        # GERI YUKLEME finally'de: aradaki her sey patlasa da kullanicinin
        # baktigi yer geri gelsin. Kullanicinin gorunumunu bozmak, gorsel
        # kontrolun kendisinden daha pahali bir hata.
        try:
            gorunum.setCamera(kamera)
            _cizimi_bitir()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"kamera geri yuklenemedi: {e}")
        if animasyon:
            try:
                gorunum.setAnimationEnabled(True)
            except Exception:                                    # noqa: BLE001
                pass

    return kareler


def yakala_yakin(adlar, genislik: int = GENISLIK, yukseklik: int = YUKSEKLIK,
                 cok_aci: bool = False) -> list[bytes]:
    """Kamerayi VERILEN NESNELERE yaklastirip yakalar.

    NEDEN VAR (olculdu, MANTIK 39). Tum model kadraja sigdiginda kare kaba
    kaliyor: 201 mm'lik gemi 900x640 karede ~4 piksel/mm demek, yani 0.6 mm
    kalinligindaki bir yelken 2 piksel. Model tam bu yuzden bir cakismayi
    goremedi. Cozunurlugu buyutmek uc kareyi ~4 kat pahalilastirir ve
    arkada kalan seyi yine gostermez; KAMERAYI YAKLASTIRMAK ayni token ile
    ~10 kat detay veriyor.

    `adlar`: FreeCAD IC ADLARI (Label degil). Bulunamayan ad sessizce
    atlanmaz — cagiran taraf hangilerinin bulundugunu bilsin diye uyari
    birakilir ve bulunanlarla devam edilir.

    Kamera §31.4'teki desenle korunuyor: animasyon KAPALI (canlandirmali
    gecis geri yuklemeyi eziyordu) ve geri yukleme `finally` icinde.
    Secim de geri aliniyor — kullanicinin secimini bozmak bizim isimiz
    degil.
    """
    try:
        import FreeCADGui as Gui

        gorunum = Gui.ActiveDocument.ActiveView
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"yakin cekim yapilamadi (GUI yok): {e}")
        return []

    try:
        import FreeCAD as App

        doc = App.ActiveDocument
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"yakin cekim: belge yok: {e}")
        return []

    nesneler = []
    for ad in adlar:
        o = doc.getObject(ad) if doc is not None else None
        if o is None:
            log.uyari(f"yakin cekim: '{ad}' adinda nesne yok, atlandi")
        else:
            nesneler.append(o)
    if not nesneler:
        return []

    kamera = None
    try:
        kamera = gorunum.getCamera()
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"kamera durumu okunamadi ({e}); yakin cekim denenmeyecek")
        return []

    animasyon = None
    try:
        animasyon = gorunum.isAnimationEnabled()
        gorunum.setAnimationEnabled(False)
    except Exception as e:                                       # noqa: BLE001
        log.ayik(f"animasyon bayragi ayarlanamadi: {e}")

    eski_secim = []
    kareler: list[bytes] = []
    try:
        try:
            eski_secim = Gui.Selection.getSelectionEx()
        except Exception:                                        # noqa: BLE001
            eski_secim = []
        Gui.Selection.clearSelection()
        for o in nesneler:
            Gui.Selection.addSelection(doc.Name, o.Name)

        # FreeCAD'in KENDI "secime yaklas" komutu. Yedegi bbox'tan kamera
        # kurmak degil — o surume gore degisen bir is; yedek, normal
        # fitAll'a dusup bunu SOYLEMEK.
        yaklasti = False
        try:
            Gui.SendMsgToActiveView("ViewSelection")
            yaklasti = True
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"ViewSelection calismadi ({e}); genel kareye dusuldu")
            try:
                gorunum.fitAll()
            except Exception:                                    # noqa: BLE001
                pass
        _cizimi_bitir()

        aci_listesi = [None]
        if cok_aci:
            aci_listesi = [None, "viewFront", "viewTop"]
        for aci in aci_listesi:
            if aci is not None:
                try:
                    getattr(gorunum, aci)()
                    if yaklasti:
                        Gui.SendMsgToActiveView("ViewSelection")
                    _cizimi_bitir()
                except Exception as e:                           # noqa: BLE001
                    log.uyari(f"{aci} (yakin) yakalanamadi: {e}")
                    continue
            kare = yakala(genislik, yukseklik)
            if kare:
                kareler.append(kare)
    finally:
        try:
            Gui.Selection.clearSelection()
            for s in eski_secim:
                try:
                    Gui.Selection.addSelection(s.Object)
                except Exception:                                # noqa: BLE001
                    pass
        except Exception:                                        # noqa: BLE001
            pass
        try:
            gorunum.setCamera(kamera)
            _cizimi_bitir()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"kamera geri yuklenemedi (yakin cekim): {e}")
        if animasyon:
            try:
                gorunum.setAnimationEnabled(True)
            except Exception:                                    # noqa: BLE001
                pass

    return kareler


def _cizimi_bitir() -> None:
    """Bekleyen gorunum guncellemesini EKRANA islet.

    saveImage OpenGL tamponundan okuyor; aci degistikten hemen sonra
    cagirilirsa henuz cizilmemis kareyi alabilir. Kamera geri yuklemesinden
    sonra da ayni sey: kullanici bir an eski/yeni arasi bir kare gorur.
    """
    try:
        import FreeCADGui as Gui

        Gui.updateGui()
    except Exception:                                            # noqa: BLE001
        pass


def _widget_ile_yakala() -> bytes | None:
    """saveImage calismazsa: 3B widget'in kendisini grab et.

    Yedek yol, cunku saveImage OpenGL tamponundan okuyor ve bazi surucu /
    uzak masaustu bilesimlerinde bos cikabiliyor. QWidget.grab() ekranda ne
    varsa onu alir - kalitesi daha dusuk ama hicbir seyden iyi.
    """
    try:
        import FreeCADGui as Gui
        from PySide import QtCore

        # ActiveView'in Qt widget'ina tasinabilir bir yol yok; ana pencerenin
        # merkezi alanini grab etmek calisan en basit yontem.
        mw = Gui.getMainWindow()
        if mw is None:
            return None
        resim = mw.centralWidget().grab()
        tampon = QtCore.QBuffer()
        tampon.open(QtCore.QIODevice.WriteOnly)
        if not resim.save(tampon, "PNG"):
            return None
        return bytes(tampon.data())
    except Exception as e:
        log.uyari(f"widget grab da basarisiz: {e}")
        return None
