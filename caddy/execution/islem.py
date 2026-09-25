"""Helpers that expose FreeCAD's READY-MADE capabilities to the model as a single call.

WHY IT EXISTS. The model was hand-writing jobs that are a single call in
FreeCAD, and damaging the model while doing it. Measured in the log
(LOG/2026-08-20_baa70fa4.txt): splitting parts with flood-fill, closing
holes by stitching boundary loops, fixing normals with BFS — tried three
turns in a row, and each time a REAL HOLE was torn in the body and the user
had to undo. The ready-made chain that does the same job is eight lines and
0.024 seconds.

SPEED. This module does not slow turns down, it SPEEDS THEM UP. What
determines latency is generated tokens: the slowest turns in the log
(149.6 s, 118.5 s) are exactly the turns where the model hand-wrote 45-50
lines of geometry. Writing `mesh_onar()` is an order of magnitude faster.

COMMON RULE: A HELPER VERIFIES ITS OWN EFFECT.
The lesson from measuring `PartDesign::PolarPattern`: on a primitive it
does NOT raise an error, State says "Up-to-date", the volume does not
change — it silently leaves a single copy. The model says "I made 6 holes",
the document has one hole. So every helper here MEASURES the result after
doing its job and says so plainly if it does not find what it expected. The
same pattern as "NOT ROUND" in the measurement layer.

They all print: the output goes back to the model automatically.
None of them leaks an exception.

LAYER RULE (MANTIK 12): NO Qt here.
"""

from __future__ import annotations

import math
import os
import time

import FreeCAD as App

from . import olcum

# Densities of 3D printing materials (g/cm3).
YOGUNLUK = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07,
    "TPU": 1.21, "NAYLON": 1.14, "PA": 1.14, "RECINE": 1.15,
    "PC": 1.20, "PP": 0.90,
}

# Upper limit for converting a mesh to a solid. Above it, every triangle
# becomes a FACE: measured, 8000 facets -> an 8000-face solid, 4.64 s. On
# such a solid every boolean is painfully slow.
AZAMI_FACET = 4000


def _hedef(nesne):
    return olcum._hedef(nesne)


def _mesh_al(nesne):
    return olcum._mesh_al(nesne)


def _sekil_al(nesne):
    return olcum._sekil_al(nesne)


def _sayi(x) -> str:
    return olcum._sayi(x)


def _mesh_durumu(m) -> dict:
    d = {}
    for ad, cagri in (("kapali", lambda: bool(m.isSolid())),
                      ("facet", lambda: int(m.CountFacets)),
                      ("parca", lambda: int(m.countComponents())),
                      ("kesisme", lambda: bool(m.hasSelfIntersections())),
                      ("manifold_disi", lambda: bool(m.hasNonManifolds()))):
        try:
            d[ad] = cagri()
        except Exception:
            d[ad] = None
    return d


def _mesh_kati(m, azami_facet: int = AZAMI_FACET):
    """Mesh -> Part solid. ADDS NO OBJECT TO THE DOCUMENT. Returns (solid, final_facets).

    Both `kati_yap` and the mesh path of `birlestir` use this — keeping the
    conversion in one place means the two paths cannot silently diverge.

    The facet limit is CRITICAL, measured (cylinder+torus, convert to solid
    + fuse + back to mesh):
        2 172 facets ->  2.9 s   closed, no self-intersection, 1 component
        3 784 facets ->  7.4 s   closed, no self-intersection, 1 component
       32 756 facets -> 59.2 s   valid solid BUT the mesh has SELF-INTERSECTIONS
    So the limit is not only for speed, it is also for the CLEANLINESS OF THE
    RESULT.
    """
    import Part

    calisilan = m
    facet = int(m.CountFacets)
    if facet > azami_facet:
        try:
            calisilan = m.copy()
            calisilan.decimate(0.01, 1.0 - (azami_facet / float(facet)))
        except Exception:
            calisilan = m

    s = Part.Shape()
    s.makeShapeFromMesh(calisilan.Topology, 0.1)
    return Part.makeSolid(s), int(calisilan.CountFacets)


def _kati_baski_gercegi(sekil, sapma: float = 0.1):
    """The PRINT reality of a SOLID result. Returns (state, seconds); None if it fails.

    WHY HERE. `dogrulama` does NOT RUN the self-intersection check on SOLID
    (BRep) objects — it is expensive in OCC and would be paid for every
    object on every run. But `birlestir` is already an operation that takes
    seconds, and it is exactly the place most likely to produce
    self-intersections.

    MEASURED LOSS (LOG/2026-08-24_3ad4cef1.txt, 12:08 -> 12:09): birlestir
    said "volume=5.551e+04 mm3, 1 solid", verification said "solid=1", the
    shape's isValid() was True. The SAME shape meshed at 0.05 mm came out
    not closed + self-intersecting + non-manifold. So a 108-second operation
    gave false confidence, and the error only showed up at export, at the
    end of the job. `isValid()` and `Solids == 1` do NOT mean ready to print.

    COST MEASURED — the check (meshing + three questions) / the operation:
        two boxes              0.047 s / connect 0.285 s
        cylinder + sphere      0.064 s / connect 0.059 s
        mesh-derived solid     0.929 s / fuse    1.802 s
    ~1 s in the worst case, and a small percentage of the operation on the
    mesh-derived path where the risk is highest. So it runs unconditionally.
    """
    import time

    import MeshPart

    t0 = time.time()
    try:
        m = MeshPart.meshFromShape(Shape=sekil, LinearDeflection=sapma,
                                   AngularDeflection=0.4)
        return _mesh_durumu(m), time.time() - t0
    except Exception:                                            # noqa: BLE001
        return None, time.time() - t0


def _baski_verdikti(d: dict) -> list:
    """What is broken from a printing point of view. Empty list = clean."""
    sorun = []
    if d.get("kapali") is False:
        sorun.append("not closed (not watertight)")
    if d.get("kesisme"):
        sorun.append("self-intersecting — isValid() does NOT catch this")
    if d.get("manifold_disi"):
        sorun.append("non-manifold")
    if d.get("parca") not in (None, 1):
        sorun.append(f"{d['parca']} separate components")
    return sorun


def _durum_metni(d: dict) -> str:
    p = [("closed" if d.get("kapali") else "OPEN"),
         f"facets={d.get('facet')}"]
    if d.get("parca") not in (None, 1):
        p.append(f"components={d['parca']}")
    if d.get("kesisme"):
        p.append("SELF-INTERSECTING")
    if d.get("manifold_disi"):
        p.append("NON-MANIFOLD")
    return " ".join(p)


# ==========================================================================
# ROUND 1 — make a downloaded mesh workable
# ==========================================================================

