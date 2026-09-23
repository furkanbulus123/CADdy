"""Executor'un islem (transaction) davranisini FreeCAD motorunda dogrular.

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_executor_fc.py

DIKKAT: freecadcmd, betikten SONRAKI argumanlari sys.argv'ye koymaz — onlari
acilacak dosya sanar. Bu yuzden bu betik arguman ALMAZ (3D_Models/LOG.md 5.5).

Sinadigi sey, planin R3 riski: "AI'in urettigi kod kac nesne uretirse uretsin
Ctrl+Z hepsini TEK adimda geri almali."
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Testler GERCEK LOG/ klasorune yazmasin (bkz. sohbet_log modul basligi):
# olculdu, suite her kosusta oraya ~10 dosya birakiyordu ve kullanicinin
# gercek oturum gunlukleriyle karisiyordu.
os.environ["CADDY_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

import FreeCAD as App

from caddy.execution.executor import CodeExecutor

gecti = basarisiz = 0
_SATIRLAR = []


def print(*a, **k):                                          # noqa: A001
    # freecadcmd swallows script output and always exits 0, so the lines
    # also go to tests/_son_executor.txt like the other suites.
    _SATIRLAR.append(" ".join(str(x) for x in a))


def kontrol(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("  OK   %s" % ad)
    else:
        basarisiz += 1
        print("  HATA %s   %s" % (ad, ek))


doc = App.newDocument("CaddyTest")
# Konsol modunda geri alma varsayilan olarak kapali olabilir; GUI'de aciktir.
doc.UndoMode = 1
ex = CodeExecutor()
ex.oturumu_ayarla("test1234")

print("1) tek islem / cok nesne")
s = ex.calistir(
    'a = doc.addObject("Part::Box", "Kutu1")\n'
    'a.Length = 10; a.Width = 10; a.Height = 10\n'
    'b = doc.addObject("Part::Box", "Kutu2")\n'
    'b.Length = 5\n',
    "iki kutu")
kontrol("calisti", s.basarili, s.hata_izi)
kontrol("2 nesne eklendi", len(s.eklenen) == 2, s.eklenen)
kontrol("belgede 2 nesne", len(doc.Objects) == 2, len(doc.Objects))
kontrol("TEK undo girdisi", len(doc.UndoNames) == 1, doc.UndoNames)
kontrol("undo adi dogru", doc.UndoNames and doc.UndoNames[0] == "AI: iki kutu",
        doc.UndoNames)

print("2) tek Ctrl+Z hepsini geri aliyor")
doc.undo()
doc.recompute()
kontrol("belge bosaldi", len(doc.Objects) == 0, [o.Name for o in doc.Objects])

print("3) hatali kod -> islem IPTAL, belge degismiyor")
doc.redo()          # kutulari geri getir, temiz bir baslangic noktasi olsun
doc.recompute()
onceki = len(doc.Objects)
onceki_undo = len(doc.UndoNames)
s2 = ex.calistir(
    'doc.addObject("Part::Box", "Yarim")\n'
    'raise ValueError("bilerek patlat")\n',
    "patlayan")
kontrol("basarisiz bildirildi", not s2.basarili)
kontrol("traceback var", "ValueError" in s2.hata_izi, s2.hata_izi[-200:])
kontrol("traceback KAYNAK SATIRINI gosteriyor",
        "bilerek patlat" in s2.hata_izi, s2.hata_izi[-300:])
kontrol("yarim nesne belgede KALMADI", len(doc.Objects) == onceki,
        [o.Name for o in doc.Objects])
kontrol("bos undo girdisi eklenmedi", len(doc.UndoNames) == onceki_undo,
        doc.UndoNames)

print("4) sozdizimi hatasi islem bile acmiyor")
onceki_undo = len(doc.UndoNames)
s3 = ex.calistir("bu ( gecerli python degil :::", "bozuk")
kontrol("basarisiz", not s3.basarili)
kontrol("SyntaxError", "SyntaxError" in s3.hata_izi, s3.hata_izi[-200:])
kontrol("undo yigini buyumedi", len(doc.UndoNames) == onceki_undo, doc.UndoNames)

print("5) yumusak hata: olu sekil politikasi")
s4 = ex.calistir(
    'import Part\n'
    'f = doc.addObject("Part::Feature", "OluSekil")\n'
    'f.Shape = Part.makeBox(3, 3, 3)\n',
    "olu sekil")
kontrol("calisti (hata degil)", s4.basarili, s4.hata_izi)
kontrol("politika ihlali uyarisi var",
        any("dead shape" in u for u in s4.uyarilar), s4.uyarilar)

print("6) acik belge yoksa duzgun mesaj")
App.closeDocument(doc.Name)
s5 = ex.calistir('doc.addObject("Part::Box", "X")', "belgesiz")
kontrol("basarisiz", not s5.basarili)
kontrol("anlasilir mesaj", "document" in s5.hata_izi.lower(), s5.hata_izi)


print("7) mesajsiz istisnada ozet BOS KALMIYOR")
# OLCULEN SENARYO: gunlukteki tek hatanin ozeti kelimenin tam anlamiyla
# "HATA — No error" yaziyordu (OCC istisnalari mesajsiz gelebiliyor).
# Model dogru teshisi ancak kendi print'lerinden cikarabildi.
from caddy.execution.executor import _hata_ozeti

_iz_bos = ('Traceback (most recent call last):\n'
           '  File "<string>", line 3, in <module>\n'
           '    kati = s1.fuse(s2)\n'
           'Part.OCCError: No error')
o = _hata_ozeti(_iz_bos)
print("   ozet:", o)
kontrol("'No error' oldugu gibi verilmiyor", o.strip() != "No error", o)
kontrol("istisna TIPI ozette", "OCCError" in o, o)
kontrol("sucu isaret eden satir ozette", "fuse" in o, o)

_iz_dolu = ('Traceback (most recent call last):\n'
            '  File "<string>", line 1, in <module>\n'
            'RuntimeError: belge bulunamadi')
o2 = _hata_ozeti(_iz_dolu)
kontrol("mesaji olan istisnada davranis DEGISMEDI",
        o2 == "RuntimeError: belge bulunamadi", o2)
kontrol("bos izde comeliyor", _hata_ozeti("") == "error", _hata_ozeti(""))

# UCTAN UCA: belge kapali oldugu icin ex.calistir burada OCC'ye hic
# ulasmiyordu; ozeti gercekten uretmek icin mesajsiz istisnayi kendimiz
# firlatiyoruz — olculen sekliyle (str(e) == "No error").
doc2 = App.newDocument("OzetBelge")
App.setActiveDocument(doc2.Name)
ex2 = CodeExecutor()
s6 = ex2.calistir(
    'class BosIstisna(Exception):\n'
    '    def __str__(self): return "No error"\n'
    'raise BosIstisna()\n', "mesajsiz istisna")
print("   uctan uca ozet:", s6.ozet)
kontrol("uctan uca: ozet sadece 'No error' degil",
        s6.ozet.replace("ERROR — ", "").strip() != "No error", s6.ozet)
kontrol("uctan uca: istisna tipi gorunuyor", "BosIstisna" in s6.ozet, s6.ozet)
App.closeDocument(doc2.Name)

print("8) baski_kontrol KATI nesnede de cevap veriyor")
# OLCULEN KAYIP (LOG/2026-08-24_5f9d2adc.txt 14:20:44): model
# `baski_kontrol(sonuc)`u birlestirmenin sonucuna cagirdi ve tek aldigi
# cevap "mesh degil, kontrol edilmedi" oldu. Oysa dilimleyiciye giden sey
# zaten mesh; soru anlamliydi ve cevaplanabilirdi.
import io
from contextlib import redirect_stdout

from caddy.execution.executor import _baski_kontrol_yap

doc3 = App.newDocument("BaskiKati")
App.setActiveDocument(doc3.Name)
import Part as _Part

k = doc3.addObject("Part::Feature", "SaglamKati")
k.Shape = _Part.makeBox(20, 20, 20)
doc3.recompute()

_yakala = io.StringIO()
with redirect_stdout(_yakala):
    sonuc_k = _baski_kontrol_yap(k)
_c = _yakala.getvalue()
print("   cikti:", _c.strip().replace("\n", " | ")[:200])
kontrol("'mesh degil, kontrol edilmedi' DEMIYOR",
        "kontrol edilmedi" not in _c, _c)
kontrol("kati oldugunu ve mesh urettigini SOYLUYOR",
        "solid" in _c and "was generated" in _c, _c)
kontrol("gercek verdikt veriyor", "print-ready" in _c, _c)
kontrol("saglam kutu EVET cikiyor", "print-ready = YES" in _c, _c)
kontrol("doner deger de dogru", sonuc_k is True, sonuc_k)

# Sekli olmayan nesne hala durustce reddediliyor.
bos = doc3.addObject("App::FeaturePython", "Sekilsiz")
doc3.recompute()
_yakala2 = io.StringIO()
with redirect_stdout(_yakala2):
    _baski_kontrol_yap(bos)
kontrol("ne mesh ne kati olanda durustce duruyor",
        "could not be checked" in _yakala2.getvalue(), _yakala2.getvalue())
App.closeDocument(doc3.Name)

print("N) asama dokumu — 17.1 saniyenin nereye gittigini soyleyen sey")
# Olculdu (LOG/2026-08-25_dc91d6d7.txt, 10:05:15): tek bir Part::Box uretmek
# 17.1 sn surdu, gunlukte yalnizca TOPLAM sure vardi ve sebep bulunamadi.
from caddy.execution.executor import YAVAS_ESIGI, isit          # noqa: E402

doc4 = App.newDocument("CaddyAsama")
doc4.UndoMode = 1
ex4 = CodeExecutor()
ex4.oturumu_ayarla("asama")
s_h = ex4.calistir('doc.addObject("Part::Box", "Olculen")\n', "asama olcumu")
kontrol("calisti", s_h.basarili, s_h.hata_izi)
kontrol("asamalar dolduruldu", bool(s_h.asamalar), s_h.asamalar)
for _ad in ("open transaction", "attach observers", "prepare", "exec", "recompute",
            "close"):
    kontrol("asama var: %s" % _ad, _ad in s_h.asamalar, sorted(s_h.asamalar))
kontrol("asamalarin toplami sure_sn'ye esit",
        abs(sum(s_h.asamalar.values()) - s_h.sure_sn) < 0.01,
        (sum(s_h.asamalar.values()), s_h.sure_sn))
# HIZLI turda dokum YAZILMAZ: her satira yazmak gunlugu bogar.
kontrol("hizli turda dokum bos", s_h.asama_metni() == "",
        s_h.asama_metni())
# Yavas tur nasil gorunuyor: gunlukteki 17.1 saniyelik tur uydurulup
# dokumun gercekten sucluyu ONE yazdigi sinaniyor.
from caddy.execution.executor import CalismaSonucu               # noqa: E402

_yavas = CalismaSonucu(basarili=True, sure_sn=17.1, asamalar={
    "open transaction": 0.01, "attach observers": 0.00, "prepare": 0.30,
    "exec": 16.70, "recompute": 0.08, "close": 0.01})
_d = _yavas.asama_metni()
kontrol("yavas turda dokum yaziliyor", bool(_d), _d)
kontrol("en pahali asama BASTA", _d.startswith("exec 16.70 s"), _d)
kontrol("hazirla da gorunuyor", "prepare 0.30 s" in _d, _d)
kontrol("gurultu asamalari elenmis", "attach observers" not in _d, _d)

# Patlayan kod: exec asamasi hic kaydedilmez ama toplam yine tutmali.
s_p = ex4.calistir('raise ValueError("patlat")\n', "patlayan asama")
kontrol("patlayan turda da asamalar var", bool(s_p.asamalar), s_p.asamalar)
kontrol("patlayan turda toplam yine tutuyor",
        abs(sum(s_p.asamalar.values()) - s_p.sure_sn) < 0.01,
        (sum(s_p.asamalar.values()), s_p.sure_sn))

kontrol("esik makul (0 degil, sonsuz degil)", 0.5 <= YAVAS_ESIGI <= 10.0,
        YAVAS_ESIGI)
_isinma = isit()
kontrol("isit() calisiyor ve sure donduruyor",
        isinstance(_isinma, float) and _isinma >= 0.0, _isinma)
kontrol("isitma sonrasi hazirla'nin importlari hazir",
        all(_m in sys.modules for _m in ("Part", "Draft", "Mesh")),
        [m for m in ("Part", "Draft", "Mesh") if m not in sys.modules])
App.closeDocument(doc4.Name)

# --- cakisma_kontrol isim alaninda mi (MANTIK 39) ------------------------
# Model bu deseni logda IKI KEZ elle yazdi ve ancak kullanici soyledikten
# sonra. Artik hazir; isim alanina bagli olmazsa kod "NameError" alir.
print("\n9) cakisma_kontrol isim alaninda")
doc5 = App.newDocument("CakismaNS")
ex5 = CodeExecutor()
ex5.oturumu_ayarla("cakisma01")
s_ck = ex5.calistir(
    'a = doc.addObject("Part::Box", "CA")\n'
    'b = doc.addObject("Part::Box", "CB")\n'
    'b.Placement.Base.x = 5\n'
    'doc.recompute()\n'
    'r = cakisma_kontrol(a, b)\n'
    'print("GECIS SAYISI", len(r["gecisler"]))\n', "cakisma")
kontrol("cakisma_kontrol cagrilabildi", s_ck.basarili, s_ck.hata_izi[-300:])
kontrol("ciktisi modele donuyor", "GECIS SAYISI 1" in (s_ck.cikti or ""),
        s_ck.cikti)
# Blok cakismayi KENDI yazdirdi; dogrulama taramasi ayni cifti BULGU
# olarak TEKRARLAMAZ (olculdu, LOG/2026-08-31_f5a6a5ac.txt: ayni sayi tek
# istemde iki kez gidiyordu). Bastirma SESSIZ degil: olcum satiri soyluyor.
kontrol("bildirilen gecis BULGU olarak tekrarlanmiyor",
        s_ck.dogrulama is not None
        and not any("intersects" in str(b)
                    for b in s_ck.dogrulama.bulgular),
        [str(b) for b in (s_ck.dogrulama.bulgular if s_ck.dogrulama else [])])
kontrol("bastirma dururstce yaziliyor",
        s_ck.dogrulama is not None
        and any("already written" in o for o in s_ck.dogrulama.olcumler),
        s_ck.dogrulama.olcumler if s_ck.dogrulama else [])

# Kayit TEK BLOKLUK: sonraki blok cakisma_kontrol cagirmazsa tarama yine
# bulguyu yazar. Yoksa bir kez bildirilen cift sonsuza dek susardi.
ex5.oturumu_ayarla("cakisma02")
s_ck2 = ex5.calistir('doc.getObject("CB").Placement.Base.x = 4\n'
                     'doc.recompute()\n', "cakisma tekrar")
kontrol("sonraki blokta bulgu geri geliyor",
        s_ck2.dogrulama is not None
        and any("intersects" in str(b)
                for b in s_ck2.dogrulama.bulgular),
        [str(b) for b in (s_ck2.dogrulama.bulgular if s_ck2.dogrulama else [])])
App.closeDocument(doc5.Name)

print("\n%d gecti, %d basarisiz" % (gecti, basarisiz))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_son_executor.txt"), "w", encoding="utf-8") as _f:
    _f.write("\n".join(_SATIRLAR) + "\n")
if basarisiz:
    sys.exit(1)
