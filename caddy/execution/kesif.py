"""Measuring the EXISTING document top to bottom — `kesif()`, the model's first step.

WHY IT EXISTS. The user's request: "if something is built from scratch, carry
on as usual, but if it builds ON TOP of something that EXISTS, first fully
understand what it is, measure every part of it, tell the user too — then
give a professional, informed answer: 'yes, we can add a handle to this
cup, the handle span could be 24-12 mm, where do you want it'."

The logs show why this was needed: the model started work by GUESSING the
existing geometry. In one session the first question was "what is the rim
diameter" and the model did not know it; in another, five turns were spent
figuring out which part of a screw was where. In both, measuring was
ALREADY possible, nobody just did it up front.

WHO MEASURES: THE MODEL, not the host.
In the first design the host measured and put it in the context ("saves a
turn"). The user rejected that, rightly: WHAT to measure is decided BY
LOOKING AT THE TASK. The host blindly takes three sections of every object
— unnecessary on most turns, tokens on every turn. The model knows, from
"a handle will be added", what matters. Also, when the model measures, the
measurement is VISIBLE in the chat: the user sees where each number came
from and can fix the code and rerun it if needed. A host measurement is
invisible magic.

So this is a NAMESPACE HELPER: the model writes `kesif()`, and the output
comes back to it via print (see conversation._ciktiyi_yolla).

LAYER RULE: no Qt here.
"""

from __future__ import annotations

import time

import FreeCAD as App

from .. import log
from . import dogrulama, olcum

# Maximum number of objects measured by the survey, and the total time
# limit. Both are upper bounds; when exceeded the survey STOPS and says so
# in its text (the same honesty rule as in dogrulama.py).
# 8 -> 24: MEASURED on a real 52-object document, the survey stopped at 8
# objects but used only 0.48 s of its time budget (3.0 s). So the COUNT was
# the brake, while the real resource is TIME. We raise the count and leave
# braking to time; the order was prioritised too (see _oncelik).
AZAMI_NESNE = 24
SURE_BUTCESI = 3.0

# Types outside the survey: these are scaffolding, not "existing work".
_ATLANAN = (
    "App::Origin", "App::Plane", "App::Line", "App::Point", "App::Part",
    "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
    "App::DocumentObjectGroup",
)
# "App::Point" was ADDED LATER. Measured: the `saglik()` document scan wrote
# `DEFECT Origin001: NO SOLID`. That object is a datum POINT (`App::Point`,
# Shape=Vertex) — having no solid is normal. The list had `App::Plane` and
# `App::Line`, `App::Point` was forgotten; all three belong to the same
# scaffolding set.


def _atlanir_mi(o) -> bool:
    tip = getattr(o, "TypeId", "") or ""
    return any(tip.startswith(x) for x in _ATLANAN)


def _oncelik(o) -> tuple:
    """Survey order: the actual work FIRST, scaffolding AFTER.

    MEASURED: in a 52-object document only 8 were measured, and 3 of those
    8 slots went to volume-less SKETCHES (`YelkenAltKesit1`,
    `YelkenAltKesit2`, `YelkenOrtaKesit1`), because the order was
    `doc.Objects` order. So most of the sails whose overlap we were asking
    about were never measured.

    Key (smaller = first): solid with volume > shape with faces > mesh >
    the rest (sketch, wire, 2D). On a tie the visible one first — what the
    user sees on screen is the work itself.
    """
    kati = yuzey = mesh = False
    try:
        s = o.Shape
        kati = bool(s.Solids) and abs(s.Volume) > 1e-9
        yuzey = bool(s.Faces)
    except Exception:                                            # noqa: BLE001
        pass
    if not kati and not yuzey:
        try:
            mesh = hasattr(o.Mesh, "CountFacets")
        except Exception:                                        # noqa: BLE001
            mesh = False
    if kati:
        sinif = 0
    elif yuzey:
        sinif = 1
    elif mesh:
        sinif = 2
    else:
        sinif = 3
    gorunur = 0 if getattr(o, "Visibility", True) else 1
    return (sinif, gorunur)