def mesh_onar(nesne=None, yaz: bool = True) -> dict:
    """Fixes a mesh with FreeCAD's own repair chain.

    THE CHAIN (order matters): duplicated points -> indices -> degenerate
    triangles -> self-intersections -> non-manifolds -> holes -> normals.

    This replaces the hand-written "flood-fill + boundary loop stitching"
    attempts. Measured: on a mesh with a hole, isSolid False -> True,
    0.024 s.

    It DOES NOT TOUCH an already clean mesh: changing facets for no reason
    is damaging the user's model for nothing.
    """
    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("repair_mesh: this is not a mesh object "
                  "(for a solid look at Shape.fix/removeSplitter)")
        return {}

    ad = getattr(nesne, "Name", "?")
    once = _mesh_durumu(m)
    if (once.get("kapali") and not once.get("kesisme")
            and not once.get("manifold_disi")):
        if yaz:
            print(f"{ad}: already clean ({_durum_metni(once)}) — not touched")
        return {"degisti": False, "once": once, "sonra": once}

    t0 = time.time()
    yeni = m.copy()
    adimlar = []
    for adim, cagri in (
            ("duplicated points", lambda: yeni.removeDuplicatedPoints()),
            ("indices", lambda: yeni.fixIndices()),
            ("degenerate triangles", lambda: yeni.fixDegenerations(0.001)),
            ("self-intersections", lambda: yeni.fixSelfIntersections()),
            ("non-manifold", lambda: yeni.removeNonManifolds()),
            ("holes", lambda: yeni.fillupHoles(1000, 0)),
            ("normals", lambda: yeni.harmonizeNormals())):
        try:
            cagri()
        except Exception as e:                                   # noqa: BLE001
            adimlar.append(f"{adim}(skipped: {e})")

    try:
        nesne.Mesh = yeni
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"repair_mesh: could not write the result ({e})")
        return {}

    sonra = _mesh_durumu(yeni)
    d = {"degisti": True, "once": once, "sonra": sonra,
         "sure": time.time() - t0}
    if yaz:
        print(f"{ad} repaired ({d['sure']:.2f} s): "
              f"{_durum_metni(once)}  ->  {_durum_metni(sonra)}")
        for a in adimlar:
            print(f"    {a}")
        # HONESTY: the chain cannot fix everything. Saying what did not get
        # fixed is better than saying "repaired" and leaving it.
        kalan = []
        if not sonra.get("kapali"):
            kalan.append("still OPEN (the hole may be too large)")
        if sonra.get("kesisme"):
            kalan.append("still self-intersecting")
        if sonra.get("manifold_disi"):
            kalan.append("still non-manifold")
        if kalan:
            print("    REMAINING PROBLEM: " + ", ".join(kalan))
    return d


def kati_yap(nesne=None, azami_facet: int = AZAMI_FACET, yaz: bool = True):
    """Converts a mesh into a SOLID — the door to the parametric tools.

    WHY IT IS NEEDED: everything imported (STL/OBJ/3MF) is a mesh. A mesh has
    no fillet, no pocket, and booleans are hard. Converted to a solid, all of
    FreeCAD's Part/PartDesign tools open up.

    TWO HONESTY RULES:
      * If the mesh is NOT CLOSED it refuses. A "solid" made from an open
        mesh is a lie; mesh_onar has to be called first.
      * The result is NOT PARAMETRIC and it says so. Measured: 8000 facets
        -> an 8000-FACE solid, 4.64 s. If the facet limit is exceeded,
        decimate is applied first and the new count is printed.
    """
    import Part

    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("make_solid: this is not a mesh object")
        return None

    ad = getattr(nesne, "Name", "?")
    durum = _mesh_durumu(m)
    if not durum.get("kapali"):
        if yaz:
            print(f"make_solid: {ad} is NOT CLOSED ({_durum_metni(durum)}). "
                  f"A solid made from an open mesh is misleading — run "
                  f"repair_mesh({ad}) first.")
        return None

    t0 = time.time()
    try:
        kati, facet_sonra = _mesh_kati(m, azami_facet)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"make_solid: conversion failed ({e})")
        return None

    doc = App.ActiveDocument
    yeni = doc.addObject("Part::Feature", ad + "_kati")
    yeni.Label = (getattr(nesne, "Label", ad) or ad) + " (solid)"
    yeni.Shape = kati

    try:
        nesne.Visibility = False
    except Exception:
        pass

    sure = time.time() - t0
    if yaz:
        sapma = ""
        try:
            hm = float(m.Volume)
            if hm:
                sapma = f", volume deviation {abs(kati.Volume - hm) / hm * 100:.2f}%"
        except Exception:
            pass
        print(f"{ad} -> {yeni.Name}: solid, {len(kati.Faces)} faces, "
              f"volume={_sayi(kati.Volume)} mm3{sapma} ({sure:.2f} s)")
        facet = durum.get("facet") or 0
        if facet_sonra != facet:
            print(f"    facets {facet} -> {facet_sonra} "
                  f"(limit {azami_facet}, decimate applied)")
        if not kati.isValid():
            print("    WARNING: solid isValid() is False — if booleans are "
                  "built on it, the error surfaces at the end of the chain")
        print("    NOTE: this is NOT a PARAMETRIC solid, every triangle is a "
              "face. If an editable part is wanted, take the dimensions and "
              "build it from scratch.")
    return yeni


def icini_bosalt(nesne=None, kalinlik: float = 2.0, acik_yuz=None,
                 yaz: bool = True):
    """Hollows out a solid body (shell) — cup, box, enclosure.

    TRAP (measured): `makeThickness` wants the face from the SAME shape
    INSTANCE. Building the shape twice and passing the face from the other
    instance gives "face does not belong to the shape". Here the face is
    always picked from the shape being worked on.

    If `acik_yuz` is not given, the TOPMOST face is opened (right for a
    cup/box).
    """
    nesne = _hedef(nesne)
    s = _sekil_al(nesne)
    if s is None:
        if yaz:
            print("hollow: needs a solid object (for a mesh, make_solid first)")
        return None

    ad = getattr(nesne, "Name", "?")
    try:
        yuzler = s.Faces
    except Exception:
        yuzler = []
    if not yuzler:
        if yaz:
            print(f"hollow: {ad} has no faces")
        return None

    if acik_yuz is None:
        yuz = max(yuzler, key=lambda f: f.CenterOfMass.z)
    elif isinstance(acik_yuz, int):
        if not 0 <= acik_yuz < len(yuzler):
            if yaz:
                print(f"hollow: there is no face {acik_yuz} "
                      f"(0..{len(yuzler) - 1})")
            return None
        yuz = yuzler[acik_yuz]
    else:
        yuz = acik_yuz

    onceki_hacim = float(s.Volume or 0.0)
    try:
        kabuk = s.makeThickness([yuz], -abs(kalinlik), 1e-3)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"hollow: failed ({e}). The thickness may be too large for "
                  f"the body; try a smaller value.")
        return None

    doc = App.ActiveDocument
    yeni = doc.addObject("Part::Feature", ad + "_kabuk")
    yeni.Label = (getattr(nesne, "Label", ad) or ad) + f" (shell {kalinlik}mm)"
    yeni.Shape = kabuk
    try:
        nesne.Visibility = False
    except Exception:
        pass

    if yaz:
        h = float(kabuk.Volume or 0.0)
        print(f"{ad} -> {yeni.Name}: shell {kalinlik} mm, "
              f"volume {_sayi(onceki_hacim)} -> {_sayi(h)} mm3")
        # VERIFICATION: the shell volume should be a fraction of the
        # original. If it is almost the same, the operation stayed
        # INVISIBLE.
        if onceki_hacim and h > 0.9 * onceki_hacim:
            print("    WARNING: the volume barely changed — the shell may not "
                  "have formed, check the open face")
        if not kabuk.isValid():
            print("    WARNING: result isValid() is False")
    return yeni


