"""Turns the open document into text.

A rule followed from the start: **the selection section is the most valuable
byte.** "Make this face 3 mm deeper" only works when the selected sub-element
name (Face7), the feature that produced it AND what that face is (plane or
cylinder, which way it faces, what radius) are all known.

MEASURED: this was the most frequently repeated loss. The user picks a face
in 3D and says "this one"; only `sub=Face7` reached the model. The model did
NOT KNOW whether Face7 was a plane or a cylinder, where it faced or what its
diameter was, and guessed. A wrong guess cost another turn.

BUDGET BEHAVIOUR. The old version cut the text from the end; at the limit
that trimmed the tail of the object list first and then, if needed, the
selection — i.e. it threw away the most valuable bytes first. New
behaviour: the header and the selection are NEVER trimmed; trimming only
happens in the object list and follows relevance (selected objects >
neighbours of the selection > the rest). A cheap version of ordering by
graph distance.
"""

from __future__ import annotations

import math

import FreeCAD as App

BUTCE = 12_000  # characters

# Short type names used in sub-element summaries. Part's class names
# ('Plane', 'Cylinder', ...) are already short and clear; only the long
# ones are abbreviated.
_TIP_KISA = {
    "BSplineSurface": "bspline",
    "SurfaceOfRevolution": "revolution",
    "SurfaceOfExtrusion": "extrusion",
    "BSplineCurve": "bspline",
    "ArcOfCircle": "arc",
    "ArcOfEllipse": "arc_ellipse",
}


def _sayi(x) -> str:
    try:
        v = float(x)
        # Turn -0.0 into zero: OCC produces it a lot on axes and
        # 'axis=(-0,-0,-1)' is both ugly and makes the reader pause over
        # "what does minus zero mean".
        if v == 0:
            v = 0.0
        return f"{v:.6g}"
    except Exception:
        return str(x)


def _vek(v) -> str:
    try:
        return f"({_sayi(v.x)},{_sayi(v.y)},{_sayi(v.z)})"
    except Exception:
        return ""


def _kutu(o) -> str:
    b = None
    try:
        b = o.Shape.BoundBox
    except Exception:
        # Mesh::Feature has NO Shape. In the old version this except quietly
        # returned empty, so the model NEVER saw a mesh's dimensions. The
        # log has the model's own sentence: "the diameter of the mesh object
        # is not in the context" — and so it created a measurement object in
        # the document just to learn one number.
        try:
            b = o.Mesh.BoundBox
        except Exception:
            return ""
    try:
        # For an EMPTY shape OCC gives "-inf x -inf" and 1.8e308 corners.
        # Writing that into the context is both noise and misleading: the
        # model thinks it saw a dimension. Empty shapes are already reported
        # as findings by verification.
        if not all(math.isfinite(v) for v in
                   (b.XLength, b.YLength, b.ZLength, b.XMin, b.YMin, b.ZMin)):
            return ""
        return (f"{_sayi(b.XLength)}x{_sayi(b.YLength)}x{_sayi(b.ZLength)} mm"
                f" @({_sayi(b.XMin)},{_sayi(b.YMin)},{_sayi(b.ZMin)})")
    except Exception:
        return ""


def _mesh_ozeti(o) -> str:
    """One-line status for a mesh object. Empty if it is not a mesh.

    Why these: facet count answers "how big", closed/components answers
    "is it printable". All three are free (measured: 0.01 s total at 12850
    facets) and they are what the model asks about most.
    """
    try:
        m = o.Mesh
        facet = int(m.CountFacets)
    except Exception:
        return ""
    p = [f"mesh facet={facet}"]
    try:
        p.append("closed" if m.isSolid() else "OPEN(has holes)")
    except Exception:
        pass
    try:
        n = int(m.countComponents())
        if n != 1:
            p.append(f"components={n}")
    except Exception:
        pass
    return " ".join(p)


def _tip_adi(nesne) -> str:
    ad = type(nesne).__name__
    return _TIP_KISA.get(ad, ad.lower())


def _alt_eleman(o, ad: str):
    """'Face7' -> Part.Face. None if not found; NEVER raises."""
    try:
        return o.Shape.getElement(ad)
    except Exception:
        pass
    try:
        return getattr(o.Shape, ad)
    except Exception:
        return None