# Properties through which an object CONSUMES another as raw material.
# Everything in Part/PartDesign/Draft that uses another name goes here; if
# an unknown type shows up the object counts as not consumed (showing too
# much beats silently dropping).
_TUKETEN_ALANLAR = ("Base", "Tool", "Shapes", "Source", "Objects",
                    "Profile", "Sections", "Spine", "Sketch", "Group")


def tuketilmis_mi(o) -> bool:
    """Is this object another object's RAW MATERIAL (cut base, mirror source)?

    MEASURED: in a pickup-truck session, **627 (77%)** of the 813
    "INTERSECTS" lines in the overlap report were such objects —
    `KabinDetay x Kabin` 37 844 mm3, `Teker1 x CamIc1` 904 mm3. Neither is
    a defect: Kabin is the uncut version of KabinDetay; CamIc1 is a cutting
    cylinder, a tool rather than a part. Every turn the model had to write a
    disclaimer "these are hidden source objects, no new problem" — the same
    false alarm repeated 31 times earlier, in a new disguise.

    TWO CONDITIONS ARE REQUIRED TOGETHER, and both came from measurement:

    * VISIBILITY alone is not enough — the user may have temporarily hidden
      a real part; it is still a part.
    * REFERENCE alone is not enough either. The first attempt was like that
      and in the same document it dropped `KapiKolu`: it is a
      `Part::Mirroring` source, but FreeCAD does NOT hide mirror sources —
      the handle is a real part on screen. `Part::Cut`/`MultiFuse`, on the
      other hand, do hide their bases.

    So the criterion is: **someone else's raw material AND FreeCAD hid it.**
    If it was not hidden it is part of the result and gets measured.
    """
    if getattr(o, "Visibility", True):
        return False
    try:
        ustler = list(getattr(o, "InList", []) or [])
    except Exception:                                            # noqa: BLE001
        return False
    for ust in ustler:
        for alan in _TUKETEN_ALANLAR:
            try:
                deger = getattr(ust, alan, None)
            except Exception:                                    # noqa: BLE001
                continue
            if deger is None:
                continue
            if deger is o:
                return True
            try:
                if any(x is o for x in deger):
                    return True
            except TypeError:
                pass
    return False


def ilgili_nesneler(doc) -> list:
    """Objects worth surveying — the bodies, without scaffolding.

    SORTED BY PRIORITY (see _oncelik): if the budget runs out, what gets
    skipped should be a sketch, not a part. The sort is STABLE (`sorted`),
    so objects of the same class keep document order.
    """
    if doc is None:
        return []
    return sorted((o for o in doc.Objects if not _atlanir_mi(o)),
                  key=_oncelik)


def kesif(nesne=None, yaz: bool = True) -> str:
    """The entry point the model calls: measures the document (or one object).

    One line: `kesif()`. Its output comes back to the model via print, so
    the "first understand what is there" step is ONE BLOCK and one turn.
    """
    if nesne is not None:
        metin = "\n".join(_bir_nesne(nesne))
    else:
        metin = kesif_metni()
    if not metin:
        metin = ("survey: nothing to measure in the document — empty "
                 "document. You are starting from scratch.")
    if yaz:
        print(metin)
    return metin


def _delik_dokumu(sekil) -> str:
    """Groups cylindrical faces by diameter: 'Ø3.4x4, Ø8x2'.

    A hole inventory is the most asked thing when adding to an existing
    part: "is there a screw hole, how many mm". Counting cylindrical faces
    does not give it exactly (a boss can be cylindrical too), but enough to
    make the model ask the right question.
    """
    try:
        yuzler = sekil.Faces
    except Exception:
        return ""
    sayac: dict[float, int] = {}
    for y in yuzler:
        try:
            yuzey = y.Surface
            if type(yuzey).__name__ != "Cylinder":
                continue
            r = round(float(yuzey.Radius), 2)
        except Exception:
            continue
        sayac[r] = sayac.get(r, 0) + 1
    if not sayac:
        return ""
    parcalar = [f"Ø{olcum._sayi(2 * r)}x{n}"
                for r, n in sorted(sayac.items(), reverse=True)]
    return "cylindrical faces: " + ", ".join(parcalar[:6])