# ==========================================================================
# ROUND 2 — dimensions in a TABLE (Spreadsheet + expression engine)
# ==========================================================================

TABLO_ADI = "Olculer"


def olcu_tablosu(_ad: str = TABLO_ADI, yaz: bool = True, **degerler):
    """Puts dimensions into a TABLE; properties can be bound to it.

    WHY: the strongest form of the "leave it editable" rule. When the
    dimensions are constants buried in the code, the user has to go back to
    the AI for every change. In a table they change one cell and the model
    updates.

        olcu_tablosu(cap=55.5, yukseklik=95, duvar=2)
        bagla(govde, "Radius", "Olculer.cap / 2")

    Measured: setAlias + setExpression works, Radius = 27.75 mm.
    """
    doc = App.ActiveDocument
    if doc is None:
        if yaz:
            print("dimension_table: no open document")
        return None

    sh = doc.getObject(_ad)
    if sh is None:
        sh = doc.addObject("Spreadsheet::Sheet", _ad)
        sh.Label = "Dimensions"

    # Find the existing rows so the same name is not written twice.
    satir = 1
    mevcut = {}
    while satir < 200:
        try:
            a = sh.get(f"A{satir}")
        except Exception:
            break
        if a in (None, ""):
            break
        mevcut[str(a)] = satir
        satir += 1

    yazilan = []
    for ad, deger in degerler.items():
        r = mevcut.get(ad, satir)
        if ad not in mevcut:
            satir += 1
        try:
            sh.set(f"A{r}", str(ad))
            sh.set(f"B{r}", str(deger))
            sh.setAlias(f"B{r}", str(ad))
            yazilan.append(f"{ad}={deger}")
        except Exception as e:                                   # noqa: BLE001
            if yaz:
                print(f"    could not write {ad}: {e}")

    try:
        doc.recompute()
    except Exception:
        pass

    if yaz:
        print(f"{_ad} table: " + (", ".join(yazilan) or "(empty)"))
        print(f"    usage: bind(obj, \"Radius\", \"{_ad}.<name> / 2\")")
    return sh


def bagla(nesne, ozellik: str, ifade: str, yaz: bool = True) -> bool:
    """BINDS a property to a value in the table and VERIFIES that it is bound.

    `setExpression` can silently do nothing (a wrong alias, an expression
    that does not resolve). Here the value is actually read back after
    binding.
    """
    if nesne is None or not ozellik:
        if yaz:
            print("bind: needs an object and a property name")
        return False
    try:
        onceki = getattr(nesne, ozellik, None)
    except Exception:
        onceki = None

    # TRY THE EXPRESSION FIRST. MEASURED: `setExpression` also accepts an
    # expression that DOES NOT RESOLVE — it raises no exception, it goes into
    # the ExpressionEngine, but the value does not change. So checking the
    # ExpressionEngine for "is it set up" gives the WRONG answer. The only
    # reliable way is to evaluate the expression.
    try:
        nesne.evalExpression(ifade)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"bind: the expression DID NOT RESOLVE — {ifade}  ({e})")
            print(f"    {ozellik} stayed {onceki}. Check the alias name in "
                  f"the table (it is printed in the dimension_table output).")
        return False

    try:
        nesne.setExpression(ozellik, ifade)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"bind: {ozellik} <- {ifade} failed ({e})")
        return False

    try:
        sonra = getattr(nesne, ozellik, None)
    except Exception:
        sonra = None

    if yaz:
        print(f"{nesne.Name}.{ozellik} <- {ifade}  (={sonra})")
    return True


# ==========================================================================
# ROUND 3 — text, screw thread, weight
# ==========================================================================

_FONT_ADAYLARI = ("arial.ttf", "segoeui.ttf", "tahoma.ttf", "verdana.ttf",
                  "calibri.ttf", "DejaVuSans.ttf")


def _font_bul(font: str = "") -> str:
    if font and os.path.isfile(font):
        return font
    dizinler = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]
    for d in dizinler:
        for ad in _FONT_ADAYLARI:
            yol = os.path.join(d, ad)
            if os.path.isfile(yol):
                return yol
    return ""


def yazi(metin: str, boyut: float = 10.0, kalinlik: float = 1.0,
         font: str = "", yaz: bool = True):
    """TEXT on a part — a name, a dimension, a logo. Produces real geometry.

    Measured: Draft.make_shapestring 2.14 s (first call loads the module),
    a 97-edge shape for "CADdy".

    If `kalinlik` > 0 the text is made solid (ready for embossing/engraving).
    If no font is found it DOES NOT STAY SILENT.
    """
    yol = _font_bul(font)
    if not yol:
        if yaz:
            print(f"text3d: no font found (tried: "
                  f"{', '.join(_FONT_ADAYLARI)}). Give a full path: "
                  f"text3d('...', font=r'C:\\Windows\\Fonts\\arial.ttf')")
        return None

    try:
        import Draft
        import Part
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"text3d: could not load Draft ({e})")
        return None

    doc = App.ActiveDocument
    try:
        ss = Draft.make_shapestring(String=str(metin), FontFile=yol,
                                    Size=float(boyut))
        doc.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"text3d: could not be created ({e})")
        return None

    sonuc = ss
    if kalinlik and kalinlik > 0:
        try:
            kati = ss.Shape.extrude(App.Vector(0, 0, float(kalinlik)))
            nesne = doc.addObject("Part::Feature", "Yazi")
            nesne.Label = f"Text: {metin}"
            nesne.Shape = kati
            doc.removeObject(ss.Name)
            doc.recompute()
            sonuc = nesne
        except Exception as e:                                   # noqa: BLE001
            if yaz:
                print(f"    could not be thickened ({e}); left as a flat shape")

    if yaz:
        try:
            b = sonuc.Shape.BoundBox
            print(f"{sonuc.Name}: '{metin}' {_sayi(b.XLength)}x"
                  f"{_sayi(b.YLength)}x{_sayi(b.ZLength)} mm "
                  f"(font {os.path.basename(yol)})")
            print("    On the XY plane, starting at (0,0). Use Placement to "
                  "position it, a boolean to embed it.")
        except Exception:
            pass
    return sonuc


