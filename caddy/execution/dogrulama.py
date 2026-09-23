"""DETERMINISTIC geometry check after code runs.

WHY IT EXISTS. CADdy needed two verification layers and had one. The visual
check catches SEMANTIC mistakes — "the ear went to the wrong place", "the
parts do not touch". What it cannot catch is broken topology that looks
normal to the eye. A deterministic check catches that, and that layer was
missing.

The split is:

    deterministic check  ->  DECIDES pass/fail
    visual check         ->  catches what the deterministic one does not encode

The idea comes from earthtojake/text-to-cad's `inspection-and-validation.md`.
Its two warnings were MEASURED on FreeCAD 1.1.1 and both held:

  1. `isValid()` DOES NOT CATCH A REVERSED SOLID. For
     Part.makeBox(10,10,10).reversed(), isValid() -> True, Volume ->
     -999.9999. Topological validity accepts an inside-out body; only the
     SIGN OF THE VOLUME catches it. A reversed solid looks like "a hole in
     the world" in 3D and breaks booleans.

  2. VOLUMES ARE NEVER SUMMED, each solid is checked on its own. Measured:
     a compound containing +1000 and -1000 has `.Volume` **0.0**. A check
     looking at the total sees nothing.

The third is our own measurement:

  3. AN OPEN SHELL passes isValid() too. A five-faced box: isValid() ->
     True, isClosed() -> False, Solids -> 0. "Valid", yet unprintable.

The fourth is on the MESH side, the same pattern again:

  4. `mesh.isSolid()` alone is not enough either. Measured: for the mesh of
     two interpenetrating boxes isSolid() -> True but
     hasSelfIntersections() -> True and countComponents() -> 2. Being
     "closed" does not mean printable.

COST (measured, 36-face solid): isValid 0.043 s, isClosed ~0, Solids and
Volume 0.001 s, BoundBox ~0. isValid grows with face count, so both time
and object count are budgeted.
Mesh side (measured, 12850 facets): isSolid 0.008, hasSelfIntersections
0.024, hasNonManifolds 0.005, countComponents 0.001 s.

HONESTY RULE. The report separates checks that RAN from those that did not.
A check that did not run is not silently counted as "clean"; its name goes
into `atlanan` and reaches the model with the reason. Why: a model counts a
check it never saw as passed and reports "verified" — in the source file's
words, *"report only checks that were actually run"*.

LAYER RULE: no Qt here, only FreeCAD. It must be testable without a GUI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import FreeCAD as App

from .. import log

# Maximum objects checked in one run, and total time. Both are upper
# bounds; when exceeded the check STOPS and says so in the report.
AZAMI_NESNE = 25
SURE_BUTCESI = 1.5          # seconds

# Types NOT EXPECTED to produce a solid. A sketch having no solid is not a
# defect; reporting these as "no solid produced" would be crying wolf, and
# the model would stop taking real findings seriously.
_KATI_BEKLENMEYEN = (
    "Sketcher::",
    "Part::Part2DObject",
    "App::Origin",
    "App::Plane",
    "App::Line",
    "App::DocumentObjectGroup",
    "PartDesign::Plane",
    "PartDesign::Line",
    "PartDesign::Point",
)


@dataclass
class Bulgu:
    nesne: str
    tur: str
    ayrinti: str

    def __str__(self) -> str:
        return f"{self.nesne}: {self.tur} — {self.ayrinti}"


@dataclass
class Rapor:
    kosan: list[str] = field(default_factory=list)
    atlanan: list[str] = field(default_factory=list)
    bulgular: list[Bulgu] = field(default_factory=list)
    olcumler: list[str] = field(default_factory=list)
    bakilan: int = 0
    sure_sn: float = 0.0

    @property
    def temiz(self) -> bool:
        return not self.bulgular

    def metin(self) -> str:
        """Text sent to the model. Kept short — it is sent after every run."""
        if not self.kosan and not self.atlanan:
            return ""
        p = [f"verification: {self.bakilan} objects, {self.sure_sn:.2f} s"]
        if self.kosan:
            p.append("  checks run: " + ", ".join(self.kosan))
        for a in self.atlanan:
            p.append("  NOT RUN: " + a)
        for o in self.olcumler:
            p.append("  " + o)
        for b in self.bulgular:
            p.append("  FINDING " + str(b))
        if not self.bulgular and self.kosan:
            p.append("  no findings (only for the checks run above)")
        return "\n".join(p)


def _kati_beklenir_mi(o) -> bool:
    tip = getattr(o, "TypeId", "") or ""
    return not any(tip.startswith(x) for x in _KATI_BEKLENMEYEN)


def _sayi(x) -> str:
    # Same formatting as olcum._sayi: no scientific notation (a log showed
    # "volume=1.2e+06 mm3" for a 200x200x30 plate).
    try:
        v = float(x)
        if abs(v) >= 10000:
            return f"{v:.0f}"
        return f"{v:.6g}"
    except Exception:
        return str(x)


def _mesh_al(o):
    """The object's mesh (Mesh::Feature) or None. NEVER raises."""
    try:
        m = getattr(o, "Mesh", None)
    except Exception:
        return None
    # A Mesh::Feature's Mesh is a MeshObject; other types may have an
    # unrelated property with the same name, so we check for a method.
    return m if m is not None and hasattr(m, "CountFacets") else None


