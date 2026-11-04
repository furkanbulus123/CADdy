"""Baski analizi, parametre taramasi ve teknik resim (baski.py, islem.tara,
cizim.py).

Arayuzsuz calisir:

    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecadcmd.exe" tests\\test_baski_fc.py

Uc yardimci BIRLESTIRILDI (yeni ad acilmadi): print_check(process=...),
wall_thickness() (z'siz = tum govde), place_on_bed(minimize_support=True).
Iki yeni yardimci: sweep() ve drawing(). Hepsi gercek calistirici uzerinden,
INGILIZCE adlarla cagriliyor — namespace baglamasi da sinaniyor.

Rapor dosyaya SATIR SATIR yaziliyor (MANTIK 14.5).
"""

import os
import re
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
os.environ["KEDICAD_LOG_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_gunlukler")

RAPOR = os.path.join(KOK, "tests", "_son_baski.txt")
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
        _yaz("  HATA %s   %s" % (ad, str(ek)[:500]))


def bolum(ad):
    _yaz("")
    _yaz("--- %s %s" % (ad, "-" * max(0, 56 - len(ad))))


import FreeCAD as App
import Part

from kedicad.execution.executor import CodeExecutor

_yaz("=" * 70)
_yaz("KediCAD baski analizi / tarama / teknik resim")
_yaz("=" * 70)

doc = App.newDocument("BaskiTest")
doc.UndoMode = 1
yurutucu = CodeExecutor()


def kos(kod, baslik="test"):
    s = yurutucu.calistir(kod, baslik)
    if not s.basarili:
        _yaz("       PATLADI: " + s.hata_izi.strip().splitlines()[-1])
    return s


def ekle(ad, sekil):
    o = doc.addObject("Part::Feature", ad)
    o.Shape = sekil
    doc.recompute()
    return o


# Bardak: 2 mm duvar, 2 mm taban. Ince: 0.8 mm duvar. T: alti 1500 mm2 sarkan.
ekle("Bardak", Part.makeCylinder(20, 40).cut(
    Part.makeCylinder(18, 40, App.Vector(0, 0, 2))))
ekle("Ince", Part.makeCylinder(20, 30).cut(
    Part.makeCylinder(19.2, 32, App.Vector(0, 0, -1))))
ekle("Kup", Part.makeBox(20, 20, 20))
ekle("T", Part.makeBox(10, 10, 20, App.Vector(15, 15, 0)).fuse(
    Part.makeBox(40, 40, 5, App.Vector(0, 0, 20))).removeSplitter())
ekle("Minik", Part.makeBox(0.2, 0.2, 0.2))


# ===================================================== 1. wall_thickness
bolum("wall_thickness — z'siz: tum govde, katida da")

s = kos("d = wall_thickness(doc.getObject('Bardak'))\n"
        "print('p05:', round(d['p05'], 2), 'min:', round(d['en_ince'], 2))\n"
        "print('ornekleme sn: %.2f' % d['sure'])",
        "bardak duvari")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("katida calisti (mesh'e cevirip)", "solid meshed" in s.cikti, s.cikti)
kontrol("p05 ~2 mm (gercek duvar 2.0)",
        "p05: 1.9" in s.cikti or "p05: 2.0" in s.cikti, s.cikti)
kontrol("en ince noktanin KONUMUNU veriyor", "thinnest" in s.cikti
        and " at (" in s.cikti, s.cikti)
kontrol("kac olcum yaptigini soyluyor", "measurements" in s.cikti, s.cikti)
_m = re.search(r"ornekleme sn: ([\d.]+)", s.cikti)
kontrol("ornekleme butcede (<= 1.6 sn)", _m is not None
        and float(_m.group(1)) <= 1.6, s.cikti)

s = kos("wall_thickness(doc.getObject('Ince'))", "ince duvar")
# Kati 0.1 mm sapmayla mesh'e cevriliyor: ic/dis cokgenler duvari ~0.03 mm
# inceltiyor (olculdu: 0.8 mm duvar -> p05 0.774). Cikti bunu soyluyor.
_m = re.search(r"p05 ([\d.]+) mm", s.cikti)
kontrol("0.8 mm duvari buluyor (mesh payi icinde)", _m is not None
        and 0.72 <= float(_m.group(1)) <= 0.82, s.cikti)

s = kos("print(wall_thickness(doc.getObject('Bardak'), z=20))",
        "eski kip: z ile")
kontrol("z kipi katida durustce reddediyor, z'siz kipi gosteriyor",
        "call it without z for a solid" in s.cikti, s.cikti)


# ===================================================== 2. print_check
bolum("print_check(process=...) — DfAM bolumu")

s = kos("print('donen:', print_check(doc.getObject('Kup')))", "kup FDM")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("varsayilan surec FDM", "print analysis for FDM" in s.cikti, s.cikti)
kontrol("limitin KAYNAGINI soyluyor", "text-to-cad process table" in s.cikti,
        s.cikti)