def vida_disi(yaricap: float, hatve: float, boy: float,
              ic_mi: bool = False, yaz: bool = True):
    """Produces a SCREW THREAD (helix + triangular profile).

    LOG: b2938bd0 was a BANJO BOLT session from start to finish and the
    thread could never be made.

    `yaricap` is HALF the outer diameter (4 for M8). `hatve` is the advance
    per turn (1.25 for M8 coarse). With `ic_mi=True` (nut/hole thread) the
    profile points inward.
    """
    import Part

    try:
        yaricap = float(yaricap)
        hatve = float(hatve)
        boy = float(boy)
    except Exception:
        if yaz:
            print("screw_thread: needs numeric values")
        return None
    if min(yaricap, hatve, boy) <= 0:
        if yaz:
            print("screw_thread: radius, pitch and length must be positive")
        return None

    # The theoretical depth of an ISO metric thread is 0.6134 * pitch.
    derinlik = 0.6134 * hatve
    yon = -1.0 if ic_mi else 1.0

    try:
        helis = Part.makeHelix(hatve, boy, yaricap)
        # THE PROFILE BASE MUST BE INSIDE THE CYLINDER. Measured: with the
        # base exactly at the radius (TANGENT to the cylinder surface) fuse
        # produces an invalid solid — isValid() False and the volume comes
        # out SMALLER than the cylinder's. Moved in by depth/3, isValid() is
        # True and the volume is 1155 (cylinder 1005), i.e. the thread
        # really sticks out.
        taban = App.Vector(yaricap - derinlik / 3.0, 0, 0)
        p1 = taban + App.Vector(0, 0, -hatve / 2.0)
        p2 = taban + App.Vector(0, 0, hatve / 2.0)
        p3 = App.Vector(yaricap + yon * derinlik, 0, 0)
        profil = Part.Wire(Part.makePolygon([p1, p2, p3, p1]))
        boru = Part.Wire(helis).makePipeShell([profil], True, True)
        govde = Part.makeCylinder(yaricap, boy)
        kati = govde.fuse(boru) if not ic_mi else govde.cut(boru)
        kati = kati.removeSplitter()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"screw_thread: could not be produced ({e})")
        return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Part::Feature", "VidaDisi")
    nesne.Label = f"Thread M{_sayi(2 * yaricap)}x{_sayi(hatve)}"
    nesne.Shape = kati
    doc.recompute()

    if yaz:
        print(f"{nesne.Name}: {'internal' if ic_mi else 'external'} thread, "
              f"diameter={_sayi(2 * yaricap)} pitch={_sayi(hatve)} "
              f"length={_sayi(boy)} mm, {int(boy / hatve)} turns, "
              f"volume={_sayi(kati.Volume)} mm3")
        if not kati.isValid():
            print("    WARNING: result isValid() is False — review the "
                  "pitch/depth ratio")
        if len(kati.Solids) != 1:
            print(f"    WARNING: {len(kati.Solids)} solids came out, 1 was expected")
    return nesne