def _alt_eleman_ozeti(o, ad: str) -> str:
    """GEOMETRIC summary of the selected face/edge — one short line.

    Example output:
        plane area=1200 normal=(0,0,1)
        cylinder r=4 axis=(0,0,1) area=75.4
        line len=20
        circle r=3 center=(10,0,5)
    """
    e = _alt_eleman(o, ad)
    if e is None:
        return ""

    p: list[str] = []

    yuzey = getattr(e, "Surface", None)
    egri = getattr(e, "Curve", None)

    if yuzey is not None:                       # --- face ---
        p.append(_tip_adi(yuzey))
        # Radius: direct on cylinder/sphere/torus; a cone has two radii.
        for alan, etiket in (("Radius", "r"), ("Radius1", "r1"),
                             ("Radius2", "r2")):
            d = getattr(yuzey, alan, None)
            if d is not None:
                p.append(f"{etiket}={_sayi(d)}")
        eksen = getattr(yuzey, "Axis", None)
        if eksen is not None:
            # On a plane, Axis is the normal itself; on curved surfaces the rotation axis.
            p.append(("normal=" if _tip_adi(yuzey) == "plane" else "axis=")
                     + _vek(eksen))
        merkez = getattr(yuzey, "Center", None)
        if merkez is not None:
            p.append("center=" + _vek(merkez))
        try:
            p.append(f"area={_sayi(e.Area)}")
        except Exception:
            pass

    elif egri is not None:                      # --- edge ---
        p.append(_tip_adi(egri))
        d = getattr(egri, "Radius", None)
        if d is not None:
            p.append(f"r={_sayi(d)}")
        merkez = getattr(egri, "Center", None)
        if merkez is not None:
            p.append("center=" + _vek(merkez))
        try:
            p.append(f"len={_sayi(e.Length)}")
        except Exception:
            pass

    else:                                       # --- vertex ---
        nokta = getattr(e, "Point", None)
        if nokta is not None:
            p.append("vertex=" + _vek(nokta))

    return " ".join(x for x in p if x)


def _yerlesim(o) -> str:
    """Write a non-identity Placement. Stay silent if identity — do not waste bytes."""
    try:
        yer = o.Placement
        taban, donme = yer.Base, yer.Rotation
        bos_taban = taban.Length < 1e-9
        bos_donme = abs(donme.Angle) < 1e-9
        if bos_taban and bos_donme:
            return ""
        parca = []
        if not bos_taban:
            parca.append("pos=" + _vek(taban))
        if not bos_donme:
            parca.append(f"rot={_sayi(donme.Angle * 180.0 / 3.141592653589793)}"
                         f"deg@{_vek(donme.Axis)}")
        return " ".join(parca)
    except Exception:
        return ""


def _secim() -> tuple[list[str], set[str]]:
    """Selected objects + sub-elements + the feature that made them + geometry.

    Returns: (lines, selected object names). The names are needed to set
    priority when trimming to budget.
    """
    satir: list[str] = []
    adlar: set[str] = set()
    try:
        import FreeCADGui as Gui
        secimler = Gui.Selection.getSelectionEx()
    except Exception:
        return satir, adlar

    for s in secimler:
        o = s.Object
        adlar.add(o.Name)
        temel = f"  {o.Name} ({o.TypeId}) label={o.Label!r}"

        # The selected object's own size and position — to see what grows
        # when told "make this 3 mm bigger".
        ek = []
        k = _kutu(o)
        if k:
            ek.append("bbox=" + k)
        m = _mesh_ozeti(o)
        if m:
            ek.append(m)
        y = _yerlesim(o)
        if y:
            ek.append(y)
        nesne_satiri = temel + (("  " + " ".join(ek)) if ek else "")

        alt = list(s.SubElementNames or ())
        if not alt:
            satir.append(nesne_satiri)
            continue

        satir.append(nesne_satiri)
        for ad in alt:
            iz = ""
            try:
                # WHICH feature produced this face/edge — the answer to "change that"
                gecmis = o.getElementHistory(ad)
                if gecmis:
                    iz = (f"  <- {gecmis[0][0].Name}"
                          if hasattr(gecmis[0][0], "Name") else "")
            except Exception:
                pass
            nokta = ""
            try:
                p = s.PickedPoints[alt.index(ad)]
                nokta = f" picked={_vek(p)}"
            except Exception:
                pass
            ozet = _alt_eleman_ozeti(o, ad)
            satir.append(f"    sub={ad}"
                         + (f" {ozet}" if ozet else "")
                         + nokta + iz)
    return satir, adlar


def _komsular(doc, secili: set[str]) -> set[str]:
    """One hop beyond the selection: its inputs and whatever uses it."""
    yakin: set[str] = set()
    for ad in secili:
        o = doc.getObject(ad)
        if o is None:
            continue
        for liste in ("OutList", "InList"):
            try:
                for x in getattr(o, liste, ()) or ():
                    yakin.add(x.Name)
            except Exception:
                pass
    return yakin - secili


def _kirpma_notu(n: int) -> str:
    return (f"  … {n} objects trimmed for budget "
            f"(selection and its neighbours kept)")


# Room the note line takes in the budget. The number of digits is not known
# in advance, so the widest case is measured.
_NOT_PAYI = len(_kirpma_notu(999_999)) + 1