def _bir_mesh(o, m, rapor: Rapor) -> None:
    """Checks a mesh object.

    WHY A SEPARATE PATH. A Mesh::Feature has NO `Shape`. In the old version
    _bir_nesne returned on the first line with `Shape is None`, so meshes
    were NEVER visible to verification. A log review measured the cost: the
    main object of the last four real sessions was a mesh, and this layer
    did not run a single check in any of them. Downloaded models arrive as
    meshes, so this is the main workflow too.

    `isSolid()` LIES TOO — measured: for the mesh of two interpenetrating
    boxes isSolid() -> True, hasSelfIntersections() -> True,
    countComponents() -> 2. Being "closed" is not enough; intersections and
    component count must be asked separately. The mesh counterpart of the
    isValid() pattern (see the module header).

    COST (measured, 12850 facets): isSolid 0.008, hasSelfIntersections
    0.024, hasNonManifolds 0.005, countComponents 0.001 s. Together a
    fiftieth of the time budget — they all run.
    """
    ad = o.Name
    hazir, engeller, olcumler = baskiya_hazir_mesh(m)

    for tur, ayrinti in engeller:
        rapor.bulgular.append(Bulgu(ad, tur, ayrinti))
    if olcumler:
        rapor.olcumler.append(f"{ad}: " + " ".join(olcumler))
    # This line lets the model answer "is it ready" with a measurement, not
    # an opinion. Users ask this in almost every session.
    rapor.olcumler.append(
        f"{ad}: print-ready = {'YES' if hazir else 'NO'}")


def baskiya_hazir_mesh(m) -> tuple[bool, list[tuple[str, str]], list[str]]:
    """(ready, [(kind, detail)...], [measurement...]). NEVER raises.

    "Print-ready" = a state a 3D printer's slicer will accept: a closed
    (watertight), non-self-intersecting, manifold, single-component mesh
    with positive volume. FreeCAD provides all of these out of the box;
    the only missing piece was asking.
    """
    engeller: list[tuple[str, str]] = []
    olcumler: list[str] = []

    def sor(cagri, varsayilan=None):
        try:
            return cagri()
        except Exception:
            return varsayilan

    facet = sor(lambda: int(m.CountFacets), 0)
    olcumler.append(f"facet={facet}")

    b = sor(lambda: m.BoundBox)
    if b is not None:
        olcumler.append(f"bbox={_sayi(b.XLength)}x{_sayi(b.YLength)}"
                        f"x{_sayi(b.ZLength)} mm")

    hacim = sor(lambda: float(m.Volume))
    if hacim is not None:
        olcumler.append(f"volume={_sayi(hacim)} mm3")

    kapali = sor(lambda: bool(m.isSolid()))
    if kapali is False:
        engeller.append(("not closed",
                         "the mesh is not watertight (open edges/holes); "
                         "a slicer will either reject it or close it by "
                         "guessing"))

    kesisme = sor(lambda: bool(m.hasSelfIntersections()))
    if kesisme:
        engeller.append(("self-intersection",
                         "surfaces pass through each other. isSolid() does "
                         "NOT catch this — measured"))

    manifold = sor(lambda: bool(m.hasNonManifolds()))
    if manifold:
        engeller.append(("non-manifold",
                         "an edge is shared by more than two faces; "
                         "produces holes/artifacts in the slicer"))

    bozuk = sor(lambda: bool(m.hasCorruptedFacets()))
    if bozuk:
        engeller.append(("corrupt facet", "degenerate triangle present"))

    parca = sor(lambda: int(m.countComponents()), 1)
    if parca is not None:
        olcumler.append(f"components={parca}")
        if parca > 1:
            engeller.append((
                "multiple components",
                f"{parca} separate shells. Fine if intended; otherwise one "
                f"of them is a leftover — this is exactly what happened in "
                f"the handle-separation attempts"))

    if hacim is not None and hacim <= 0 and facet:
        engeller.append(("volume not positive",
                         f"volume {_sayi(hacim)} — normals may be flipped "
                         f"(flipNormals/harmonizeNormals)"))

    return (not engeller), engeller, olcumler