def agirlik(nesne=None, malzeme: str = "PLA", doluluk: float = 1.0,
            yaz: bool = True) -> dict:
    """The part's WEIGHT and the filament it will use.

    The answer to "how many grams will it be", which we could never give
    until now. `doluluk` is 0..1 (0.2 = 20% infill; rough — walls and
    top/bottom layers push it up, so the result is a LOWER BOUND).
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("weight: object not found")
        return {}

    hacim = None
    m = _mesh_al(nesne)
    if m is not None:
        try:
            hacim = float(m.Volume)
        except Exception:
            hacim = None
    if hacim is None:
        s = _sekil_al(nesne)
        try:
            hacim = float(s.Volume)
        except Exception:
            hacim = None
    if not hacim or hacim <= 0:
        if yaz:
            print(f"weight: could not read the volume of "
                  f"{getattr(nesne, 'Name', '?')} "
                  f"(if the mesh is not closed, volume is meaningless)")
        return {}

    anahtar = str(malzeme).upper().strip()
    yog = YOGUNLUK.get(anahtar)
    if yog is None:
        if yaz:
            print(f"weight: {malzeme} is unknown. Known: "
                  f"{', '.join(sorted(YOGUNLUK))}")
        return {}

    cm3 = hacim / 1000.0 * max(0.0, min(1.0, doluluk))
    gram = cm3 * yog
    # 1.75 mm filament cross-section = pi * 0.875^2 = 2.405 mm2 -> 2.405 cm3/m
    metre = cm3 / 2.405 * 10.0 / 10.0 if False else cm3 / 0.2405 / 100.0

    d = {"hacim_mm3": hacim, "gram": gram, "malzeme": anahtar,
         "metre": metre}
    if yaz:
        ek = "" if doluluk >= 1 else f" ({doluluk * 100:.0f}% infill, lower bound)"
        print(f"{getattr(nesne, 'Name', '?')}: {_sayi(hacim / 1000.0)} cm3 "
              f"{anahtar} -> {gram:.1f} g{ek}, ~{metre:.1f} m filament "
              f"(1.75 mm)")
    return d


# ==========================================================================
# ROUND 4 — splitting, arrays, bed face, joining
# ==========================================================================

def baskiya_bol(nesne=None, z=None, yaz: bool = True) -> list:
    """Splits a part into PIECES for printing (with a horizontal plane).

    LOG: in b2938bd0 the user said "if needed we'll make 2 parts that fit
    into each other" and it was done by hand. BOPTools.SplitAPI is a single
    call (measured: 0.391 s, 2 solids).
    """
    from BOPTools import SplitAPI
    import Part

    nesne = _hedef(nesne)
    s = _sekil_al(nesne)
    if s is None:
        if yaz:
            print("split_for_print: needs a solid object (for a mesh, "
                  "make_solid first)")
        return []

    b = s.BoundBox
    if z is None:
        z = b.ZMin + b.ZLength / 2.0
    if not (b.ZMin < z < b.ZMax):
        if yaz:
            print(f"split_for_print: z={_sayi(z)} is outside the body "
                  f"({_sayi(b.ZMin)}..{_sayi(b.ZMax)})")
        return []

    try:
        pay = max(b.XLength, b.YLength) * 2 + 10
        duzlem = Part.makePlane(pay, pay,
                                App.Vector(b.Center.x - pay / 2,
                                           b.Center.y - pay / 2, z))
        bolunmus = SplitAPI.slice(s, [duzlem], "Split")
        katilar = list(bolunmus.Solids)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"split_for_print: failed ({e})")
        return []

    if len(katilar) < 2:
        if yaz:
            print(f"split_for_print: the z={_sayi(z)} plane did not split the "
                  f"body ({len(katilar)} piece(s)). Try another height.")
        return []

    doc = App.ActiveDocument
    ad = getattr(nesne, "Name", "Parca")
    yeniler = []
    for i, k in enumerate(katilar, start=1):
        o = doc.addObject("Part::Feature", f"{ad}_p{i}")
        o.Label = f"{getattr(nesne, 'Label', ad)} part {i}"
        o.Shape = k
        yeniler.append(o)
    try:
        nesne.Visibility = False
    except Exception:
        pass
    doc.recompute()

    if yaz:
        print(f"{ad}: split into {len(yeniler)} pieces at z={_sayi(z)}")
        for o in yeniler:
            bb = o.Shape.BoundBox
            print(f"    {o.Name}: {_sayi(bb.XLength)}x{_sayi(bb.YLength)}"
                  f"x{_sayi(bb.ZLength)} mm  volume={_sayi(o.Shape.Volume)}")
        print("    NOTE: the pieces were cut flat; if a joint/pin is wanted "
              "it has to be added separately.")
    return yeniler


def _dizi_dogrula(dizi, beklenen: int, yaz: bool) -> bool:
    """Measures that the array really produced `beklenen` copies.

    PartDesign patterns can silently leave a SINGLE copy (measured). We do
    not accept the same silent failure from a Draft array either.
    """
    try:
        n = len(dizi.Shape.Solids) or len(dizi.Shape.childShapes())
    except Exception:
        return True
    if n < beklenen:
        if yaz:
            print(f"    WARNING: {beklenen} copies were requested but the result "
                  f"has {n}. The copies may overlap or the array may not have "
                  f"been applied.")
        return False
    return True


def dizi_polar(nesne=None, adet: int = 6, aci: float = 360.0,
               merkez=None, yaz: bool = True):
    """Arrays the object POLARLY around the Z axis. Measured: 0.030 s."""
    import Draft

    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("polar_array: object not found")
        return None
    if adet < 2:
        if yaz:
            print("polar_array: count must be at least 2")
        return None

    if merkez is None:
        merkez = App.Vector(0, 0, 0)
    try:
        d = Draft.make_polar_array(nesne, int(adet), float(aci), merkez)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"polar_array: failed ({e})")
        return None

    if yaz:
        print(f"{d.Name}: {getattr(nesne, 'Name', '?')} x{adet}, "
              f"over {_sayi(aci)} degrees, center=({_sayi(merkez.x)},"
              f"{_sayi(merkez.y)})")
        _dizi_dogrula(d, adet, yaz)
    return d


def dizi_dogrusal(nesne=None, adet: int = 3, yon=None, aralik: float = 20.0,
                  yaz: bool = True):
    """Arrays the object along a direction. Measured: 1.93 s (first call)."""
    import Draft

    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("linear_array: object not found")
        return None
    if adet < 2:
        if yaz:
            print("linear_array: count must be at least 2")
        return None

    if yon is None:
        yon = App.Vector(1, 0, 0)
    try:
        u = App.Vector(yon).normalize()
    except Exception:
        u = App.Vector(1, 0, 0)
    adim = App.Vector(u.x * aralik, u.y * aralik, u.z * aralik)

    try:
        d = Draft.make_ortho_array(nesne, adim, App.Vector(0, 0, 0),
                                   App.Vector(0, 0, 0), int(adet), 1, 1)
        App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"linear_array: failed ({e})")
        return None

    if yaz:
        print(f"{d.Name}: {getattr(nesne, 'Name', '?')} x{adet}, "
              f"{_sayi(aralik)} mm apart along ({_sayi(u.x)},{_sayi(u.y)},"
              f"{_sayi(u.z)})")
        _dizi_dogrula(d, adet, yaz)
    return d


def _en_buyuk_duz_yuz(nesne):
    """(normal, point) — the widest flat region of the part. None if there is none."""
    m = _mesh_al(nesne)
    if m is not None:
        try:
            segmentler = m.getPlanarSegments(0.01)
        except Exception:
            return None
        if not segmentler:
            return None
        en = max(segmentler, key=len)
        if len(en) < 3:
            return None
        try:
            f = m.Facets[en[0]]
            n = App.Vector(*f.Normal)
            p = App.Vector(*f.Points[0])
            # We preferred the segment largest by area; the facet count is
            # a good enough proxy (the triangles are roughly the same size).
            return n.normalize(), p
        except Exception:
            return None

    s = _sekil_al(nesne)
    if s is None:
        return None
    duz = []
    for f in s.Faces:
        try:
            if type(f.Surface).__name__ == "Plane":
                duz.append(f)
        except Exception:
            continue
    if not duz:
        return None
    f = max(duz, key=lambda x: x.Area)
    try:
        return App.Vector(f.Surface.Axis).normalize(), f.CenterOfMass
    except Exception:
        return None


def tabana_otur(nesne=None, yaz: bool = True) -> bool:
    """Places the part on the bed with its widest FLAT face down.

    The first question of print preparation, and until now it was done by
    eye. Measured: Mesh.getPlanarSegments 0.010 s.

    If there is no flat region it DOES NOT MAKE ONE UP, it says so.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("place_on_bed: object not found")
        return False

    bulgu = _en_buyuk_duz_yuz(nesne)
    if bulgu is None:
        if yaz:
            print(f"place_on_bed: no flat face found for "
                  f"{getattr(nesne, 'Name', '?')} — this part has no flat "
                  f"place to sit on the bed, it needs supports or manual "
                  f"orientation")
        return False

    normal, _nokta = bulgu
    hedef = App.Vector(0, 0, -1)
    try:
        aci = math.degrees(normal.getAngle(hedef))
    except Exception:
        aci = 0.0

    try:
        if aci > 0.5:
            eksen = normal.cross(hedef)
            if eksen.Length < 1e-9:               # exactly opposite direction
                eksen = App.Vector(1, 0, 0)
            donme = App.Rotation(eksen, aci)
            p = nesne.Placement
            nesne.Placement = App.Placement(
                donme.multVec(p.Base), donme.multiply(p.Rotation))
        App.ActiveDocument.recompute()
        b = olcum._kutu(nesne)
        if b is not None and abs(b.ZMin) > 1e-9:
            p = nesne.Placement
            p.Base = App.Vector(p.Base.x, p.Base.y, p.Base.z - b.ZMin)
            nesne.Placement = p
            App.ActiveDocument.recompute()
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"place_on_bed: could not be placed ({e})")
        return False

    if yaz:
        b = olcum._kutu(nesne)
        print(f"{getattr(nesne, 'Name', '?')}: rotated {_sayi(aci)} degrees "
              f"and placed on the bed, z={_sayi(b.ZMin)}.."
              f"{_sayi(b.ZMax)}")
    return True


_KABUK_ONBELLEK = {}          # (document, object) -> (signature, shell, flat_zs)


def _yatay_yuz_zleri(m, tol: float = 1e-4) -> list:
    """The z heights of HORIZONTAL faces in the mesh. The places where a section lies.

    MEASURED — if a section lands exactly on a horizontal face the result
    silently breaks, on both the OCC and the mesh path:

        cylinder r=15 h=40   z=0  -> area   7.2   (correct: 706.9)
        cylinder r=15 h=40   z=40 -> area   7.2
        box 20x30x10         z=0  -> area 300.0   (correct: 600)
        stepped part         z=10 -> area 600.0   (below 1600, above 400)

    The last one is the sneakiest: the value equals neither the one below
    nor the one above, it is a made-up number between the two. None of them
    raises an error.

    A single pass, collecting the z of the facets whose normal is +-Z —
    milliseconds on 4500 facets. It goes into the cache with the shell.
    """
    zler = set()
    try:
        for facet in m.Facets:
            n = facet.Normal
            if abs(n.z) > 0.9999 and abs(n.x) < 1e-3 and abs(n.y) < 1e-3:
                p = facet.Points[0]
                zler.add(round(p[2], 4))
    except Exception:                                            # noqa: BLE001
        return []
    # Collect nearby values under one heading (facets may not be at exactly
    # the same z).
    sirali = sorted(zler)
    kumeler = []
    for z in sirali:
        if kumeler and abs(z - kumeler[-1]) <= tol * 10:
            continue
        kumeler.append(z)
    return kumeler