kontrol("kupte duvar PASS", "PASS   wall" in s.cikti, s.cikti)
kontrol("kupte sarkma yok", "nothing steeper than 45" in s.cikti, s.cikti)
kontrol("olculemeyenleri NOT MEASURED diye yaziyor",
        "NOT MEASURED: min hole" in s.cikti, s.cikti)
kontrol("kup hazir: True", "donen: True" in s.cikti, s.cikti)

s = kos("print('donen:', print_check(doc.getObject('Ince'), process='FDM'))",
        "ince FDM")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("0.8 mm duvar FDM'de FAIL", "FAIL" in s.cikti, s.cikti)
kontrol("yeniden tasarim talimati: konum + hedef",
        "thicken the wall near (" in s.cikti and ">= 1.2 mm" in s.cikti,
        s.cikti)
kontrol("FAIL donus degerine yansiyor", "donen: False" in s.cikti, s.cikti)

s = kos("print('donen:', print_check(doc.getObject('Ince'), process='resin'))",
        "ince SLA")
kontrol("takma ad: resin -> SLA", "print analysis for SLA" in s.cikti, s.cikti)
kontrol("SLA'da 0.8 mm REVIEW (destekliye yeter, desteksize degil)",
        "REVIEW" in s.cikti and "FAIL" not in s.cikti, s.cikti)
kontrol("SLA'da donus True", "donen: True" in s.cikti, s.cikti)

s = kos("print_check(doc.getObject('T'))", "T FDM")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("sarkmayi buldu", "SUPPORT overhangs past 45" in s.cikti, s.cikti)
kontrol("alan ~1500 mm2", "1500 mm2" in s.cikti or "1.5e+03" in s.cikti,
        s.cikti)
kontrol("bolgenin konumunu veriyor", "region" in s.cikti and "around (" in
        s.cikti, s.cikti)
kontrol("daha iyi yonelimi oneriyor (+Z asagi)",
        "ORIENT +Z side down" in s.cikti, s.cikti)
kontrol("nasil uygulanacagini soyluyor",
        "minimize_support=True" in s.cikti, s.cikti)

s = kos("print_check(doc.getObject('T'), process='SLS')", "T SLS")
kontrol("tozda sarkma uygulanmiyor", "not applicable for SLS" in s.cikti,
        s.cikti)
kontrol("hapsolan toz NOT MEASURED", "Trapped powder" in s.cikti, s.cikti)

s = kos("print_check(doc.getObject('Minik'))", "birim")
kontrol("birim suphesi", "UNITS SUSPECT" in s.cikti, s.cikti)

s = kos("print_check(doc.getObject('Kup'), process='lazer')", "bilinmeyen")
kontrol("bilinmeyen sureci listeyle reddediyor",
        "unknown process" in s.cikti and "FDM" in s.cikti, s.cikti)


# ===================================================== 3. place_on_bed
bolum("place_on_bed(minimize_support=True)")

s = kos("place_on_bed(doc.getObject('T'), minimize_support=True)\n"
        "b = doc.getObject('T').Shape.BoundBox\n"
        "print('zmin:', round(b.ZMin, 3), 'zmax:', round(b.ZMax, 3))",
        "T cevir")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("+Z asagi cevirdi", "turned +Z side down" in s.cikti, s.cikti)
kontrol("destek 0'a indi", "-> 0 mm2" in s.cikti, s.cikti)
kontrol("tablada (zmin 0)", "zmin: 0.0" in s.cikti or "zmin: -0.0" in s.cikti,
        s.cikti)
s = kos("t = doc.getObject('T')\nprint_check(t)", "T yeniden")
kontrol("yeni yonelimde sarkma YOK", "nothing steeper than 45" in s.cikti,
        s.cikti)

s = kos("place_on_bed(doc.getObject('Kup'), minimize_support=True)", "kup")
kontrol("zaten en iyisiyse dokunmuyor, SOYLUYOR",
        "already needs the least support" in s.cikti, s.cikti)

s = kos("place_on_bed(doc.getObject('Kup'))", "eski yol")
kontrol("varsayilan yol degismedi (en genis duz yuz)",
        "placed on the bed" in s.cikti and "rotated" in s.cikti, s.cikti)


# ===================================================== 4. sweep
bolum("sweep — modelin hangi degerde kirildigi")

s = kos("dimension_table(r=2)\n"
        "k = doc.addObject('Part::Box', 'Kutu')\n"
        "c = doc.addObject('Part::Cylinder', 'Silindir')\n"
        "c.Height = 20\n"
        "c.Placement.Base = Vector(5, 5, -5)\n"
        "bind(c, 'Radius', 'Olculer.r')\n"
        "cut = doc.addObject('Part::Cut', 'Delik')\n"
        "cut.Base = k\n"
        "cut.Tool = c\n"
        "k.Visibility = False\n"
        "c.Visibility = False\n"
        "doc.recompute()", "kurulum")