def _desen_kontrolu(o, sekil, rapor: Rapor) -> None:
    """Did the PartDesign pattern REALLY multiply?

    MEASURED, and this is the worst kind of silent wrong: a
    `PartDesign::PolarPattern` applied to a PRIMITIVE (like
    AdditiveCylinder) gives NO error, State says "Up-to-date", the volume
    does not change — it leaves a single copy. The model says "I made 6
    holes", the document has one. (Patterns only work on SKETCH-BASED
    features — Pad/Pocket.)

    Check: the pattern's shape must differ from the shape of the
    BaseFeature it builds on. Same volume means the pattern stayed INVISIBLE.
    """
    tip = getattr(o, "TypeId", "") or ""
    if not any(tip.endswith(x) for x in
               ("PolarPattern", "LinearPattern", "Mirrored", "MultiTransform")):
        return
    try:
        taban = getattr(o, "BaseFeature", None)
        if taban is None or taban.Shape is None:
            return
        h1 = float(sekil.Volume)
        h0 = float(taban.Shape.Volume)
    except Exception:
        return
    if h0 and abs(h1 - h0) <= max(1e-6, 1e-6 * abs(h0)):
        rapor.bulgular.append(Bulgu(
            o.Name, "pattern left a single copy",
            f"volume {_sayi(h1)} — SAME as {taban.Name}, so the pattern was "
            f"not applied. No error is raised and State shows 'Up-to-date'. "
            f"Usual cause: the pattern is attached to a PRIMITIVE; it only "
            f"works on sketch-based features (Pad/Pocket). Also check that "
            f"Originals is filled and body.Tip was moved to the pattern"))


def _bir_nesne(o, rapor: Rapor) -> None:
    """Checks one object. NEVER RAISES under any condition.

    Verification runs on top of an operation that succeeded. Failing here
    would turn a job that ended well into one that ended badly.
    """
    ad = o.Name
    try:
        sekil = getattr(o, "Shape", None)
    except Exception:
        sekil = None

    if sekil is None:
        m = _mesh_al(o)
        if m is not None:
            _bir_mesh(o, m, rapor)
        return

    try:
        if sekil.isNull():
            if _kati_beklenir_mi(o):
                rapor.bulgular.append(Bulgu(ad, "empty shape",
                                            "the object has no shape"))
            return
    except Exception:
        return

    _desen_kontrolu(o, sekil, rapor)

    try:
        if not sekil.isValid():
            rapor.bulgular.append(
                Bulgu(ad, "invalid topology",
                      "Shape.isValid() False — if later booleans build on "
                      "this, the error shows up AT THE END OF THE CHAIN"))
    except Exception:
        pass

    # --- volume sign: SOLID BY SOLID, never by summing --------------------
    katilar = []
    try:
        katilar = list(sekil.Solids)
    except Exception:
        pass

    if katilar:
        toplam = 0.0
        for i, k in enumerate(katilar, start=1):
            try:
                h = float(k.Volume)
            except Exception:
                continue
            toplam += h
            if h < 0:
                rapor.bulgular.append(
                    Bulgu(ad, "reversed solid",
                          f"solid {i} has negative volume ({_sayi(h)}). "
                          f"isValid() does NOT catch this; in 3D it looks "
                          f"like a hole in the world and breaks booleans"))
            elif h == 0:
                rapor.bulgular.append(
                    Bulgu(ad, "zero volume", f"solid {i} is empty"))
        try:
            b = sekil.BoundBox
            rapor.olcumler.append(
                f"{ad}: solids={len(katilar)} volume={_sayi(toplam)} mm3 "
                f"bbox={_sayi(b.XLength)}x{_sayi(b.YLength)}x"
                f"{_sayi(b.ZLength)} mm")
        except Exception:
            pass
        return

    # --- no solid: is the shell closed -------------------------------------
    kabuklar = []
    try:
        kabuklar = list(sekil.Shells)
    except Exception:
        pass

    if kabuklar:
        acik = 0
        for k in kabuklar:
            try:
                if not k.isClosed():
                    acik += 1
            except Exception:
                pass
        if acik:
            rapor.bulgular.append(
                Bulgu(ad, "open shell",
                      f"{acik} shell(s) not closed — isValid() lets this "
                      f"through, but it cannot be printed and solid "
                      f"operations reject it"))
        return

    # Neither solid nor shell: sketch, wire, face. Not a defect, information.
    if _kati_beklenir_mi(o):
        try:
            rapor.olcumler.append(f"{ad}: not a solid ({sekil.ShapeType})")
        except Exception:
            pass