def _mesh_on_kontrol(m, yaz: bool) -> str:
    """The mesh's health BEFORE converting it to a shell. Returns the reason text if broken.

    WHY IT EXISTS — MEASURED (LOG/2026-09-01_361c792d.txt): on a downloaded
    aircraft mesh (34350 facets) `kesit_konturu(plane, [3,8,15,25,35,43])`
    took **22.66 seconds** and six lines said "no contour". The whole cost
    is in the `makeShapeFromMesh` conversion; the sections themselves take
    0.01 s.

    Yet the answer coming out empty was known IN ADVANCE, in 0.05 seconds:

        isSolid              False   0.016 s
        hasNonManifolds      True    0.001 s
        hasSelfIntersections True    0.016 s
        countComponents      494     0.000 s

    So a look 700 times cheaper was saying the 22.66 seconds would be
    wasted. What's more, in the same block `kesif()` had already written
    "ready to print = NO (not closed, self-intersecting, non-manifold, many
    components)"; the diagnosis was there, this function was not looking at
    it.

    WE DON'T REFUSE, WE WARN. Measured (four meshes, the same day):

        clean box       closed, one component, 12 facets  -> 0.00 s, 1 contour
        OPEN box        OPEN,   one component, 10 facets  -> 0.01 s, 1 contour
        3 disjoint spheres closed, 3 COMPONENTS, 912 facets -> 0.13 s, 3 contours
        downloaded plane open+non-manifold+self-intersecting, 494 components,
                        34350 facets                       -> 24.87 s, 0 contours

    So "not closed" ALONE is NOT a reason to refuse (the open box gave the
    right contour), and neither is "many components" (three spheres gave
    three contours). Writing a rule from a single example is forbidden in
    this project; so we give no verdict, we say what we are getting BEFORE
    paying the cost, and if it comes out empty we write the REASON.
    """
    try:
        facet = int(m.CountFacets)
        kusurlar = []
        if not m.isSolid():
            kusurlar.append("not closed")
        if m.hasNonManifolds():
            kusurlar.append("non-manifold")
        if m.hasSelfIntersections():
            kusurlar.append("self-intersecting")
        parca = int(m.countComponents())
        if parca > 1:
            kusurlar.append(f"{parca} separate components")
    except Exception:                                            # noqa: BLE001
        return ""
    if not kusurlar:
        return ""
    metin = ", ".join(kusurlar)
    if yaz:
        print(f"section_contour: the mesh is not sound ({metin}); {facet} facets "
              f"will be converted to a shell — this may take long and no "
              f"section may come out")
    return metin


def _kabuk_ve_duzler(hedef, m):
    """Mesh -> (shell, z of horizontal faces). Computed ONCE for the same object.

    MEASURED: `makeShapeFromMesh` 1.84 s on 4512 facets, `slice` 2.76 s per
    call. In the log the model asked for sections at six different heights
    and the conversion was paid SIX TIMES: it should have been 18.6 s
    instead of 27.8 s (1.5x). The real cost is in slice and that is OCC's
    business, but paying for the conversion again and again was a free
    loss.
    """
    import Part

    doc = App.ActiveDocument
    anahtar = (getattr(doc, "Name", ""), getattr(hedef, "Name", id(hedef)))
    imza = (int(m.CountFacets), round(float(m.Area), 6))
    onbellek = _KABUK_ONBELLEK.get(anahtar)
    if onbellek is not None and onbellek[0] == imza:
        return onbellek[1], onbellek[2]

    kabuk = Part.Shape()
    kabuk.makeShapeFromMesh(m.Topology, 0.1)
    duzler = _yatay_yuz_zleri(m)
    _KABUK_ONBELLEK[anahtar] = (imza, kabuk, duzler)
    # Don't let the cache grow without limit; within a session this is a few
    # objects.
    if len(_KABUK_ONBELLEK) > 8:
        for k in list(_KABUK_ONBELLEK)[:-8]:
            _KABUK_ONBELLEK.pop(k, None)
    return kabuk, duzler


def kesit_konturu(nesne=None, z=None, sik: float = 0.8, yaz: bool = True):
    """Gives the SECTION CONTOURS at a height as point lists.

    Returns: the list of contours, sorted longest to shortest. Each contour
    is a [(x, y), ...] list. EMPTY LIST if nothing is found.

    WHY IT EXISTS — in two separate sessions two separate models hand-wrote
    the same ten lines:

      LOG/2026-08-24_67cd3efb (Sonnet): a width profile with a `shape.slice`
        loop -> 68.9 s; plus a 49.0 s isInside point scan.
      LOG/2026-08-24_3ad4cef1 (Opus): rewrote the `makeShapeFromMesh ->
        slice -> sort -> discretize` pattern from scratch in FIVE separate
        blocks. Every repeat means both tokens and the risk of "what if I
        get it wrong this time".

    Accepts both a mesh and a solid; a mesh is first converted to a shell
    (unlike kati_yap it ADDS NO OBJECT TO THE DOCUMENT, it only reads). If
    `z` is not given it cuts right through the middle of the part. `z` can
    also be a LIST — then it returns {z: contours} and the conversion is
    paid once.

    CONTOUR ORDER matters: [0] is always the longest (the outer outline),
    the rest are holes/separate islands. In Opus's "section wire count: 2"
    output, the second wire was the rabbit's eye.

    A SECTION THAT LANDS ON A HORIZONTAL FACE COMES OUT SILENTLY WRONG — this
    was a plain bug in the first version of this helper, measured: cylinder
    r=15 h=40, section area at z=0 7.2 mm2 (correct: 706.9), box at z=0 300
    (correct: 600), stepped part at shoulder height 600 (below 1600, above
    400). None of them raised an error. Now:
      * a z requested at the end (at the bbox boundary) is moved INWARD and
        this is said,
      * if it lands on an internal horizontal face a WARNING is given and
        the two safe neighbouring z values are printed — which one is
        wanted is the caller's decision.

    Mesh.crossSections was REJECTED: 673x faster, but on a sphere's equator
    it traverses the path twice and zeroes the area, and on a box at z=0 it
    still gives 300. Buying speed at the cost of correctness is forbidden in
    this project.
    """
    import Part

    hedef = _hedef(nesne)
    if hedef is None:
        if yaz:
            print("section_contour: no object")
        return {} if isinstance(z, (list, tuple)) else []

    coklu = isinstance(z, (list, tuple))
    duz_zler = []
    mesh_kusuru = ""          # the REASON for an empty section, if the mesh is broken
    sekil = _sekil_al(hedef)
    if sekil is None:
        m = _mesh_al(hedef)
        if m is None:
            if yaz:
                print("section_contour: the object has neither a shape nor a mesh")
            return {} if coklu else []
        # A 0.05-second look BEFORE the expensive conversion (see _mesh_on_kontrol).
        mesh_kusuru = _mesh_on_kontrol(m, yaz)
        sekil, duz_zler = _kabuk_ve_duzler(hedef, m)

    try:
        bb = sekil.BoundBox
    except Exception:                                            # noqa: BLE001
        if yaz:
            print("section_contour: could not read the bounding box")
        return {} if coklu else []

    if z is None:
        istenen = [(bb.ZMin + bb.ZMax) / 2.0]
    elif coklu:
        istenen = [float(v) for v in z]
    else:
        istenen = [float(z)]

    # Cutting at the end always comes out broken (measured). A small but
    # meaningful margin relative to the thickness: 0.001 was not enough on a
    # very thin part.
    pay = max(bb.ZLength * 1e-4, 1e-4)
    sonuc = {}
    for ham_z in istenen:
        # Being AT THE END and being OUTSIDE are different things. At the end
        # we shift (it is the requested section, OCC just breaks exactly at
        # the boundary); outside we DO NOT SHIFT — that would be answering a
        # question that was not asked.
        if ham_z < bb.ZMin - pay or ham_z > bb.ZMax + pay:
            if yaz:
                print(f"section_contour: z={_sayi(ham_z)} is outside the part "
                      f"(z {_sayi(bb.ZMin)}..{_sayi(bb.ZMax)}) — no section")
            sonuc[ham_z] = []
            continue

        kz = ham_z
        if kz < bb.ZMin + pay:
            kz = bb.ZMin + pay
        elif kz > bb.ZMax - pay:
            kz = bb.ZMax - pay
        if yaz and abs(kz - ham_z) > 1e-12:
            print(f"section_contour: z={_sayi(ham_z)} is exactly at the end — moved "
                  f"to {_sayi(kz)} (a section at the very end comes out broken)")
        elif yaz and duz_zler:
            yakin = [d for d in duz_zler if abs(d - kz) <= pay * 10]
            if yakin:
                print(f"section_contour: WARNING z={_sayi(kz)} lies on a horizontal "
                      f"face — the section is ambiguous at this height. "
                      f"Ask below/above separately: {_sayi(kz - pay * 20)} and "
                      f"{_sayi(kz + pay * 20)}")

        konturlar, teller = _bir_kesit(sekil, kz, sik)
        sonuc[ham_z] = konturlar
        if yaz:
            _kesit_yaz(kz, konturlar, teller)

    # If NONE of them gave a contour and the mesh is broken, SAY WHY. The log
    # had six identical "no contour" lines and none of them explained why;
    # the model reached the right conclusion by its own reasoning. The
    # lesson of §35.2: general advice does not fire, a NAMED order does —
    # so not "be careful" but "drop this path, use another measurement".
    if yaz and mesh_kusuru and not any(sonuc.values()):
        print(f"section_contour: no contour at any of the {len(sonuc)} heights — "
              f"the cause is NOT the height choice but the mesh ({mesh_kusuru}); "
              f"the shell did not come out sound. Sections will not work on "
              f"this object, use another measurement (bbox scan, measure(), distance()).")

    if coklu:
        return sonuc
    return sonuc[istenen[0]]