def _nesne_satiri(o) -> str:
    girdi = [f"  {o.Name} ({o.TypeId})"]
    if o.Label and o.Label != o.Name:
        girdi.append(f"label={o.Label!r}")
    k = _kutu(o)
    if k:
        girdi.append(k)
    m = _mesh_ozeti(o)
    if m:
        girdi.append(m)
    try:
        bagli = [x.Name for x in o.OutList]
        if bagli:
            girdi.append("<- " + ",".join(bagli[:4]))
    except Exception:
        pass
    return " ".join(girdi)


def belge_metni(doc=None, butce: int = BUTCE) -> str:
    doc = doc or App.ActiveDocument
    if doc is None:
        return "<document>No document is open.</document>"

    bas: list[str] = ["<document>"]
    basi = f"name={doc.Name} label={doc.Label!r} objects={len(doc.Objects)}"
    # App.Document has NO 'Modified' (tried on 1.1, AttributeError).
    # isTouched() tells whether there are unsaved changes.
    try:
        basi += f" touched={bool(doc.isTouched())}"
    except Exception:
        pass
    bas.append(basi)
    if getattr(doc, "FileName", ""):
        bas.append(f"file={doc.FileName}")

    # TOP OF THE UNDO STACK. The model may ask for an undo, but it can only
    # undo its own work; asking without seeing what is on top would be
    # blind. The first three entries are enough and keep the line short.
    try:
        adlar = list(getattr(doc, "UndoNames", ()) or ())
        if adlar:
            bas.append("undo_stack=" + " | ".join(adlar[:3]))
    except Exception:
        pass

    # Active Body — in PartDesign it decides where new features go
    try:
        import FreeCADGui as Gui
        gorunum = Gui.ActiveDocument.ActiveView
        body = gorunum.getActiveObject("pdbody")
        if body is not None:
            bas.append(f"active_body={body.Name}")
    except Exception:
        pass

    sec, secili = _secim()
    bas.append("<selection>")
    bas.extend(sec if sec else ["  (nothing selected)"])
    bas.append("</selection>")

    # --- object list -----------------------------------------------------
    # TopologicalSortedObjects on an EMPTY document prints the warning
    # "cyclic dependency detected (no root object)" to the FreeCAD console —
    # harmless, but it would litter the Report view every turn. With fewer
    # than 2 objects sorting is meaningless anyway.
    sirali = doc.Objects
    if len(doc.Objects) > 1:
        try:
            sirali = doc.TopologicalSortedObjects
        except Exception:
            pass

    yakin = _komsular(doc, secili) if secili else set()
    # (priority, order, text) — priority 0 is the most valuable.
    kayit = []
    for i, o in enumerate(sirali):
        if o.Name in secili:
            oncelik = 0
        elif o.Name in yakin:
            oncelik = 1
        else:
            oncelik = 2
        kayit.append([oncelik, i, _nesne_satiri(o)])

    # Length is computed EXACTLY, not estimated: lines are joined with "\n",
    # so each line costs its own length + 1, except the closing line.
    sabit_uzunluk = (sum(len(x) + 1 for x in bas)
                     + len("<objects>") + 1
                     + len("</objects>") + 1
                     + len("</document>"))
    toplam = sabit_uzunluk + sum(len(x[2]) + 1 for x in kayit)

    # Trim order: lowest priority first, and within that group the OLDEST
    # object. Start from the oldest because the end of the document is
    # usually where work is happening (the tip in PartDesign, the last
    # boolean in Part); the beginning holds origin planes and base sketches
    # — their names are already in CLAUDE.md and need not be repeated.
    atilacak = sorted(range(len(kayit)), key=lambda i: (-kayit[i][0], kayit[i][1]))
    dusen = 0
    for i in atilacak:
        if toplam <= butce:
            break
        if kayit[i][0] == 0:
            break                      # a selected object is NEVER dropped
        if dusen == 0:
            # The trim note ITSELF eats budget too. The first measurement
            # forgot it and produced 1232 characters where 1200 was asked.
            toplam += _NOT_PAYI
        toplam -= len(kayit[i][2]) + 1
        kayit[i] = None
        dusen += 1

    p = bas + ["<objects>"]
    p.extend(k[2] for k in kayit if k is not None)
    if dusen:
        p.append(_kirpma_notu(dusen))
    p.append("</objects>")
    p.append("</document>")

    metin = "\n".join(p)
    if len(metin) > butce:
        # Only reached if the SELECTION alone exceeds the budget — if it does
        # not fit even with the object list emptied. A crude cut, but the tag
        # is closed: a half-finished <document> confuses the model.
        kuyruk = "\n… (context trimmed)\n</document>"
        metin = metin[:max(0, butce - len(kuyruk))] + kuyruk
    return metin