# Time budget of the overlap scan. It runs after every execution, so it adds
# directly to the turn's latency. Measured (52-object document, 1 touched
# object): 0.02 s. The budget is a ceiling for pathological cases.
CAKISMA_BUTCESI = 1.0
# How many overlap findings are written one by one; the rest are collapsed
# into one line. The reason was measured: the same finding repeated 31
# times filled both the output and the context.
CAKISMA_AZAMI_SATIR = 5


def _akraba_mi(a, b) -> bool:
    """Are the two objects in the same dependency chain (is one the other's input).

    WHY IT IS REQUIRED: the Base and Tool objects of a `Part::Cut` STAY in
    the document and the result overlaps them completely (measured:
    Cut.OutList = [A, B]). Reporting that as an overlap would produce the
    same false alarm that repeated 31 times — while nothing of the user's
    is broken.
    """
    for x, y in ((a, b), (b, a)):
        try:
            liste = getattr(x, "OutListRecursive", None) or x.OutList
        except Exception:                                        # noqa: BLE001
            liste = []
        if any(getattr(o, "Name", None) == y.Name for o in liste):
            return True
    return False


def _cakisma_taramasi(doc, adlar, rapor: "Rapor",
                      sure_butcesi: float = CAKISMA_BUTCESI) -> None:
    """Do the touched objects pass THROUGH another part.

    WHY THE HOST DOES IT (measured): the model looked at three frames, said
    "no overlap" and was wrong; the user saw it. An image cannot settle this
    question — ~4 pixels/mm in a 900x640 frame. The way to remove the chance
    of the model forgetting to ask is for the HOST to measure and report.

    THE SCOPE IS KEPT NARROW: only objects the code touched x candidates
    whose bounding box intersects them. Even a 52-object document gives a
    few pairs; a full scan (1326 pairs) took 0.33 s and cannot be paid on
    every turn.

    TOUCHING IS NOT A FINDING. In real models a sail touches the mast, a
    rail touches the hull, on purpose; counting every contact as a defect
    would bring back the false alarm that repeated 31 times. Defect =
    PASSING THROUGH.

    A CONSUMED OBJECT IS NOT A FINDING EITHER. A turn that does a
    `Part::Cut` touches three objects at once: result, base and tool. The
    base appears to "pass through" the result — because the result was
    carved out of it. Measured: most findings in the report were this. It
    is dropped from both the touched and the candidate lists (see
    kesif.tuketilmis_mi).

    A GROUP IS NOT A PART EITHER. FreeCAD GIVES an
    `App::DocumentObjectGroup` a `.Shape` — the compound of its children
    (measured: in a 2-box group, a Compound, 2 solids, volume = the sum of
    both). So the group reported every overlap of its children A SECOND
    TIME under its own name. Measured in a real session: two of three
    FINDING lines were echoes — `REF_Cihaz x D_sol_k4` and
    `REF_Cihaz x D_sag`, both 2520 mm3, both the already-reported
    `D_sol_k4 x REF_OnPanel` / `D_sag x REF_OnPanel` pair. `_akraba_mi` is
    not enough here: it protects the group against ITS OWN child, but not a
    THIRD object against the group. The candidate pool already dropped
    groups (kesif._ATLANAN); the TOUCHED side was what was missing.
    """
    from . import olcum

    if doc is None or not adlar:
        return

    t0 = time.time()
    from . import kesif as _kesif

    dokunulan = [doc.getObject(a) for a in adlar]
    dokunulan = [o for o in dokunulan if o is not None
                 and not _kesif._atlanir_mi(o)
                 and olcum._sekil_al(o) is not None
                 and not _kesif.tuketilmis_mi(o)]
    if not dokunulan:
        return

    # Candidate pool: measurable parts in the document with volume/faces.
    # Sketches and 2D scaffolding stay out — intersection curves show up
    # everywhere and none of them is a defect.
    adaylar = []
    for o in _kesif.ilgili_nesneler(doc):
        s = olcum._sekil_al(o)
        if s is None or not s.Faces:
            continue
        if _kesif.tuketilmis_mi(o):
            continue
        adaylar.append(o)

    rapor.kosan.append("overlap (touched objects x bbox-intersecting neighbours; "
                       "excluding cut bases/mirror sources)")

    gecisler = []
    bakilan = 0
    bakilmayan = 0
    zaten_yazili = 0
    gorulen = set()
    for a in dokunulan:
        for b in adaylar:
            if a.Name == b.Name:
                continue
            anahtar = tuple(sorted((a.Name, b.Name)))
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            if time.time() - t0 > sure_butcesi:
                bakilmayan += 1
                continue
            if not olcum._bbox_kesisiyor_mu(a, b):
                continue
            if _akraba_mi(a, b):
                # A boolean's input overlaps its result; not a defect.
                continue
            bakilan += 1
            d = olcum._cift_olc(a, b)
            if d.get("gecis"):
                # If the block's OWN `cakisma_kontrol` output already wrote
                # this pair we do not repeat it — same number, two
                # sentences, one prompt (measured; reason in
                # olcum._bildirilen_gecisler).
                if olcum.gecis_bildirildi_mi(d["a"], d["b"]):
                    zaten_yazili += 1
                    continue
                gecisler.append(d)

    if bakilmayan:
        rapor.atlanan.append(
            f"overlap: {bakilmayan} pairs (time limit {sure_butcesi:g} s "
            f"exceeded)")

    # ORDER OF IMPORTANCE. The list used to be in document order and the cut
    # was ARBITRARY: the 5-line ceiling could leave the heaviest overlap
    # out. Measured: the report had 7 overlaps, the first 5 were written
    # with "see the rest with cakisma_kontrol()" — the model never made
    # that call. Now engulfment ratio first, then volume: if something has
    # to be cut, cut the LIGHTEST.
    gecisler.sort(key=lambda x: (x.get("oran", 0.0), x.get("hacim", 0.0)),
                  reverse=True)
    for d in gecisler[:CAKISMA_AZAMI_SATIR]:
        rapor.bulgular.append(Bulgu(d["a"], "intersects",
                                    d["satir"].split("— ", 1)[-1]
                                    + f" (with {d['b']})"))
    if len(gecisler) > CAKISMA_AZAMI_SATIR:
        kalan = gecisler[CAKISMA_AZAMI_SATIR:]
        rapor.bulgular.append(Bulgu(
            f"{len(kalan)} more pairs", "intersects",
            "the heaviest are above (sorted by engulfment ratio); "
            "the largest of the rest is %s x %s, common volume %s mm3 — "
            "use cakisma_kontrol() for all of them"
            % (kalan[0]["a"], kalan[0]["b"],
               olcum._sayi(kalan[0].get("hacim", 0.0)))))
    # HONESTY: what is suppressed does not stay SILENT. The model should look
    # at the `cakisma_kontrol` output above, not assume "the scan found
    # nothing".
    if zaten_yazili:
        rapor.olcumler.append(
            f"overlap: {zaten_yazili} intersection(s) already written in the "
            f"block's own cakisma_kontrol output — not repeated here")
    if bakilan and not gecisler and not zaten_yazili:
        rapor.olcumler.append(
            f"overlap: {bakilan} pairs measured, none intersect "
            f"(touching is not a defect)")