def _bir_kesit(sekil, z: float, sik: float):
    """A section at a single height. Returns (contours, wires)."""
    try:
        teller = sekil.slice(App.Vector(0, 0, 1), float(z))
    except Exception:                                            # noqa: BLE001
        return [], []
    teller = sorted(teller, key=lambda w: -w.Length)
    konturlar = []
    kalan_teller = []
    for tel in teller:
        try:
            noktalar = [(v.x, v.y) for v in tel.discretize(Distance=sik)]
        except Exception:                                        # noqa: BLE001
            continue
        # On a closed wire the first and last points are the same; we drop
        # the repeat so that when the caller says "n points" it uses the
        # real count.
        if len(noktalar) > 1 and _yakin(noktalar[0], noktalar[-1]):
            noktalar = noktalar[:-1]
        if len(noktalar) >= 3:
            konturlar.append(noktalar)
            kalan_teller.append(tel)
    return konturlar, kalan_teller


def _kesit_yaz(z: float, konturlar: list, teller: list) -> None:
    if not konturlar:
        print(f"section_contour: no contour in the z={_sayi(z)} section")
        return
    print(f"section_contour: z={_sayi(z)} — {len(konturlar)} contour(s) "
          f"(longest first)")
    for i, k in enumerate(konturlar):
        xs = [p[0] for p in k]
        ys = [p[1] for p in k]
        cevre = _sayi(teller[i].Length) if i < len(teller) else "?"
        print(f"    [{i}] {len(k)} points  x={_sayi(min(xs))}.."
              f"{_sayi(max(xs))}  y={_sayi(min(ys))}..{_sayi(max(ys))}"
              f"  perimeter={cevre} mm")


def _yakin(p, q, tol: float = 1e-7) -> bool:
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def _bbox_ortusme(ma, mb):
    """Do two meshes' bboxes overlap. (overlapping, smallest_overlap).

    If they don't overlap, the second value is NEGATIVE: the largest gap
    between the axes, i.e. a LOWER BOUND on the real distance. Saying it is
    a lower bound is better than giving a made-up distance.
    """
    try:
        ba, bb = ma.BoundBox, mb.BoundBox
    except Exception:
        return None, 0.0
    ortak = []
    for (a0, a1), (b0, b1) in (((ba.XMin, ba.XMax), (bb.XMin, bb.XMax)),
                               ((ba.YMin, ba.YMax), (bb.YMin, bb.YMax)),
                               ((ba.ZMin, ba.ZMax), (bb.ZMin, bb.ZMax))):
        ortak.append(min(a1, b1) - max(a0, b0))
    en_kucuk = min(ortak)
    return (en_kucuk > 0), en_kucuk


