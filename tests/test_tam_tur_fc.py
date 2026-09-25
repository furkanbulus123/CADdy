"""M1+M2 tam turu, ARAYUZSUZ - ConversationController uzerinden.

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_tam_tur_fc.py

Widget yok ama gercek bir Qt olay dongusu var, yani su zincirin tamami
sinaniyor:

    QProcess ile claude.exe baslatma          (planin R2 riski)
    -> stdin'den istem
    -> UTF-8 NDJSON cerceveleme
    -> stream-json ayristirma: asama + CANLI metin parcalari
    -> ```freecad-python blogu ayiklama
    -> canli belgede transaction icinde exec
    -> tek temiz geri alma                    (planin R3 riski)
    -> token sayaci ve SOHBET GUNLUGU dosyasi

GERCEK bir claude cagrisi yapar; internet ve oturum acilmis olmasi gerekir.
Yaklasik 10-40 sn surer.
"""

import os
import sys
import time
import traceback

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

import FreeCAD as App
from PySide import QtCore

from caddy.conversation import ConversationController

RAPOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_son_tur.txt")
_satirlar = []
gecti = basarisiz = 0


def yaz(s):
    _satirlar.append(str(s))
    try:
        print(s)
    except Exception:
        pass


def kontrol(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        yaz("  OK   %s" % ad)
    else:
        basarisiz += 1
        yaz("  HATA %s   %s" % (ad, ek))


app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(sys.argv)

doc = App.newDocument("TamTur")
doc.UndoMode = 1

ctl = ConversationController()

# --- gozlemciler ---
gorulen = {"asama": [], "parca": 0, "metin": "", "bloklar": [],
           "bilgi": "", "ipucu": "", "mesajlar": []}

ctl.asama.connect(lambda a: gorulen["asama"].append(a))
ctl.akis_parcasi.connect(
    lambda p: (gorulen.__setitem__("parca", gorulen["parca"] + 1),
               gorulen.__setitem__("metin", gorulen["metin"] + p)))
ctl.oneri.connect(lambda b: gorulen["bloklar"].append(b))
ctl.mesaj.connect(lambda r, m: gorulen["mesajlar"].append((r, m)))
ctl.bilgi_satiri.connect(
    lambda t, i: (gorulen.__setitem__("bilgi", t),
                  gorulen.__setitem__("ipucu", i)))

gorulen_nabiz = []
ctl.dusunce_olcusu.connect(gorulen_nabiz.append)

# --- 0) NABIZ: aga cikmadan, sentetik satirlarla -------------------------
# Neden burada: gercek cagride model kisa dusunurse nabiz hic gelmeyebilir,
# o zaman test "gecti" der ama kablo kopuk olur. Zor bir istekte 89 nabiz
# geliyor ve bunlarin atilmasi, panelin dakikalarca donmus gorunmesinin
# ta kendisiydi — bu yuzden kablo DETERMINISTIK olarak sinaniyor.
yaz("0) NABIZ KABLOSU (sentetik, ag yok)")
_t = ctl.transport
_t._mesgul = True                      # tur suruyormus gibi davran
_t._saat.stop()
try:
    _t._satir_geldi('{"type":"system","subtype":"thinking_tokens",'
                    '"estimated_tokens":250,"estimated_tokens_delta":150}')
    kontrol("thinking_tokens -> dusunce_olcusu", gorulen_nabiz == [250],
            gorulen_nabiz)
    kontrol("nabiz asamayi 'dusunuyor' yapiyor",
            gorulen["asama"][-1:] == ["dusunuyor"], gorulen["asama"])
    # ASIL DUZELTME: her satir sessizlik saatini bastan kuruyor. Toplam
    # sureye bakan eski saat, 166 sn suren saglikli bir turu kesiyordu.
    kontrol("gelen satir sessizlik saatini kurdu", _t._saat.isActive())

    _t._satir_geldi('{"type":"system","subtype":"status","status":"requesting"}')
    kontrol("status/requesting asama bildiriyor",
            gorulen["asama"][-1:] == ["istek gonderildi"], gorulen["asama"])
    _t._satir_geldi('{"type":"kimsenin_bilmedigi_yeni_tip","x":1}')
    kontrol("bilinmeyen tip patlatmiyor", True)
finally:
    _t._saat.stop()
    _t._mesgul = False
gorulen_nabiz[:] = []
gorulen["asama"][:] = []

yaz("0b) HIZ AYARLARI")
from caddy import config as _cfg
from caddy.transport.transport import SISTEM_SOZLESMESI as _sz

kontrol("model listesi opus+sonnet",
        [m[0] for m in _cfg.MODELLER] == ["opus", "sonnet"], _cfg.MODELLER)
# Kalite sozu TAM etikette duruyor; kutuda gorunen KISA etiket panelin
# asgari genisligini dusurmek icin kisaldi (bkz. test_panel_fc.py).
kontrol("model tam etiketleri kalite soyluyor",
        all("quality" in m[2] for m in _cfg.MODELLER),
        [m[2] for m in _cfg.MODELLER])
kontrol("kisa etiketler gercekten kisa",
        all(len(m[1]) < 14 for m in _cfg.MODELLER),
        [m[1] for m in _cfg.MODELLER])
kontrol("baglam siniri kisa gosterimi", _cfg.baglam_siniri_kisa() == "1M",
        _cfg.baglam_siniri_kisa())
_eski = _cfg.model()
_cfg.modeli_ayarla("sonnet")
kontrol("model secimi kalici", _cfg.model() == "sonnet", _cfg.model())
_cfg.yaz("Model", "uydurma-model")
kontrol("gecersiz model varsayilana duser", _cfg.model() == "opus", _cfg.model())
_cfg.modeli_ayarla(_eski)
kontrol("eski model geri kondu", _cfg.model() == _eski, _cfg.model())

# --- HARCAMA ile BAGLAM ayri sayilar mi -------------------------------
# OLCULEN HATA: gunlukte baglam 86953 -> 179116 -> 92600 diye sicradi.
# Sebep: `result.usage` TURUN TAMAMINI topluyor; tur iki API cagrisi
# yaptiysa ayni baglam iki kez sayiliyordu ve panelde bu sayi yaziyordu.
from caddy.transport.transport import TurSonucu as _TS

_iki_cagri = _TS(tk_girdi=1200, tk_cikti=800, tk_onbellek_okuma=85000,
                 tk_onbellek_yazma=6000, api_cagrisi=2, tk_son_istem=92000)
yaz("   iki cagrili tur: toplam=%d baglam=%d (son istem %d)"
    % (_iki_cagri.tk_toplam, _iki_cagri.tk_baglam, _iki_cagri.tk_son_istem))
kontrol("harcama tum cagrilari topluyor (dogru davranis)",
        _iki_cagri.tk_toplam == 93000, _iki_cagri.tk_toplam)
kontrol("BAGLAM son istemin boyu, turun toplami DEGIL",
        _iki_cagri.tk_baglam == 92000, _iki_cagri.tk_baglam)
kontrol("baglam artik harcamadan KUCUK (sicrama kalkti)",
        _iki_cagri.tk_baglam < _iki_cagri.tk_toplam)

# Alan yoksa (eski CLI / eksik usage) eski davranisa duser - yanlis ama
# hic sayi olmamasindan iyi.
_eski_cli = _TS(tk_girdi=1200, tk_cikti=800, tk_onbellek_okuma=85000,
                tk_onbellek_yazma=6000)
kontrol("son istem yoksa toplama geri dusuyor",
        _eski_cli.tk_baglam == 92200, _eski_cli.tk_baglam)
kontrol("api sayaci varsayilan 0", _eski_cli.api_cagrisi == 0)

# Sureyi asil kisaltan sey model degil, istegin bolunmesi + belirsizligin
# ucuz bir soruyla kapatilmasi. Sozlesmenin bu maddeleri OLCULEREK secildi
# (bkz. MANTIK.md 8b/8c), o yuzden kazayla silinmelerini istemiyoruz.
for _ad, _parca in [
    ("kisa soru turu", "ONE short question"),
    ("ayni soruyu tekrar sormama", "never re-ask"),
    ("kac adim + hangi adim bildirimi", "how many steps"),
    ("yalnizca 1. adim", "STEP 1 ONLY"),
    ("varsayimlari acik etme", "state the assumptions"),
    ("adim buyuklugu tavani", "How big may one step be"),
    # caddy_gelisim.txt kayip 2: genel "belirsizse sor" maddesi zaten
    # vardi ve %12 tetikleniyordu. Tetikleyen sey ADI KONMUS desen, o
    # yuzden kapsam maddesi ayrica yaziliyor — silinmesin.
    ("kapsam belirsizligi maddesi", "SCOPE requests"),
    ("kapsamda once onay, kod sonra", "wait for one confirmation"),
    # kayip 5: gorsel kontrolun kendisi kisilmadi, onay turu kisildi.
    ("gorsel onayi kisa olsun", "ONE short line and stop"),
    # MANTIK 17: deterministik dogrulama katmani. Modelin KOSMAYAN bir
    # kontrolu gecmis sayip "dogrulandi" dememesi bu maddeye bagli.
    ("dogrulama raporu maddesi", "VERIFICATION REPORT"),
    ("yalnizca kosan kontrol iddia edilir", "Claim only what the report"),
    ("ters kati ve acik kabuk adiyla aniliyor", "reversed solid"),
    # MANTIK 19: olculdu, modelin "Ctrl+Z ile geri don" demesi 13 dakika
    # kaybettirdi ve bir kez de "geri alindigini varsayip" kod uretti.
    ("geri alma maddesi", "UNDOING YOUR OWN WORK"),
    ("kullaniciya Ctrl+Z dedirtme", "Do NOT tell the user to press"),
    ("reddedilirse varsayma", "NEVER assume the undo happened"),
    # MANTIK 32/33: sozlesme baskiya gomulmustu; kullanici "belki
    # basmayacagim, en basta sorsun" dedi. Amac sorusu ve amaca gore
    # kurallar kazayla silinirse CADdy yine herkesi 3B yaziciya sokar.
    ("amac sorusu maddesi", "WHAT IS THIS DESIGN FOR"),
    ("amac sorusu bir kez sorulur", "Ask this ONCE per session"),
    ("secenekler harfli", "(f) visual"),
    ("son sik diger", "(g) other"),
    ("amaca gore kurallar", "RULES PER PURPOSE"),
    ("CNC ic kose yaricapi", "internal vertical corner"),
    ("sac sabit kalinlik", "constant thickness everywhere"),
    ("kalip cikma acisi", "Draft >= 1 deg"),
    ("FEA sadelestirme", "defeature what does not carry load"),
    ("sadece gorselde imalat uyarisi YOK",
     "manufacturability is NOT your concern here"),
    ("bicim amaca gore", "THE FORMAT FOLLOWS THE PURPOSE"),
    ("CNC'ye mesh gonderme", "MESH IS THE WRONG ANSWER"),
    ("AP242 icin OCC yolu", "write.step.schema"),
    ("bulgular amaca gore okunur", "Read the findings THROUGH THE PURPOSE"),
    ("tekrar eden bulgu tek satir", "Never repeat the same"),
    # MANTIK 39: model UC KAREYE bakip "cakisma yok" dedi ve yanildi.
    # Temas/cakisma sorusu goruntuye SORULMAYACAK; bu maddeler silinirse
    # ayni hataya donulur.
    ("goruntu neyi kanitlayamaz", "WHAT A PICTURE CANNOT PROVE"),
    ("cakisma_kontrol adiyla aniliyor", "cakisma_kontrol"),
    ("olcmeden cakisma onaylanmaz", "is a guess, and so is any claim"),
    ("onay cumlesi olculene dayanir", "may only claim what you actually"),
    # MANTIK 34: arastirmayla derinlestirilen kurallar. Bunlarin her biri
    # gunlukte YANLIS yapilabilecek, sayisi olmadan tetiklenmeyen sey.
    ("baskida katman yonu zayif", "ANISOTROPY"),
    ("recinede iki tahliye deligi", "TWO drain holes"),
    ("SLS toz kacis deligi", "escape holes"),
    ("CNC varsayilan tolerans ISO 2768-m", "ISO 2768-m"),
    ("toleransi yalnizca gereken yerde sik", "ONLY on the two or"),
    ("sac buküm boşaltmasi", "bend relief"),
    ("sac K-faktoru soylenir", "K-factor"),
    ("kalip goblek kurallari", "BOSSES"),
    ("FEM burada gercekten kosuyor", "ObjectsFem builds the analysis"),
    ("kuvvet birimi tuzagi", "silently means 1 N"),
    ("cozucu sonucu elle dogrulanir", "sanity-checked"),
    ("vida maddesi", "THREADS AND FASTENERS"),
    ("M4 altinda basili dis guvenilmez", "below M4 is unreliable"),
    ("SheetMetal tezgahi yok", "no SheetMetal workbench"),
    # Kod blogu sayisi karari (2026-08-27): olcum bloklari YOGUN olsun,
    # yazan bloklar bagimsizsa en fazla uc tane, kareler ise kisilsin.
    ("olcum blogu yogun olmali", "five or ten calls in ONE"),
    ("ilk bakista iyice olc", "MEASURE IT THOROUGHLY"),
    ("yazan blok TEK", "exactly ONE per reply"),
    ("gereksiz blok bir dugmedir", "a button the user has to press"),
    # 2026-08-28: gorsel sistemi KAPATILDI (deney: 4/6/8 blokluk uc kosu,
    # kaliteyi ayiran sey goruntu degil ADIM SAYISI cikti). Sozlesmede
    # goruntuyle ilgili tek madde kalmamali, yoksa model olmayan bir sey
    # ister ve her turda reddedilir.
    ("goruntu olmadigi soyleniyor", "YOU CANNOT SEE THE 3D VIEW"),
    ("adim sayisi olculdu", "SMALL STEPS BEAT BIG ONES"),
    ("sekiz adim en iyisiydi", "eight was the best"),
    ("suphedeysen ikiye bol", "make it two"),
    ("plani daha ince kes", "Cut the job FINER"),
    ("bulgular tek tek karsilanir", "ANSWER EVERY FINDING ONE BY ONE"),
    ("toplu aklama yasak", "is not"),
    ("yutulma orani anlatiliyor", "FULLY BURIED"),
    ("yazan blok kendi kanitini basar", "END EVERY WRITING BLOCK WITH ITS OWN PROOF"),
    ("tek blok cok is yapabilir", "one block may do"),
    ("odak bicimi tavsiye ediliyor", "check_overlap(focus=obj)"),
    ("tuketilmis nesneler eleniyor", "hidden raw material"),
    # PLAN S8 / MANTIK 46: bu iki yardimci sozlesmede ANLATILMAZSA model
    # varliklarini bilmez ve elle yazmaya devam eder — eklemenin tamami
    # bosa gider. Bu yuzden metnin dusmesi teste takilmali.
    ("saglik anlatiliyor", "health()"),
    ("isValid'in yetmedigi soyleniyor", "isValid() ALONE IS NOT ENOUGH"),
    ("simetri anlatiliyor", "symmetry(obj)"),
]:
    kontrol("sozlesme: " + _ad, _parca in _sz)
kontrol("zaman asimi sessizlige bakiyor",
        "SILENCE" in (_cfg.zaman_asimi.__doc__ or "").upper(),
        _cfg.zaman_asimi.__doc__)
yaz("     zaman asimi: %d sn sessizlik" % _cfg.zaman_asimi())

yaz("0b2) KONSOL YAKALAMA — FreeCAD'in turuncu satirlari (ag yok)")
# Kullanicinin istegi: "uyari ve haber kodlarini da AI gorsun, turuncu
# kisimlari". redirect_stdout bunlari YAKALAMIYOR - App.Console.PrintWarning
# C++ tarafinda. Gozlemci gercekten calisiyor mu, burada sinaniyor.
_ks = ctl.executor.calistir(
    'App.Console.PrintWarning("test uyarisi 1\\n")\n'
    'App.Console.PrintError("test hatasi 1\\n")\n'
    'kutu = doc.addObject("Part::Box", "KonsolTest")\n',
    "konsol yakalama testi")
kontrol("kod calisti", _ks.basarili, _ks.hata_izi[-300:])
kontrol("konsol UYARISI yakalandi",
        any("test uyarisi 1" in u for u in _ks.konsol_uyari), _ks.konsol_uyari)
kontrol("konsol HATASI yakalandi",
        any("test hatasi 1" in u for u in _ks.konsol_hata), _ks.konsol_hata)
kontrol("ozette uyari sayisi gorunuyor", "warning" in _ks.ozet, _ks.ozet)
_mm = _ks.modele_metin()
kontrol("modele giden metinde FreeCAD uyarisi var", "FreeCAD warning" in _mm)
kontrol("modele giden metinde FreeCAD hatasi var", "FreeCAD ERROR" in _mm)
yaz("     ozet: %s" % _ks.ozet)

# Gozlemci COZULMUS olmali: sonraki calistirmaya sizmasin.
_ks2 = ctl.executor.calistir('pass\n', "bos calistirma")
kontrol("gozlemci cozuldu (sizinti yok)",
        not _ks2.konsol_uyari and not _ks2.konsol_hata,
        (_ks2.konsol_uyari, _ks2.konsol_hata))
doc.undo(); doc.undo(); doc.recompute()

yaz("0c) GORSEL KONTROL — isaret ayristirma ve emniyet (ag yok)")
from caddy import conversation as _cv
from caddy import gorunum as _gor

_isaret = _cv._GORSEL_ISARET
kontrol("kendi satirinda tetikler",
        _isaret.search("Kulaklari ekledim.\nGORSEL-KONTROL") is not None)
kontrol("Turkce yazim da tetikler",
        _isaret.search("bitti\nGÖRSEL-KONTROL\n") is not None)
kontrol("cumle icinde TETIKLEMEZ",
        _isaret.search("bunun icin gorsel-kontrol gerekmiyor") is None)
# SOZLESMENIN TAVANI — Windows'un komut satiri siniri (~32 767 karakter).
# Sozlesme `--append-system-prompt` ile ARGUMAN olarak gidiyor; olculdu
# (MANTIK 35): 32 000 karakter calisiyor, 40 000 karakterde CLI hic
# baslamiyor ("Argument list too long") ve CADdy sessizce cevapsiz kalir.
# 28 000 tavani, diger argumanlara ve gelecekteki eklemelere pay birakiyor.
# Daha fazlasi gerekiyorsa yer workspace/CLAUDE.md (dosya, siniri yok).
kontrol("sozlesme Windows arguman sinirinin altinda",
        len(_sz) < 28000, "%d karakter" % len(_sz))
yaz("     sozlesme boyu: %d karakter (~%d token)" % (len(_sz), len(_sz) // 3))
# GORSEL SISTEMI KAPALI (2026-08-28). Sozlesmede goruntuyle ilgili TEK bir
# madde kalmamali: kalirsa model olmayan bir sey ister ve her turda
# reddedilir — bosa giden bir tur. Isaret ayristirma kodu duruyor (yukarida
# sinaniyor) cunku acmaya karar verirsek geri gelecek.
kontrol("sozlesmede gorsel maddesi KALMADI", "GORSEL-KONTROL" not in _sz)
kontrol("sozlesme 'resim yok' diyor", "YOU CANNOT SEE THE 3D VIEW" in _sz)
kontrol("gorsel anahtari kapali", _cv.GORSEL_ACIK is False)
kontrol("dongu siniri 2", _cv._GORSEL_SINIR == 2, _cv._GORSEL_SINIR)
# freecadcmd'de GUI yok; yakalanabilir_mi() PATLAMADAN False donmeli.
kontrol("GUI yokken yakalanabilir_mi False", _gor.yakalanabilir_mi() is False)
kontrol("GUI yokken yakala() None", _gor.yakala() is None)

# Isaret KULLANICIYA gosterilmemeli - protokol sozcugu, mesaj degil.
_temiz = _isaret.sub("", "Kulaklari ekledim.\nGORSEL-KONTROL").strip()
kontrol("isaret metinden temizleniyor", _temiz == "Kulaklari ekledim.", _temiz)

# OLCULEN KAYIP: model "...baskiya hazir — GORSEL-KONTROL" yazdi, isaret
# kendi satirinda olmadigi icin host SESSIZCE hicbir sey gondermedi ve
# model bunu ogrenemedi. 5 istekten 1'i boyle dustu.
_satir_sonu = "Sorun yok, ikisi de gorunur ve baskiya hazir — GORSEL-KONTROL"
kontrol("SATIR SONUNDAKI isaret artik tetikliyor",
        _isaret.search(_satir_sonu) is not None, _satir_sonu)
_uc = _isaret.search("buyuk degisiklik oldu: GORSEL-KONTROL 3")
kontrol("satir sonundaki 3'lu de tetikliyor ve UC ACI olarak okunuyor",
        _uc is not None and _uc.group(1) == "3",
        _uc.group(1) if _uc else None)
kontrol("temizlenince geriye anlamli cumle kaliyor",
        _isaret.sub("", _satir_sonu).strip().endswith("hazir"),
        _isaret.sub("", _satir_sonu).strip())
kontrol("metnin ORTASINDA hala tetiklemiyor",
        _isaret.search("GORSEL-KONTROL yazarsam resim gelir, simdi gerek yok")
        is None)

# YAKIN CEKIM (MANTIK 39). Tum model kadraja sigdiginda kare ~4 piksel/mm
# veriyor; ince iste kamera nesneye yaklasmali.
_y1 = _isaret.search("bitti\nGORSEL-KONTROL YAKIN FlokUst")
kontrol("YAKIN <ad> tetikliyor ve ad okunuyor",
        _y1 is not None and _y1.group(2) == "FlokUst",
        _y1.group(2) if _y1 else None)
_y2 = _isaret.search("buyuk is: GÖRSEL-KONTROL 3 YAKIN FlokUst,YelkenPruva")
kontrol("3 + YAKIN birlikte okunuyor",
        _y2 is not None and _y2.group(1) == "3"
        and _y2.group(2) == "FlokUst,YelkenPruva",
        (_y2.group(1), _y2.group(2)) if _y2 else None)
kontrol("YAKIN'siz isaret hala calisiyor (yakin adi bos)",
        _uc is not None and _uc.group(2) is None,
        _uc.group(2) if _uc else "eslesme yok")
kontrol("en fazla 3 nesne alinir", _cv._YAKIN_AZAMI == 3, _cv._YAKIN_AZAMI)
# Adlar FreeCAD IC ADI: bosluklu bir sey yazilirsa isaret HIC eslesmemeli
# ki cumlenin devami yanlislikla nesne adi sanilmasin. O halde de kanal
# sessiz kalmaz: anahtar yakalanir ve modele not gider (asagida).
kontrol("bosluklu ad kaliba UYMUYOR",
        _isaret.search("GORSEL-KONTROL YAKIN Flok Ust") is None)
kontrol("...ama anahtar yine de goruluyor (sessiz kalinmaz)",
        _cv._GORSEL_ANAHTAR.search("GORSEL-KONTROL YAKIN Flok Ust")
        is not None)

# Tetiklemedigi durumda SESSIZ kalmamali: anahtar var ama yerinde degil.
kontrol("anahtar kalibi ortadaki gecisi goruyor",
        _cv._GORSEL_ANAHTAR.search(
            "GORSEL-KONTROL yazarsam resim gelir") is not None)
ctl._gorsel_uyari = True
_orj_gonder = ctl.transport.tur_gonder
_yakalanan = {}
ctl.transport.tur_gonder = lambda istem, gorsel=None: _yakalanan.update(
    {"istem": istem})
try:
    ctl.gonder("kod calisti", kullanici_mi=False)
finally:
    ctl.transport.tur_gonder = _orj_gonder
_istek = _yakalanan.get("istem", "")
kontrol("dusen istek bir sonraki OTOMATIK isteme not olarak biniyor",
        _cv._GORSEL_UYARI in _istek, repr(_istek[-160:]))
kontrol("not bir kez binip temizleniyor", ctl._gorsel_uyari is False)
# Ek tur acilmadiginin kaniti: not, ZATEN gidecek olan istemin icinde,
# kendi <request> blogunda degil.
kontrol("not EK TUR acmiyor (mevcut isteme bindi)",
        _istek.count("<request>") == 1 and "kod calisti" in _istek,
        _istek.count("<request>"))
# Kullanici mesaji bayragi sifirlar - eski bir not yeni sohbete sizmasin.
ctl._gorsel_uyari = True
ctl.transport.tur_gonder = lambda istem, gorsel=None: _yakalanan.update(
    {"istem": istem})
try:
    ctl.gonder("yeni istek", kullanici_mi=True)
finally:
    ctl.transport.tur_gonder = _orj_gonder
kontrol("kullanici mesajinda not EKLENMIYOR",
        "GORSEL-KONTROL" not in _yakalanan.get("istem", ""),
        _yakalanan.get("istem", "")[:80])

# GORSEL KAPALI. Model yine de isteyebilir; host sessiz kalmamali —
# ciktiyi gondermeli ve "goruntuye bakmis gibi konusma" demeli. Sessiz
# kalinsaydi model basarili bir calistirma hakkinda SIFIR geri bildirim
# alirdi (olculen kayip, bkz. _gorsel_yerine_cikti).
_msj = []
ctl.mesaj.connect(lambda r, m: _msj.append((r, m)))
_gonderilen = {}
_orj_g = ctl.transport.tur_gonder
ctl.transport.tur_gonder = lambda istem, **k: _gonderilen.setdefault(
    "istem", istem)
try:
    ctl._gorseli_gonder("hacim: 8000 mm3")
finally:
    ctl.transport.tur_gonder = _orj_g
kontrol("gorsel kapaliyken KARE gonderilmiyor", not ctl._gorsel_tur,
        ctl._gorsel_tur)
kontrol("ama kod CIKTISI yine de modele gidiyor",
        "8000" in _gonderilen.get("istem", ""),
        _gonderilen.get("istem", "")[:120])
kontrol("modele 'goruntuye bakmis gibi konusma' deniyor",
        "could NOT be sent" in _gonderilen.get("istem", ""),
        _gonderilen.get("istem", "")[:200])
ctl._gorsel_tur = 0
_msj.clear()

# ---- OLCULEN KAYIP: butce CIKTIYI da yutuyordu ----------------------
# LOG/2026-08-24_3ad4cef1.txt 12:03:26 — basarili bir calistirmadan sonra
# gunluge HICBIR sey dusmedi, ne cikti ne gorsel. Cikti bu cagriya
# BINDIRILIYOR; gorsel yolu erken donunce "dolgu alani: 3080 mm2 |
# cakisma: 0.00 mm2" da beraberinde gitti ve model basarili bir
# calistirma hakkinda sifir geri bildirim aldi.
yaz("0d) GORSEL BUTCESI — cikti ONA BINIYOR, onunla birlikte yutulmamali")

_gunluk_satirlari = []
_orj_sistem = ctl.gunluk.sistem
ctl.gunluk.sistem = lambda m: _gunluk_satirlari.append(m)
_yakalanan.clear()
ctl.transport.tur_gonder = lambda istem, gorsel=None: _yakalanan.update(
    {"istem": istem, "gorsel": gorsel})
try:
    ctl._gorsel_tur = _cv._GORSEL_SINIR
    ctl._gorseli_gonder("dolgu alani: 3080 mm2 | cakisma: 0.00 mm2")
finally:
    ctl.transport.tur_gonder = _orj_gonder
    ctl.gunluk.sistem = _orj_sistem
    ctl._gorsel_tur = 0

_ist = _yakalanan.get("istem", "")
kontrol("butce dolsa da CIKTI modele gidiyor", "3080 mm2" in _ist,
        repr(_ist[:200]))
kontrol("gorsel gonderilmedigi SOYLENIYOR (resme bakmis gibi konusmasin)",
        "could NOT be sent" in _ist, repr(_ist[:300]))
kontrol("gorsel gercekten eklenmedi", not _yakalanan.get("gorsel"))
kontrol("bastirma GUNLUGE yaziliyor (log'da sebep gorunsun)",
        any("IMAGE NOT SENT" in m for m in _gunluk_satirlari),
        _gunluk_satirlari)
kontrol("ciktinin gonderildigi de gunlukte",
        any("OUTPUT sent anyway" in m for m in _gunluk_satirlari),
        _gunluk_satirlari)

# Cikti YOKSA bos bir tur harcanmamali.
_yakalanan.clear()
ctl.transport.tur_gonder = lambda istem, gorsel=None: _yakalanan.update(
    {"istem": istem})
try:
    ctl._gorsel_tur = _cv._GORSEL_SINIR
    ctl._gorseli_gonder()
finally:
    ctl.transport.tur_gonder = _orj_gonder
    ctl._gorsel_tur = 0
kontrol("cikti yoksa BOS tur harcanmiyor", "istem" not in _yakalanan,
        _yakalanan)

# ---- SAYAC NEYI SAYIYOR: "bak-yine bak" mi, "bak-degistir-yine bak" mi --
# Opus 11:46 / 11:53 / 11:58'de bakti; her bakis arasinda GERI-AL verip yeni
# kod yazdi — istedigimiz dongunun ta kendisi — ve dorduncude cezalandirildi.
yaz("0e) GORSEL SAYACI — arada KOD kostuysa zincir degil, ilerleme")

ctl._gorsel_tur = _cv._GORSEL_SINIR
_blok = type("B", (), {"kod": "x = 1 + 1", "baslik": "sessiz is"})()
# Cikti YOK: yoksa _ciktiyi_yolla gercek bir tur baslatir ve asagidaki
# canli tur testini bozar (olculdu — bu testi ilk yazista tam bu oldu).
ctl.transport.tur_gonder = lambda istem, gorsel=None: None
try:
    ctl.blogu_calistir(_blok)
finally:
    ctl.transport.tur_gonder = _orj_gonder
kontrol("kod kosunca gorsel sayaci SIFIRLANIYOR", ctl._gorsel_tur == 0,
        ctl._gorsel_tur)

# Ama koruma kaybolmadi: arada is yokken sinir hala kesiyor. Bassiz
# ortamda 3B pencere olmadigi icin sayac kendiliginden artmaz — sinir
# dalini dogrudan surmek gerekiyor.
# Dongu emniyeti KODU duruyor ama gorsel kapaliyken ona hic varilmiyor:
# kapali dal en basta donuyor. Acildiginda korumanin geri gelmesi icin
# sabitin yerinde oldugunu ve sayacin kirletilmedigini sinariyoruz.
_msj.clear()
ctl._gorsel_tur = _cv._GORSEL_SINIR
ctl._gorseli_gonder()
kontrol("kapali dal sayaci KIRLETMIYOR",
        ctl._gorsel_tur == _cv._GORSEL_SINIR, ctl._gorsel_tur)
kontrol("dongu emniyeti sabiti yerinde duruyor (acilinca gerekli)",
        _cv._GORSEL_SINIR == 2, _cv._GORSEL_SINIR)
ctl._gorsel_tur = 0
_msj.clear()

# ---- GUNLUK BASLIGINDA MODEL ADI ------------------------------------
# Iki modeli karsilastirmaya baslayinca (ayni tavsan, once Sonnet sonra
# Opus) her log dosyasinin tepesindeki "model : (bilinmiyor)" gercek bir
# engel oldu: dosyaya bakip hangi modelle calisildigi anlasilmiyordu.

# ---- KARE SAYISINA HOST KARAR VERIR ---------------------------------
# OLCULDU (LOG/2026-08-27_9564dc71.txt): karar modeldeyken 30 gorsel
# gonderiminin 27'si (%90) uc kareydi ve sozlesmeye "uc kare varsayilan
# degil" yazildiktan SONRA da oran %90 kaldi. Kural tutmayinca kurali
# uygulayacak yere tasidik: _kac_kare.
yaz("0h) KARE SAYISI — karar host'ta")
ctl._gorsel_tur = 0
ctl._son_eklenen = []
ctl._gorsel_cok = True
_cok, _not = ctl._kac_kare()
kontrol("model istedi ama yeni nesne yok -> TEK kare", _cok is False, _cok)
kontrol("indirimin sebebi modele soyleniyor", "one was sent" in _not,
        _not[:80])
kontrol("model yerine ne yapacagi da soyleniyor",
        "check_overlap" in _not, _not[-120:])

ctl._son_eklenen = ["Kutu"]
ctl._gorsel_cok = True
_cok, _not = ctl._kac_kare()
kontrol("yeni nesne eklendiyse UC kare", _cok is True, _cok)
kontrol("hak verilince not YOK", _not == "", _not)

# Ikinci bakis: ilk kare soruyu kapatmadi.
ctl._son_eklenen = []
ctl._gorsel_tur = 1
ctl._gorsel_cok = False
_cok, _not = ctl._kac_kare()
kontrol("arka arkaya ikinci bakista UC kare", _cok is True, _cok)

# Model HIC istemediyse ve ortada yeni bir sey yoksa tek kare, not da yok:
# istemedigi bir seyin gerekcesini yazmak gurultudur.
ctl._gorsel_tur = 0
ctl._gorsel_cok = False
_cok, _not = ctl._kac_kare()
kontrol("istemeyene tek kare, not YOK", _cok is False and _not == "",
        (_cok, _not))

# Calisan blok EKLENEN nesneleri _son_eklenen'e yaziyor mu.
_blok2 = type("B", (), {"kod": 'k = doc.addObject("Part::Box", "KareKutu")',
                        "baslik": "ek"})()
#
# AYRI BELGEDE kosuyor, ve bu iki olculmus kazadan sonra boyle: (1)
# `TamTur` belgesinde kosturunca asagidaki GERCEK cagride model kutuyu
# gordu, "zaten tam istediginiz kup var" deyip HIC kod yazmadi ve blok
# testleri dustu; (2) kutuyu silmek de paylasilan geri alma yiginina
# fazladan girdi biraktı, "TEK undo girdisi" kontrolu kirildi. Test,
# sinadigi sistemin durumunu kirletmemeli.
_kd = App.newDocument("KareSayisi")
ctl.transport.tur_gonder = lambda istem, gorsel=None: None
try:
    ctl.blogu_calistir(_blok2)
finally:
    ctl.transport.tur_gonder = _orj_gonder
    App.closeDocument(_kd.Name)
    App.setActiveDocument(doc.Name)
kontrol("calisan blok eklenen nesneyi kaydediyor",
        "KareKutu" in ctl._son_eklenen, ctl._son_eklenen)
ctl._son_eklenen = []
ctl._gorsel_tur = 0

# GORSEL KAPALIYKEN hak BIRIKTIRILMIYOR. Bassiz "3B pencere yok" dalinda
# hakki saklamak dogruydu (kullanici pencereyi acinca ilk bakisini alsin).
# Kapali sistemde saklanacak bir sey yok: kare hic gelmeyecek, birikmis
# hak yalnizca acildigi gun patlar.
ctl._son_eklenen = ["Kutu"]
ctl._gorsel_tur = 0
ctl._gorsel_cok = True
ctl._gorseli_gonder()
kontrol("gorsel kapaliyken hak biriktirilmiyor",
        ctl._son_eklenen == [], ctl._son_eklenen)
# Temizlik gonderim yolunda: sayac artmissa kare cikmistir.
kontrol("gonderilmeyen bakis sayaci da artirmiyor", ctl._gorsel_tur == 0,
        ctl._gorsel_tur)
ctl._son_eklenen = []
ctl._gorsel_cok = False

yaz("0g) EFOR — dusunme miktari GERCEKTEN komut satirina gidiyor mu")
# OLCULDU (3 tekrar, sonnet, ayni istem):
#   low 37 · 43 · 37 -> ortanca 37.0 sn ·  2774 cikti token
#   (varsayilan)     -> ortanca 116.1 sn ·  9820
#   high 123·130·149 -> ortanca 129.6 sn · 11408   (varsayilandan YAVAS)
# Gecikmenin %91-94'u dusunme oldugu icin asil hiz kolu bu.
_eski_efor = _cfg.efor()
try:
    _cfg.eforu_ayarla("low")
    _a = ctl.transport._argv()
    kontrol("efor secilince --effort GECIYOR", "--effort" in _a, _a)
    kontrol("dogru deger geciyor", _a[_a.index("--effort") + 1] == "low", _a)

    _cfg.eforu_ayarla("")
    _a = ctl.transport._argv()
    kontrol("BOS DIZE secilince bayrak HIC gecmiyor (CLI varsayilani)",
            "--effort" not in _a, _a)

    _cfg.eforu_ayarla("high")
    kontrol("listede olmayan deger varsayilana DUSUYOR (high cikarildi)",
            _cfg.efor() == "", _cfg.efor())
finally:
    _cfg.eforu_ayarla(_eski_efor)

kontrol("iki secenek var", len(_cfg.EFORLAR) == 2,
        [e[0] for e in _cfg.EFORLAR])
kontrol("model kutusu kisaldi (yer efor kutusuna gitti)",
        all(len(m[1]) <= 8 for m in _cfg.MODELLER),
        [m[1] for m in _cfg.MODELLER])
kontrol("model kutusunun KALITE notu ipucunda duruyor",
        all("quality" in m[2] for m in _cfg.MODELLER),
        [m[2] for m in _cfg.MODELLER])

# OLCULEN HATA: --model ve --effort surec BASLARKEN veriliyor, surec ise
# turlar boyunca ayakta kaliyor. Yani oturum ortasinda model degistirmek
# HICBIR SEY YAPMIYORDU — kutunun ipucu "sonraki mesajdan itibaren
# gecerli" diyordu ve bu dogru degildi.
kontrol("transport ayar degisimini uygulayabiliyor",
        hasattr(ctl.transport, "ayarlar_degisti"))
ctl.transport._mesgul = False
kontrol("BOSTA iken ayar uygulaniyor", ctl.transport.ayarlar_degisti() is True)
ctl.transport._mesgul = True
kontrol("TUR ORTASINDA akan yanit KESILMIYOR",
        ctl.transport.ayarlar_degisti() is False)
kontrol("ama unutulmuyor — tur bitince uygulanacak",
        ctl.transport._yeniden_baslat_gerek is True)
ctl.transport._mesgul = False
ctl.transport._yeniden_baslat_gerek = False

yaz("0f) GUNLUK BASLIGI — 'model : (bilinmiyor)' duzeliyor mu")

import tempfile
from pathlib import Path

from caddy.sohbet_log import SohbetGunlugu

_gecici = Path(tempfile.mkdtemp(prefix="caddy_log_"))
_g = SohbetGunlugu(_gecici)
_g.oturum_ac("abcdef1234")
# BASLIK TEMBEL: oturum acmak diske DOKUNMUYOR (MANTIK 37 — konusulmayan
# oturum 298 baytlik hayalet dosya birakiyordu). Dosya ilk gercek kayitla
# doguyor.
kontrol("oturum acmak dosya olusturmuyor", not list(_gecici.glob("*.txt")),
        list(_gecici.glob("*.txt")))
_g.kullanici("ilk mesaj")
_dosya = next(_gecici.glob("*.txt"))
kontrol("ilk kayitla dosya dogdu", _dosya.exists(), _dosya)
kontrol("ON KABUL: baslik once '(unknown)' yaziyor",
        "(unknown)" in _dosya.read_text(encoding="utf-8"))
_bas = _dosya.read_text(encoding="utf-8")
kontrol("baslikta EFOR satiri da var", "effort  :" in _bas,
        _bas.splitlines()[:7])
kontrol("efor satiri gercek ayari yaziyor",
        any(x[2] in _bas for x in _cfg.EFORLAR if x[0] == _cfg.efor()),
        [s for s in _bas.splitlines() if s.startswith("efor")])
_g.ai("merhaba", model="claude-opus-5", sure_sn=1.0)
_icerik = _dosya.read_text(encoding="utf-8")
kontrol("ilk yanittan sonra baslikta GERCEK model var",
        "model   : claude-opus-5" in _icerik,
        _icerik.splitlines()[:6])
kontrol("'(unknown)' kalmadi", "(unknown)" not in _icerik,
        _icerik.splitlines()[:6])
_g.ai("ikinci", model="claude-sonnet-5", sure_sn=1.0)
_icerik2 = _dosya.read_text(encoding="utf-8")
kontrol("baslik BIR KEZ yaziliyor (sonraki turlar bozmuyor)",
        "model   : claude-opus-5" in _icerik2, _icerik2.splitlines()[:6])
kontrol("tur satirlari yine de kendi modelini yaziyor",
        "claude-sonnet-5" in _icerik2, _icerik2[-300:])

dongu = QtCore.QEventLoop()
ctl.transport.tur_bitti.connect(lambda s: (gorulen.__setitem__("sonuc", s),
                                           dongu.quit()))

emniyet = QtCore.QTimer()
emniyet.setSingleShot(True)
emniyet.timeout.connect(dongu.quit)
emniyet.start(240_000)

ISTEK = "Kenar uzunlugu 10 mm olan bir kup yap."
yaz("istek: %s" % ISTEK)
yaz("claude cagriliyor, bekle...")

ctl.gonder(ISTEK)
dongu.exec()

s = gorulen.get("sonuc")
kontrol("yanit geldi (zaman asimi yok)", s is not None)

if s is None:
    yaz("")
    yaz("%d gecti, %d basarisiz" % (gecti, basarisiz + 1))
    with open(RAPOR, "w", encoding="utf-8") as f:
        f.write("\n".join(_satirlar) + "\n")
    sys.exit(1)

kontrol("hata bayragi yok", not s.hata_mi, s.aciklama[:400])
kontrol("session_id alindi", bool(s.oturum), s.oturum)
kontrol("model bildirildi", bool(s.model), s.model)
yaz("     sure %.1f sn · %s · %d token" % (s.sure_ms / 1000.0, s.model,
                                           s.tk_toplam))

yaz("1) CANLI AKIS")
kontrol("asama bildirimleri geldi", len(gorulen["asama"]) > 0, gorulen["asama"])
kontrol("metin parca parca aktı", gorulen["parca"] >= 2, gorulen["parca"])
kontrol("akan metin sonucla ortusuyor",
        gorulen["metin"].strip()[:40] in s.metin, gorulen["metin"][:80])

yaz("2) TOKEN SAYIMI (dolar yerine bu gosteriliyor)")
kontrol("cikti token > 0", s.tk_cikti > 0, s.tk_cikti)
kontrol("toplam = 4 bilesenin toplami",
        s.tk_toplam == (s.tk_girdi + s.tk_cikti + s.tk_onbellek_okuma
                        + s.tk_onbellek_yazma), s.tk_toplam)
kontrol("bilgi satirinda 'token' yazıyor", "token" in gorulen["bilgi"],
        gorulen["bilgi"])
kontrol("bilgi satirinda DOLAR YOK", "$" not in gorulen["bilgi"],
        gorulen["bilgi"])
kontrol("dolar aciklamasi ipucunda kaldi",
        "subscription" in gorulen["ipucu"].lower(), gorulen["ipucu"][:120])
yaz("     bilgi satiri: %s" % gorulen["bilgi"])

yaz("3) SOHBET GUNLUGU (1 session = 1 dosya)")
dosya = ctl.gunluk.dosya
kontrol("gunluk dosyasi olustu", dosya is not None and os.path.isfile(str(dosya)),
        dosya)
if dosya and os.path.isfile(str(dosya)):
    icerik = open(str(dosya), encoding="utf-8").read()
    kontrol("kullanici mesaji yazildi", "USER" in icerik and ISTEK in icerik)
    kontrol("AI yaniti yazildi", "AI" in icerik)
    kontrol("oturum kimligi basligi var", s.oturum[:8] in icerik)
    # Kok dizin CADDY_LOG_DIR ile degistirilebiliyor (MANTIK 37: testler
    # kullanicinin gercek LOG/ klasorunu kirletmesin). Testte o degisken
    # tests/_gunlukler'i gosteriyor; sinanan sey gunlugun DOGRU KOKE
    # yazdigi.
    kontrol("gunluk yapilandirilan koke yaziyor",
            os.path.dirname(str(dosya)) == os.environ["CADDY_LOG_DIR"],
            str(dosya))
    yaz("     %s  (%d bayt)" % (dosya, len(icerik)))

    # Ayni oturum icin tekrar cagirmak YENI DOSYA ACMAMALI
    ctl.gunluk.oturum_ac(s.oturum)
    kontrol("ayni oturum -> ayni dosya", str(ctl.gunluk.dosya) == str(dosya),
            ctl.gunluk.dosya)

yaz("4) KOD BLOGU VE CALISTIRMA")
kontrol("en az bir kod blogu", len(gorulen["bloklar"]) >= 1, repr(s.metin[:400]))

if gorulen["bloklar"]:
    b = gorulen["bloklar"][0]
    kontrol("sozlesmeli etiketle geldi", b.guvenilir)
    yaz("     --- uretilen kod ---")
    for satir in b.kod.strip().splitlines():
        yaz("     | %s" % satir)

    kontrol("olu sekil uretmedi",
            "Part.show(" not in b.kod and "Part::Feature" not in b.kod)
    kontrol("kendi transaction'ini acmadi",
            "openTransaction" not in b.kod and "setActiveTransaction" not in b.kod)
    kontrol("newDocument cagirmadi", "newDocument" not in b.kod)

    calisma = {}
    ctl.calisma_sonucu.connect(lambda c: calisma.__setitem__("c", c))
    ctl.blogu_calistir(b)
    c = calisma.get("c")

    kontrol("kod calisti", c is not None and c.basarili,
            (c.hata_izi[-500:] if c else "sonuc yok"))
    kontrol("nesne eklendi", c and len(c.eklenen) >= 1, c.eklenen if c else None)
    kontrol("TEK undo girdisi", len(doc.UndoNames) == 1, doc.UndoNames)

    if c and c.basarili:
        try:
            sekilli = [o for o in doc.Objects
                       if getattr(o, "Shape", None) is not None
                       and not o.Shape.isNull()]
            bb = sekilli[0].Shape.BoundBox
            olcu = (round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3))
            yaz("     olcu: %s" % (olcu,))
            kontrol("10x10x10 mm", olcu == (10.0, 10.0, 10.0), olcu)
        except Exception:
            kontrol("olcu okundu", False, traceback.format_exc(limit=2))

        # Calistirma da gunluge yazilmis olmali
        if dosya:
            icerik2 = open(str(dosya), encoding="utf-8").read()
            kontrol("calistirma gunluge yazildi", "RUN" in icerik2)
            kontrol("kod onerisi gunluge yazildi", "CODE" in icerik2)

        doc.undo()
        doc.recompute()
        kontrol("tek Ctrl+Z hepsini geri aldi", len(doc.Objects) == 0,
                [o.Name for o in doc.Objects])

yaz("5) KALICI SUREC — ikinci tur ayni surece gitmeli")
# Kullanicinin sorusu: "her mesajda baglaniyor yaziyor, bir kere baglansa
# olmaz mi?" Bu bolum cevabin DOGRULANMASI: surec ayakta kaldi mi, ve
# ikinci tur gercekten hizlandi mi.
kontrol("surec turdan sonra ayakta", ctl.transport._proc.calisiyor_mu())

gorulen["asama"][:] = []
_t0 = time.time()
dongu2 = QtCore.QEventLoop()
sonuc2 = {}
_b = ctl.transport.tur_bitti.connect(
    lambda s: (sonuc2.__setitem__("s", s), dongu2.quit()))
emniyet2 = QtCore.QTimer()
emniyet2.setSingleShot(True)
emniyet2.timeout.connect(dongu2.quit)
emniyet2.start(240_000)

ctl.gonder("Tek kelimeyle cevap ver: az once hangi nesneyi ekledin?")
dongu2.exec()
_gecen2 = time.time() - _t0

s2 = sonuc2.get("s")
kontrol("ikinci tur yanit verdi", s2 is not None and not s2.hata_mi,
        (s2.aciklama[:300] if s2 else "yanit yok"))
kontrol("surec hala ayni ve ayakta", ctl.transport._proc.calisiyor_mu())
kontrol("ikinci turda 'baglaniyor' YOK (yeniden baglanmadi)",
        "baglaniyor" not in gorulen["asama"], gorulen["asama"])
if s2:
    kontrol("oturum ayni kaldi", s2.oturum == s.oturum, (s.oturum, s2.oturum))
    kontrol("baglam olculuyor", s2.tk_baglam > 0, s2.tk_baglam)
    kontrol("baglam = toplam - cikti",
            s2.tk_baglam == s2.tk_toplam - s2.tk_cikti,
            (s2.tk_baglam, s2.tk_toplam, s2.tk_cikti))
    kontrol("baglam ikinci turda buyudu", s2.tk_baglam >= s.tk_baglam,
            (s.tk_baglam, s2.tk_baglam))
yaz("     tur 1: %.1f sn (soguk) · tur 2: %.1f sn (ayni surec)"
    % (s.sure_ms / 1000.0, _gecen2))
yaz("     bilgi satiri: %s" % gorulen["bilgi"])
kontrol("bilgi satirinda baglam var", "context" in gorulen["bilgi"],
        gorulen["bilgi"])
kontrol("bos blokta '0 kod blogu' yazmiyor",
        "0 kod" not in gorulen["bilgi"], gorulen["bilgi"])

ctl.transport.kapat()

yaz("")
yaz("%d gecti, %d basarisiz" % (gecti, basarisiz))
with open(RAPOR, "w", encoding="utf-8") as f:
    f.write("\n".join(_satirlar) + "\n")
if basarisiz:
    sys.exit(1)