def dogrula(doc, adlar, azami_nesne: int = AZAMI_NESNE,
            sure_butcesi: float = SURE_BUTCESI) -> Rapor:
    """Deterministically checks the objects in `adlar`.

    `adlar` is usually the objects the code TOUCHED (added + changed).
    Looking only at added ones is not enough: "pad.Length = 20" ADDS no
    object but can break the model — in the old version no check ran in
    that case.
    """
    rapor = Rapor()
    if doc is None or not adlar:
        return rapor

    t0 = time.time()
    rapor.kosan = ["empty shape", "topology validity",
                   "solid volume sign (per solid)", "closed shell",
                   "mesh: closed/self-intersection/manifold/components/volume",
                   "pattern really multiplied"]
    # Self-intersection is not cheap on the BRep side — OCC needs a boolean
    # test. On the MESH side it is built in and cheap (measured: 0.024 s at
    # 12850 facets), so it runs there.
    rapor.atlanan.append("self-intersection on SOLID (BRep) objects "
                         "(expensive in OCC; runs on meshes)")

    # GROUPS ARE DROPPED, and BEFORE the count limit. A group's `.Shape` is
    # the compound of its children, so its measurement line is an exact copy
    # of the child's (measured, synthetic document: "GROUP: solids=1
    # volume=1000" next to "A: solids=1 volume=1000"), and it also eats a
    # slot from the 25-object quota. Reason in _cakisma_taramasi's docstring.
    from . import kesif as _kesif
    sirali = []
    for a in adlar:
        o = doc.getObject(a)
        if o is not None and _kesif._atlanir_mi(o):
            continue
        sirali.append(a)
    if len(sirali) > azami_nesne:
        rapor.atlanan.append(
            f"{len(sirali) - azami_nesne} objects (object limit {azami_nesne})")
        sirali = sirali[:azami_nesne]

    kalan_zamansiz = 0
    for i, ad in enumerate(sirali):
        if time.time() - t0 > sure_butcesi:
            kalan_zamansiz = len(sirali) - i
            break
        o = doc.getObject(ad)
        if o is None:
            continue
        rapor.bakilan += 1
        _bir_nesne(o, rapor)

    if kalan_zamansiz:
        rapor.atlanan.append(
            f"{kalan_zamansiz} objects (time limit {sure_butcesi:g} s exceeded)")

    # OVERLAP SCAN. SEPARATE from the per-object checks because the question
    # is different: the others ask "is this object sound in itself", this
    # asks "does it pass through another part". Measured: this was the only
    # kind of defect the model missed by looking at images.
    try:
        _cakisma_taramasi(doc, adlar, rapor)
    except Exception as e:                                       # noqa: BLE001
        log.uyari(f"overlap scan failed: {e}")

    rapor.sure_sn = time.time() - t0
    return rapor