def _mesh_birlestir(a, b, ma, mb, azami_facet: int, yaz: bool):
    """The MESH path of birlestir() — convert to solid, fuse, back to mesh.

    WHY NOT `Mesh.Mesh.unite()`: measured, in FreeCAD 1.1.1 unite is fast
    (0.003-0.05 s) and computes the volume correctly (two boxes: exactly
    15000 mm3) but in NO configuration did it produce a CLOSED mesh:
        two boxes        -> closed=False                     still False after repair
        two spheres      -> closed=False, self-intersecting  repair made 1->3 components
        cylinder+torus   -> closed=False, self-intersecting  repair made 1->7 components
    So a helper built on unite would say "joined" while leaving an open
    mesh. The solid path gave a clean result in the same measurement (see
    _mesh_kati).

    IF IT DOES NOT HOLD IT DOES NOT MAKE THINGS UP: it deletes the
    half-made objects and gives the answer that is RIGHT for printing — a
    slicer prints two interpenetrating CLOSED parts as one piece anyway.
    This is not a consolation, it is the solution the model found by itself
    16 minutes later in the log and the user accepted; the difference is
    that it is said on the first call.
    """
    import MeshPart

    ad_a = getattr(a, "Name", "A")
    ad_b = getattr(b, "Name", "B")
    da, db = _mesh_durumu(ma), _mesh_durumu(mb)

    # 1) Both must be closed. No solid comes out of an open mesh.
    acik = [ad for ad, d in ((ad_a, da), (ad_b, db)) if not d.get("kapali")]
    if acik:
        if yaz:
            print(f"join: {', '.join(acik)} NOT CLOSED "
                  f"({_durum_metni(da)} / {_durum_metni(db)}). "
                  f"Run repair_mesh first.")
        return None

    # 2) Do they actually touch. Don't start a 7-second operation for nothing.
    ortusuyor, olcu = _bbox_ortusme(ma, mb)
    if ortusuyor is False:
        if yaz:
            print(f"join: {ad_a} and {ad_b} DO NOT TOUCH — there is at least "
                  f"{_sayi(abs(olcu))} mm of gap between their bboxes. "
                  f"Bring the parts together before joining "
                  f"(for the exact distance: distance({ad_a}, {ad_b})).")
        return None

    t0 = time.time()
    hacim_ayri = 0.0
    try:
        hacim_ayri = float(ma.Volume) + float(mb.Volume)
    except Exception:
        pass

    # 3+4) Convert to solid -> fuse -> back to mesh. The facet budget is for
    # BOTH together: in the measurement the limit makes sense over the total
    # facets.
    pay = max(1, int(azami_facet / 2))
    sorun = ""
    yeni_mesh = None
    try:
        ka, _ = _mesh_kati(ma, pay)
        kb, _ = _mesh_kati(mb, pay)
        kaynak = ka.fuse(kb)
        if len(kaynak.Solids) != 1:
            sorun = f"fuse left {len(kaynak.Solids)} separate solids"
        elif hacim_ayri and kaynak.Volume >= hacim_ayri - 1e-9:
            sorun = "the volume did not shrink below the sum (they did not really fuse)"
        else:
            yeni_mesh = MeshPart.meshFromShape(
                Shape=kaynak, LinearDeflection=0.1,
                AngularDeflection=0.3, Relative=False)
            ds = _mesh_durumu(yeni_mesh)
            if not ds.get("kapali"):
                sorun = "the result mesh is NOT closed"
            elif ds.get("parca") not in (None, 1):
                sorun = f"the result has {ds['parca']} components"
    except Exception as e:                                       # noqa: BLE001
        sorun = str(e)[:120]

    sure = time.time() - t0

    # 5) If it did not hold: leave nothing behind, say what is right.
    if sorun or yeni_mesh is None:
        if yaz:
            print(f"join: could not be fused into one piece ({sorun}) "
                  f"[{sure:.1f} s]")
            print(f"    BUT IT IS NOT A PROBLEM FOR PRINTING: {ad_a} and {ad_b} "
                  f"are both CLOSED and their bboxes overlap by {_sayi(olcu)} mm. "
                  f"A slicer prints overlapping closed parts as one piece "
                  f"— no need to join, leave them as they are.")
        return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Mesh::Feature", f"{ad_a}_birlesik")
    nesne.Mesh = yeni_mesh
    for o in (a, b):
        try:
            o.Visibility = False
        except Exception:
            pass
    doc.recompute()

    if yaz:
        ds = _mesh_durumu(yeni_mesh)
        print(f"{nesne.Name}: {ad_a} + {ad_b} -> mesh, "
              f"{_durum_metni(ds)}, volume={_sayi(yeni_mesh.Volume)} mm3 "
              f"(separate total {_sayi(hacim_ayri)}) [{sure:.1f} s]")
        if ds.get("kesisme"):
            print("    WARNING: the result self-intersects — "
                  f"try repair_mesh({nesne.Name}).")
    return nesne


def birlestir(a, b, azami_facet: int = AZAMI_FACET, yaz: bool = True):
    """Joins two parts CLEANLY.

    If TWO SOLIDS: `BOPTools.JoinAPI.connect`. A plain `fuse` can leave
    internal face leftovers on intersecting bodies; connect cleans that up.
    Measured 0.134 s.

    If TWO MESHES: convert to solid -> fuse -> back to mesh (~7 s, see
    `_mesh_birlestir`). It used to stop in this case saying "needs two SOLID
    objects"; in the log the model took it for a mesh joiner and went round
    a dead end for 13 runs / 16 minutes. The call itself was right, it
    needed to work.
    """
    from BOPTools import JoinAPI

    sa, sb = _sekil_al(a), _sekil_al(b)
    if sa is None or sb is None:
        ma, mb = _mesh_al(a), _mesh_al(b)
        if ma is not None and mb is not None:
            return _mesh_birlestir(a, b, ma, mb, azami_facet, yaz)
        if yaz:
            print("join: needs two SOLID or two MESH objects "
                  "(if one is a solid and one a mesh, match them with "
                  "make_solid first)")
        return None

    # TWO STAGES. connect is preferred (it leaves no internal face leftovers)
    # but MEASURED: on mesh-derived solids it can blow up with "There is more
    # than one largest piece!" — a 1740-face sphere solid + a box were tried,
    # connect blew up, a plain fuse did the same job. We used to return None
    # in this case, i.e. the model hit a dead end while a working path was
    # right there.
    yol = "connect"
    try:
        sonuc = JoinAPI.connect([sa, sb]).removeSplitter()
    except Exception as e:                                       # noqa: BLE001
        try:
            sonuc = sa.fuse(sb).removeSplitter()
            yol = "fuse"
            if yaz:
                print(f"join: connect failed ({e}); continuing with a plain fuse")
        except Exception as e2:                                  # noqa: BLE001
            if yaz:
                print(f"join: failed (connect: {e} | fuse: {e2})")
            return None

    doc = App.ActiveDocument
    nesne = doc.addObject("Part::Feature",
                          f"{getattr(a, 'Name', 'A')}_birlesik")
    nesne.Shape = sonuc
    for o in (a, b):
        try:
            o.Visibility = False
        except Exception:
            pass
    doc.recompute()

    # PRINT REALITY. "1 solid + isValid()" is not enough proof — measured,
    # see _kati_baski_gercegi. It is not computed when yaz=False: if the
    # caller does not want the output, it should not pay the cost either.
    if yaz:
        n = len(sonuc.Solids)
        print(f"{nesne.Name}: {getattr(a, 'Name', '?')} + "
              f"{getattr(b, 'Name', '?')} -> volume={_sayi(sonuc.Volume)} mm3, "
              f"{n} solid(s) ({yol})")
        if n != 1:
            print(f"    WARNING: {n} separate solids remain — the parts may "
                  f"NOT BE TOUCHING. Check with distance(a, b).")
        if not sonuc.isValid():
            print("    WARNING: result isValid() is False")

        durum, sure = _kati_baski_gercegi(sonuc)
        if durum is None:
            print(f"    the print check COULD NOT RUN ({sure:.1f} s) — it was "
                  f"NOT VERIFIED that the result is printable")
        else:
            sorunlar = _baski_verdikti(durum)
            if sorunlar:
                print(f"    NOT READY TO PRINT ({sure:.1f} s, "
                      f"{durum.get('facet')} facets):")
                for s in sorunlar:
                    print(f"      - {s}")
                print("      The shape is valid as a SOLID but the mesh going "
                      "to the slicer is broken. Do not export before fixing this.")
            else:
                print(f"    ready to print: closed, not self-intersecting, one "
                      f"component ({sure:.1f} s, {durum.get('facet')} facets)")
    return nesne