def _bir_nesne(o) -> list[str]:
    """Survey lines for one object. NEVER raises."""
    satirlar: list[str] = []
    ad = o.Name
    etiket = f" '{o.Label}'" if getattr(o, "Label", "") != ad else ""
    satirlar.append(f"  {ad}{etiket} ({getattr(o, 'TypeId', '?')})")

    try:
        d = olcum.olc(o, yaz=False)
        if d.get("satir"):
            satirlar.append("    " + d["satir"])
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"survey measurement: {ad}: {e}")

    m = dogrulama._mesh_al(o)
    if m is not None:
        # Sections at three heights: bottom, middle, top. For revolved
        # bodies like cups/cylinders/cones these three numbers describe the
        # WHOLE shape — the model can say "rim 55, base 45, so slightly
        # conical".
        try:
            b = m.BoundBox
            h = b.ZLength
            for etiketi, z in (("bottom", b.ZMin + h * 0.05),
                               ("middle", b.ZMin + h * 0.5),
                               ("rim/top", b.ZMin + h * 0.95)):
                k = olcum.kesit_capi(o, z=z, yaz=False)
                if k.get("satir"):
                    satirlar.append(f"    {etiketi}: " + k["satir"])
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"survey section: {ad}: {e}")

        # Wall thickness: the real question of printability, measured by
        # ray casting (see olcum.duvar_kalinligi).
        try:
            k = olcum.duvar_kalinligi(o, yaz=False)
            if k.get("satir"):
                satirlar.append("    " + k["satir"])
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"survey wall: {ad}: {e}")

        try:
            hazir, engeller, _ = dogrulama.baskiya_hazir_mesh(m)
            satirlar.append(f"    print-ready = "
                            f"{'YES' if hazir else 'NO'}"
                            + ("" if hazir else
                               " (" + ", ".join(t for t, _a in engeller) + ")"))
        except Exception:
            pass
        return satirlar

    try:
        dokum = _delik_dokumu(o.Shape)
        if dokum:
            satirlar.append("    " + dokum)
    except Exception:
        pass
    return satirlar


def kesif_metni(doc=None, azami: int = AZAMI_NESNE,
                sure_butcesi: float = SURE_BUTCESI) -> str:
    """Measured summary of the document. Empty string for an empty document."""
    doc = doc or App.ActiveDocument
    nesneler = ilgili_nesneler(doc)
    if not nesneler:
        return ""

    t0 = time.time()
    satirlar = [f"SURVEY — {len(nesneler)} objects measured (deterministic, "
                f"not guessed):"]

    try:
        b = doc.BoundBox if hasattr(doc, "BoundBox") else None
    except Exception:
        b = None
    if b is not None:
        satirlar.append(f"document bounds: {olcum._sayi(b.XLength)}x"
                        f"{olcum._sayi(b.YLength)}x{olcum._sayi(b.ZLength)} mm")

    atlanan = 0
    for i, o in enumerate(nesneler):
        if i >= azami or time.time() - t0 > sure_butcesi:
            atlanan = len(nesneler) - i
            break
        try:
            satirlar.extend(_bir_nesne(o))
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"survey: {o.Name}: {e}")

    if atlanan:
        satirlar.append(f"  ... {atlanan} objects NOT measured (limit reached). "
                        f"If needed, measure by name: kesif(doc.getObject('name'))")

    satirlar.append(f"measurement time: {time.time() - t0:.2f} s")
    return "\n".join(satirlar)