class Izleyici:
    """Collects the objects the code TOUCHED (App.addDocumentObserver).

    Why: the difference between the `onceki`/`sonraki` object sets only
    gives what was ADDED. A very common turn — "make that pad 3 mm longer"
    — adds no object. Without the set of touched objects there is nothing
    to check on that turn.

    Looking at the Touched flag is not enough either: code calling
    `doc.recompute()` itself is ALLOWED and common (needed to create a
    sketch and pad it), and that recompute clears the flags. The observer
    catches it without getting in the way — measured.

    The callbacks must NEVER raise: they run inside FreeCAD's signal chain.
    """

    def __init__(self) -> None:
        self.adlar: set[str] = set()
        self._acik = False

    def _ekle(self, nesne) -> None:
        try:
            self.adlar.add(nesne.Name)
        except Exception:
            pass

    # Names called by FreeCAD — cannot be changed.
    def slotCreatedObject(self, nesne):
        self._ekle(nesne)

    def slotChangedObject(self, nesne, ozellik):
        self._ekle(nesne)

    def slotDeletedObject(self, nesne):
        try:
            self.adlar.discard(nesne.Name)
        except Exception:
            pass

    def bagla(self) -> None:
        try:
            App.addDocumentObserver(self)
            self._acik = True
        except Exception:
            self._acik = False

    def coz(self) -> None:
        # A leaked observer fires on EVERY user action and silently piles
        # up. Detaching is called in a finally.
        if not self._acik:
            return
        try:
            App.removeDocumentObserver(self)
        except Exception:
            pass
        self._acik = False