kontrol("kurulum calisti", s.basarili, s.hata_izi)

s = kos("r = sweep('Olculer.r', 1, 8, steps=8)\n"
        "print('ok sayisi:', sum(x['ok'] for x in r))\n"
        "print('geri:', doc.getObject('Silindir').Radius.Value)", "tara")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("8 adim kostu", "8 steps" in s.cikti, s.cikti)
kontrol("kucuk degerler OK", "    1: OK" in s.cikti, s.cikti)
kontrol("buyuk degerler BROKEN", "BROKEN" in s.cikti, s.cikti)
kontrol("calistigi araligi soyluyor", "works for:" in s.cikti, s.cikti)
kontrol("ORIJINAL DEGER GERI GELDI", "geri: 2.0" in s.cikti, s.cikti)
kontrol("geri geldigini soyluyor", "original value restored" in s.cikti,
        s.cikti)

s = kos("sweep('Olculer.yok', 1, 2)", "olmayan alias")
kontrol("olmayan alias'i soyluyor", "no alias" in s.cikti, s.cikti)
s = kos("sweep('Silindir.Radius', 1, 2)", "ifadeye bagli ozellik")
kontrol("ifadeye bagli ozelligi reddediyor, kaynagi gosteriyor",
        "driven by the expression" in s.cikti, s.cikti)
s = kos("sweep('Kutu.Length', 5, 20, steps=4)\n"
        "print('geri:', doc.getObject('Kutu').Length.Value)", "ozellik")
kontrol("ozellik taramasi calisti", "4 steps" in s.cikti, s.cikti)
kontrol("ozellik geri geldi", "geri: 10.0" in s.cikti, s.cikti)
s = kos("sweep('r', 1, 3, steps=3)", "salt alias")
kontrol("noktasiz alias tablolarda bulunuyor", "Olculer.r" in s.cikti,
        s.cikti)


# ===================================================== 5. drawing
bolum("drawing — TechDraw teknik resim")

ekle("Blok", Part.makeBox(60, 40, 20).cut(
    Part.makeCylinder(5, 30, App.Vector(30, 20, -5))))
_dxf = os.path.join(KOK, "tests", "_gunlukler", "_cizim_test.dxf")
os.makedirs(os.path.dirname(_dxf), exist_ok=True)
if os.path.exists(_dxf):
    os.remove(_dxf)
s = kos("p = drawing(doc.getObject('Blok'), path=r'%s', material='AlMg3')\n"
        "print('sayfa:', p.TypeId)" % _dxf, "blok resmi")
_yaz("       " + s.cikti.strip().replace("\n", "\n       "))
kontrol("sayfa olustu", "sayfa: TechDraw::DrawPage" in s.cikti, s.cikti)
kontrol("genislik 60", "width (front): 60 mm" in s.cikti, s.cikti)
kontrol("yukseklik 20", "height (front): 20 mm" in s.cikti, s.cikti)
kontrol("derinlik 40", "depth (top): 40 mm" in s.cikti, s.cikti)
kontrol("delik capi 10", "hole x1: 10 mm" in s.cikti, s.cikti)
kontrol("DXF yazildi", os.path.isfile(_dxf) and os.path.getsize(_dxf) > 0,
        s.cikti)
kontrol("eksiklerini soyluyor", "NOT INCLUDED" in s.cikti, s.cikti)
_tpl = doc.getObject("Blok_Template")
_alan = dict(_tpl.EditableTexts) if _tpl else {}
kontrol("antet: malzeme yazildi", _alan.get("part_material") == "AlMg3", _alan)
kontrol("antet: sablonun sahte adi silindi",
        "Nemesis" not in str(_alan.values()), _alan)

s = kos("drawing(doc.getObject('Blok'), path=r'C:\\yok\\a.pdf')", "pdf basiz")
kontrol("PDF'in arayuz istedigini DURUSTCE soyluyor",
        "needs the FreeCAD GUI" in s.cikti, s.cikti)

import Mesh
_m = doc.addObject("Mesh::Feature", "MeshParca")
_m.Mesh = Mesh.createBox(10, 10, 10)
doc.recompute()
s = kos("drawing(doc.getObject('MeshParca'))", "mesh")
kontrol("mesh'te reddediyor", "needs a solid object" in s.cikti, s.cikti)


# ===================================================== SONUC
_yaz("")
_yaz("=" * 70)
_yaz("gecti: %d   basarisiz: %d" % (gecti, basarisiz))
_yaz("=" * 70)

try:
    App.closeDocument(doc.Name)
except Exception:
    pass

sys.exit(1 if basarisiz else 0)
