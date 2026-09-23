"""MEASUREMENT helpers the model can call from its code.

WHY THEY EXIST. The user's words: "measuring is very critical, the user
cannot keep measuring" and "it would be better if caddy measured directly".
A log review had separated two different problems:

  1. READING BACK — the model already computed a dimension but could not
     bring it back. Closed by the print channel.
  2. REAL MEASURING — a mesh has NO faces/edges, only triangles.
     "What is the rim diameter" HAS TO BE COMPUTED on a mesh.

EXISTING CODE IS USED, NO HAND-WRITTEN GEOMETRY.
The user's second warning: "measuring is very hard, research it, add
existing code if there is any". It was researched and MEASURED — all of it
was already at hand:

  * `Measure.Measurement` (FreeCAD's OWN measuring engine) works WITHOUT a
    GUI: radius/area/length/angle/delta/lineLineDistance/
    planePlaneDistance. Measured: radius() -> exactly 1.7 on a hole face.
    (App.MeasureManager, however, is EMPTY in the console — the GUI
    registers its types, so that path is unusable.)
  * `Shape.distToShape` — the SHORTEST distance between two solids, with
    contact points.
  * `Mesh.foraminate(base, dir)` — ALL points where a ray pierces the mesh.
    The industry-standard way to get wall thickness (trimesh's 'ray' method
    is the same). Measured: a 24-angle sweep in 0.010 s.
  * `Mesh.crossSections` / `Shape.slice` — a real section. NOT DEPENDENT on
    vertices (see _kesit_noktalari, a bug caught in testing).
  * `Mesh.getEigenSystem` / `Shape.optimalBoundingBox` — the object's OWN
    axes. For a tilted object "height" is only correct this way.
  * numpy 1.26 + scipy 1.16 SHIP with FreeCAD (measured). scipy's cKDTree
    gives mesh-mesh distance for 3542x3542 points in 0.032 s; brute force
    took 3.9 s for the same job (120x).
  * Taubin circle fitting (numpy, 15 lines) — the standard way in the
    literature to get a diameter from points. Finding the centre by
    averaging drifts on a section WITH A HANDLE: measured, true centre
    (5,-3), average (6.30,-3), Taubin (5.80,-3), exact after dropping an
    outlier.

They all print: the output goes back to the model automatically.

LAYER RULE: no Qt here.
"""

from __future__ import annotations

import math

import FreeCAD as App


def _np():
    """numpy — None if missing. Measuring as a whole must not depend on it."""
    try:
        import numpy
        return numpy
    except Exception:
        return None


def _sayi(x) -> str:
    """A number for humans. NEVER PRODUCES SCIENTIFIC NOTATION.

    MEASURED: a finding line came out as "common volume 5.791e+04 mm3" and
    the model waved it through as "an intentional joint overlap". Written
    as "57906 mm3", it would have been far more visible that the entire
    bulb was buried. `%.4g` switched to exponential notation above 10 000;
    in CAD, mm3 values routinely live there.
    """
    try:
        v = float(x)
        if v == 0:
            v = 0.0
        if abs(v) >= 10000:
            return f"{v:.0f}"
        return f"{v:.4g}"
    except Exception:
        return str(x)


def _mesh_al(nesne):
    try:
        m = nesne.Mesh
        return m if hasattr(m, "CountFacets") else None
    except Exception:
        return None


def _sekil_al(nesne):
    try:
        s = nesne.Shape
        return s if hasattr(s, "BoundBox") else None
    except Exception:
        return None


def _hedef(nesne):
    """The given object; otherwise the selection; otherwise the only object in the document."""
    if nesne is not None:
        return nesne
    try:
        import FreeCADGui as Gui

        secili = Gui.Selection.getSelection()
        if secili:
            return secili[0]
    except Exception:
        pass
    doc = App.ActiveDocument
    if doc is None:
        return None
    adaylar = [o for o in doc.Objects
               if _mesh_al(o) is not None or _sekil_al(o) is not None]
    return adaylar[0] if len(adaylar) == 1 else None


def _kutu(nesne):
    for al in (lambda: nesne.Mesh.BoundBox, lambda: nesne.Shape.BoundBox):
        try:
            return al()
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# 1. BASIC DIMENSIONS
# --------------------------------------------------------------------------

def _kendi_boyu(nesne):
    """The object's size along its OWN axes (three numbers) or None.

    WHY. An axis-aligned bbox makes a tilted part look bigger than it is: a
    30x10x5 box rotated 30 degrees has a 28.5x10x19.3 bbox, and saying "it
    is 19 mm thick" is wrong.

    METHOD. For a mesh `getEigenSystem()` gives this READY-MADE (FreeCAD's
    own code; measured, 55.35x95x55.38 on a cup).
    For a solid `optimalBoundingBox()` was TRIED and REJECTED: for a box
    rotated 30 degrees it returned 28.48x10x19.33, i.e. still AXIS-ALIGNED.
    Instead, vertices are projected onto the inertia axes from
    `PrincipalProperties` (for a prismatic part these are the part's own
    axes — measured, FirstAxisOfInertia = (0.5, 0, 0.866) on the rotated box).
    """
    m = _mesh_al(nesne)
    if m is not None:
        try:
            _, boy = m.getEigenSystem()
            return (boy.x, boy.y, boy.z)
        except Exception:
            return None

    s = _sekil_al(nesne)
    if s is None:
        return None
    try:
        p = s.PrincipalProperties
        eksenler = [p["FirstAxisOfInertia"], p["SecondAxisOfInertia"],
                    p["ThirdAxisOfInertia"]]
        noktalar = [v.Point for v in s.Vertexes]
        if len(noktalar) < 2:
            kose, _ = s.tessellate(0.5)
            noktalar = list(kose)
        if not noktalar:
            return None
        boy = []
        for e in eksenler:
            izd = [n.x * e.x + n.y * e.y + n.z * e.z for n in noktalar]
            boy.append(max(izd) - min(izd))
        return tuple(boy)
    except Exception:
        return None


def olc(nesne=None, yaz: bool = True) -> dict:
    """Basic dimensions of the object: size, centre, volume, area, mesh state.

    Without `nesne`: the selected object, otherwise the only object in the document.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("olc: no object to measure "
                  "(pass a name: olc(doc.getObject('cup')))")
        return {}

    d: dict = {"ad": getattr(nesne, "Name", "?")}
    satir = [f"{d['ad']}:"]

    b = _kutu(nesne)
    if b is not None:
        d.update(boy=(b.XLength, b.YLength, b.ZLength),
                 merkez=(b.Center.x, b.Center.y, b.Center.z),
                 z_alt=b.ZMin, z_ust=b.ZMax)
        satir.append(f"size={_sayi(b.XLength)}x{_sayi(b.YLength)}"
                     f"x{_sayi(b.ZLength)} mm")
        satir.append(f"center=({_sayi(b.Center.x)},{_sayi(b.Center.y)},"
                     f"{_sayi(b.Center.z)})")
        satir.append(f"z={_sayi(b.ZMin)}..{_sayi(b.ZMax)}")

    # If the axis-aligned bbox and the own axes DIFFER, say so: the object
    # is tilted, and that affects every later measurement.
    kendi = _kendi_boyu(nesne)
    if kendi and b is not None:
        hizali = sorted([b.XLength, b.YLength, b.ZLength])
        oz = sorted(kendi)
        d["kendi_boy"] = tuple(kendi)
        if any(abs(x - y) > max(0.02 * max(x, y, 1e-9), 0.1)
               for x, y in zip(hizali, oz)):
            d["yatik"] = True
            satir.append(f"(TILTED — along its own axes {_sayi(oz[2])}x"
                         f"{_sayi(oz[1])}x{_sayi(oz[0])} mm)")

    m = _mesh_al(nesne)
    if m is not None:
        for ad, etiket, cagri in (("hacim", "volume", lambda: m.Volume),
                                  ("alan", "area", lambda: m.Area),
                                  ("facet", "facet", lambda: m.CountFacets),
                                  ("parca", "components",
                                   lambda: m.countComponents())):
            try:
                v = cagri()
                d[ad] = v
                satir.append(f"{etiket}={_sayi(v)}")
            except Exception:
                pass
        try:
            d["kapali"] = bool(m.isSolid())
            satir.append("closed" if d["kapali"] else "OPEN")
        except Exception:
            pass
    else:
        s = _sekil_al(nesne)
        if s is not None:
            try:
                d["hacim"] = s.Volume
                d["alan"] = s.Area
                satir.append(f"volume={_sayi(s.Volume)} mm3")
                satir.append(f"area={_sayi(s.Area)} mm2")
                satir.append(f"solids={len(s.Solids)} faces={len(s.Faces)} "
                             f"edges={len(s.Edges)}")
            except Exception:
                pass

    d["satir"] = " ".join(satir)
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 2. SECTION / DIAMETER
# --------------------------------------------------------------------------

def _kesit_noktalari(nesne, z: float) -> list:
    """REAL section points in the z plane.

    WHY NOT A BAND OF POINTS. The first version said "collect the mesh
    vertices near z" and A TEST CAUGHT IT: on a cone-like body the mesh is
    made of long triangles from base to tip, there are NO vertices at
    intermediate heights, and the measurement silently came back empty. So
    the method depended on how the mesh was triangulated; a measurement
    cannot depend on that.

    The right way is a real intersection with the plane: `crossSections` on
    a mesh (measured: 0.033 s at 1558 facets), `Shape.slice` on a solid.
    """
    from FreeCAD import Vector

    m = _mesh_al(nesne)
    if m is not None:
        try:
            kesitler = m.crossSections([((0, 0, z), (0, 0, 1))], 0.0)
            noktalar = [p for kesit in kesitler for pl in kesit for p in pl]
            if noktalar:
                return noktalar
        except Exception:
            pass

    s = _sekil_al(nesne)
    if s is not None:
        try:
            noktalar = []
            for t in s.slice(Vector(0, 0, 1), z):
                try:
                    noktalar.extend(t.discretize(Distance=0.5))
                except Exception:
                    noktalar.extend(v.Point for v in t.Vertexes)
            return noktalar
        except Exception:
            return []
    return []


def _taubin(xs, ys):
    """Taubin circle fit — centre and radius from points.

    The literature's standard algebraic method (Taubin 1991); it fixes
    Kasa's bias toward small radii. Returns None without numpy and the
    caller falls back to the average.

    WHY THE AVERAGE IS NOT ENOUGH: if the section has a protrusion such as
    a handle, the centre drifts toward it. MEASURED — true centre (5,-3),
    average (6.30,-3), Taubin (5.80,-3), exact after dropping an outlier.
    """
    np = _np()
    if np is None:
        return None
    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    if len(x) < 5:
        return None
    mx, my = x.mean(), y.mean()
    u, v = x - mx, y - my
    z = u * u + v * v
    zm = z.mean()
    if zm <= 0:
        return None
    kok = math.sqrt(zm)
    A = np.column_stack([(z - zm) / (2 * kok), u, v])
    try:
        _, _, V = np.linalg.svd(A, full_matrices=False)
    except Exception:
        return None
    a = V[-1]
    A0 = a[0] / (2 * kok)
    B, C = a[1], a[2]
    D = -zm * a[0] / (2 * kok)
    if abs(A0) < 1e-12:
        return None
    kok2 = B * B + C * C - 4 * A0 * D
    if kok2 <= 0:
        return None
    return (-B / (2 * A0) + mx, -C / (2 * A0) + my,
            math.sqrt(kok2) / (2 * abs(A0)))


def _merkez_bul(noktalar):
    """Centre of the section — Taubin + one outlier-rejection pass, else the average."""
    np = _np()
    xs = [p.x for p in noktalar]
    ys = [p.y for p in noktalar]
    ortalama = (sum(xs) / len(xs), sum(ys) / len(ys))
    uygun = _taubin(xs, ys)
    if uygun is None or np is None:
        return ortalama

    cx, cy, r = uygun

    # DEGENERATE FIT GUARD. If the points are nearly COLLINEAR (the
    # horizontal section of a lying cylinder is two parallel lines), a circle
    # fit finds a huge circle and throws the centre far away. IT HAPPENED IN
    # A TEST: radius 7.8e8, centre (1.2e6, 3.9e8) — and since that made the
    # section look "circular", a wrong diameter was reported silently.
    # If the fitted radius is much bigger than the point cloud itself the
    # fit is meaningless; we go back to the average and the roundness check
    # (see kesit_capi) kicks in and says "NOT ROUND".
    yayilim = max(max(xs) - min(xs), max(ys) - min(ys))
    if not (r == r) or r > 3 * max(yayilim, 1e-9):
        return ortalama
    x = np.asarray(xs)
    y = np.asarray(ys)
    sapma = np.abs(np.hypot(x - cx, y - cy) - r)
    esik = 2.0 * sapma.std() if sapma.std() > 0 else None
    if esik:
        kalan = sapma <= esik
        if kalan.sum() >= max(8, 0.5 * len(xs)):
            ikinci = _taubin(x[kalan], y[kalan])
            if ikinci is not None:
                return ikinci[0], ikinci[1]
    return cx, cy


def kesit_capi(nesne=None, z=None, band=None, yaz: bool = True) -> dict:
    """SECTION measurement at a given height.

    TELLS THREE CASES APART, because giving all of them the same number
    would be wrong:

      * ONE RING, circular       -> one diameter
      * ONE RING, oval           -> MINOR and MAJOR diameter separately. An
                                    oval has no single diameter; the average
                                    would mistake it for a circle.
      * TWO RINGS (hollow body)  -> OUTER diameter, INNER diameter, WALL
                                    thickness. This is a cup/tube section.
      * NOT ROUND                -> REFUSES to say "diameter", gives the
                                    widest/narrowest size. This is what
                                    happens on a tilted object.

    Without z the TOP of the object is measured (the rim). `band` is no
    longer used (a real section is taken); accepted for backward
    compatibility.
    """
    nesne = _hedef(nesne)
    if nesne is None:
        if yaz:
            print("kesit_capi: object not found")
        return {}

    kutu = _kutu(nesne)
    if kutu is None:
        if yaz:
            print(f"kesit_capi: {getattr(nesne, 'Name', '?')} cannot be measured "
                  f"(neither mesh nor solid)")
        return {}

    if z is None:
        # A section exactly at the top comes out EMPTY (the plane is tangent
        # to the body); a touch lower gives the "rim" measurement.
        z = kutu.ZMax - max(kutu.ZLength * 0.02, 0.01)

    noktalar = _kesit_noktalari(nesne, z)
    ad = getattr(nesne, "Name", "?")
    if len(noktalar) < 8:
        if yaz:
            print(f"kesit_capi: no section found in the z={_sayi(z)} plane "
                  f"({len(noktalar)} points). The object is not at this "
                  f"height, or z is outside {_sayi(kutu.ZMin)}..{_sayi(kutu.ZMax)}.")
        return {}

    cx, cy = _merkez_bul(noktalar)

    # BUCKETING BY ANGLE: how many distinct radii at each angle? One means a
    # single ring, two means a wall.
    KOVA = 72                                    # 5 degree slices
    kovalar: dict[int, list[float]] = {}
    for p in noktalar:
        dx, dy = p.x - cx, p.y - cy
        r = math.hypot(dx, dy)
        i = int((math.atan2(dy, dx) + math.pi) / (2 * math.pi) * KOVA) % KOVA
        kovalar.setdefault(i, []).append(r)

    dis_r = [max(v) for v in kovalar.values()]
    ic_r = [min(v) for v in kovalar.values()]
    if not dis_r:
        return {}

    en_dis = max(dis_r)
    kalinliklar = sorted(d - i for d, i in zip(dis_r, ic_r))
    orta_kalinlik = kalinliklar[len(kalinliklar) // 2]

    d = {"z": z, "merkez": (cx, cy), "nokta": len(noktalar),
         "dis_cap": 2 * en_dis}

    if orta_kalinlik > max(0.02 * en_dis, 0.05):
        d["duvar"] = orta_kalinlik
        d["ic_cap"] = 2 * (en_dis - orta_kalinlik)
        d["tur"] = "wall"
        d["guvenilir"] = True
        d["satir"] = (f"{ad} section z={_sayi(z)}: outer dia={_sayi(2 * en_dis)} "
                      f"inner dia={_sayi(d['ic_cap'])} "
                      f"wall={_sayi(orta_kalinlik)} mm "
                      f"center=({_sayi(cx)},{_sayi(cy)})")
        if yaz:
            print(d["satir"])
        return d

    kucuk, buyuk = min(dis_r), max(dis_r)
    ort = sum(dis_r) / len(dis_r)
    d.update(kisa_cap=2 * kucuk, uzun_cap=2 * buyuk, ort_cap=2 * ort)

    # IS IT ROUND? "Diameter" only makes sense if the section is round about
    # the Z axis. If the object is TILTED a horizontal slice is two parallel
    # lines, not a ring; numbers still come out, but calling it a "diameter"
    # would be a lie. The first version did exactly that and a test caught
    # it: "minor diameter = 0.0000000001".
    if kucuk > 0 and buyuk / kucuk > 2.5:
        d["guvenilir"] = False
        d["tur"] = "not round"
        d["satir"] = (f"{ad} section z={_sayi(z)}: this section is NOT ROUND "
                      f"(aspect ratio {_sayi(buyuk / kucuk)}), 'diameter' is not "
                      f"a meaningful measure. Widest {_sayi(2 * buyuk)}, "
                      f"narrowest {_sayi(2 * kucuk)} mm. The object may not "
                      f"stand along Z; check its own axes with olc().")
        if yaz:
            print(d["satir"])
        return d

    d["guvenilir"] = True
    if buyuk - kucuk <= max(0.02 * buyuk, 0.05):
        d["tur"] = "circle"
        d["satir"] = (f"{ad} section z={_sayi(z)}: diameter={_sayi(2 * ort)} mm "
                      f"(circular) center=({_sayi(cx)},{_sayi(cy)})")
    else:
        d["tur"] = "oval"
        d["satir"] = (f"{ad} section z={_sayi(z)}: minor dia={_sayi(2 * kucuk)} "
                      f"major dia={_sayi(2 * buyuk)} mean={_sayi(2 * ort)} "
                      f"mm center=({_sayi(cx)},{_sayi(cy)})")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 3. WALL THICKNESS (ray casting — the industry standard)
# --------------------------------------------------------------------------

def duvar_kalinligi(nesne=None, z=None, yaz: bool = True) -> dict:
    """Wall thickness by ray casting. The real question of printability.

    METHOD: the mesh's `foraminate(base, dir)` method gives ALL points a ray
    pierces. A ray going outward from the axis pierces the INNER surface
    first, then the OUTER one; their difference is the wall at that point.
    trimesh's 'ray' method is exactly this; here FreeCAD's own code is used
    (measured: a 24-angle sweep in 0.010 s).

    The THINNEST spot is reported, not the average: that is where the print
    fails.
    """
    nesne = _hedef(nesne)
    m = _mesh_al(nesne)
    if m is None:
        if yaz:
            print("duvar_kalinligi: works on mesh objects only "
                  "(use kesit_capi for solids)")
        return {}

    b = m.BoundBox
    if z is None:
        z = b.ZMin + b.ZLength * 0.5
    merkez_x, merkez_y = b.Center.x, b.Center.y

    olcumler = []
    for derece in range(0, 360, 10):
        a = math.radians(derece)
        yon = (math.cos(a), math.sin(a), 0.0)
        try:
            vurus = m.foraminate((merkez_x, merkez_y, z), yon)
        except Exception:
            continue
        # SIGNED distances along the ray. Taking absolute distance with
        # hypot mixes hits BEHIND the ray in with those in front and pushes
        # the thickness toward zero — the first attempt did exactly that
        # (median came out 0.045 mm, the right answer was 2.1).
        t = []
        for v in vurus.values():
            uz = ((v[0] - merkez_x) * yon[0] + (v[1] - merkez_y) * yon[1])
            if uz > 1e-6:
                t.append(uz)
        t = sorted(t)
        # Facets sharing a point report it again: merge the close ones.
        temiz = []
        for x in t:
            if not temiz or x - temiz[-1] > 1e-3:
                temiz.append(x)
        if len(temiz) >= 2:
            olcumler.append((temiz[1] - temiz[0], derece))

    if not olcumler:
        if yaz:
            print(f"duvar_kalinligi: no wall found at height z={_sayi(z)} "
                  f"(the body may be solid inside)")
        return {}

    olcumler.sort()
    en_ince, aci = olcumler[0]
    ortanca = olcumler[len(olcumler) // 2][0]
    d = {"z": z, "en_ince": en_ince, "en_ince_aci": aci, "ortanca": ortanca,
         "olcum": len(olcumler)}
    d["satir"] = (f"{getattr(nesne, 'Name', '?')} wall z={_sayi(z)}: "
                  f"thinnest {_sayi(en_ince)} mm (at {aci} degrees), "
                  f"median {_sayi(ortanca)} mm, {len(olcumler)} measurements")
    if yaz:
        print(d["satir"])
        if en_ince < 0.8:
            print(f"    WARNING: {_sayi(en_ince)} mm is below the nozzle "
                  f"diameter of most 3D printers — that area cannot be "
                  f"printed or will leave a gap.")
    return d


# --------------------------------------------------------------------------
# 4. DISTANCE BETWEEN TWO OBJECTS
# --------------------------------------------------------------------------

def mesafe(a=None, b=None, yaz: bool = True) -> dict:
    """SHORTEST distance between two objects. The answer to "do they touch".

    Solid-solid: `Shape.distToShape` — exact, with contact points
    (FreeCAD/OCC's own code).
    Involving a mesh: nearest point pairs with scipy `cKDTree`. Brute force
    took 3.9 s for 3542x3542 points, cKDTree 0.032 s — 120x (measured). The
    result is POINT-BASED, so a contact in the middle of a triangle face may
    show slightly larger; that keeps the answer correct at the "do they
    touch" level, and it is reported as such.
    """
    if a is None or b is None:
        if yaz:
            print("mesafe: pass two objects — mesafe(doc.getObject('a'), "
                  "doc.getObject('b'))")
        return {}

    sa, sb = _sekil_al(a), _sekil_al(b)
    if sa is not None and sb is not None:
        try:
            uzunluk, noktalar, _ = sa.distToShape(sb)
            d = {"mesafe": uzunluk, "yontem": "distToShape"}
            p1, p2 = noktalar[0]
            d["satir"] = (f"{a.Name} <-> {b.Name}: {_sayi(uzunluk)} mm "
                          f"(closest points ({_sayi(p1.x)},{_sayi(p1.y)},"
                          f"{_sayi(p1.z)}) and ({_sayi(p2.x)},{_sayi(p2.y)},"
                          f"{_sayi(p2.z)}))")
            if yaz:
                print(d["satir"])
                if uzunluk < 1e-7:
                    print("    they touch (distance zero).")
            return d
        except Exception:
            pass

    np = _np()
    try:
        from scipy.spatial import cKDTree
    except Exception:
        cKDTree = None

    def noktalari(o):
        m = _mesh_al(o)
        if m is not None:
            return [(p.x, p.y, p.z) for p in m.Points]
        s = _sekil_al(o)
        if s is None:
            return []
        try:
            kose, _ = s.tessellate(0.5)
            return [(p.x, p.y, p.z) for p in kose]
        except Exception:
            return [(v.Point.x, v.Point.y, v.Point.z) for v in s.Vertexes]

    pa, pb = noktalari(a), noktalari(b)
    if not pa or not pb:
        if yaz:
            print("mesafe: could not read the objects' points")
        return {}

    if cKDTree is not None and np is not None:
        agac = cKDTree(np.asarray(pb))
        uzakliklar, _ = agac.query(np.asarray(pa), k=1)
        en_kisa = float(uzakliklar.min())
    else:
        en_kisa = min(
            math.dist(p, q) for p in pa[::max(1, len(pa) // 400)]
            for q in pb[::max(1, len(pb) // 400)])

    d = {"mesafe": en_kisa, "yontem": "point-based (mesh)"}
    d["satir"] = (f"{getattr(a, 'Name', 'a')} <-> {getattr(b, 'Name', 'b')}: "
                  f"~{_sayi(en_kisa)} mm (between mesh points; a contact in "
                  f"the middle of a triangle face may show slightly larger)")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 5. SIZE OF A SELECTED FACE/EDGE — FreeCAD's own engine
# --------------------------------------------------------------------------

def olcu(nesne=None, alt: str = "", yaz: bool = True) -> dict:
    """Radius, area, length of a face/edge — via Measure.Measurement.

    This is FreeCAD's OWN measuring engine and it works without a GUI
    (measured: radius() -> exactly 1.7 on a hole face). Ask here directly
    instead of fitting a hole diameter by hand.

    Without `alt`, the sub-element in the selection is used.
    """
    try:
        import Measure
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"olcu: no Measure module ({e})")
        return {}

    if nesne is None or not alt:
        try:
            import FreeCADGui as Gui

            secim = Gui.Selection.getSelectionEx()
            if secim and secim[0].SubElementNames:
                nesne = nesne or secim[0].Object
                alt = alt or secim[0].SubElementNames[0]
        except Exception:
            pass
    if nesne is None or not alt:
        if yaz:
            print("olcu: needs an object and a sub-element — "
                  "olcu(doc.getObject('Box'), 'Face7')")
        return {}

    m = Measure.Measurement()
    try:
        m.addReference3D(nesne.Name, alt)
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"olcu: could not add {alt} ({e})")
        return {}

    d = {"nesne": nesne.Name, "alt": alt}
    parcalar = []
    for ad, etiket, cagri in (("yaricap", "radius", m.radius),
                              ("uzunluk", "length", m.length),
                              ("alan", "area", m.area)):
        try:
            v = float(cagri())
        except Exception:
            continue
        if v and v == v:                       # not NaN
            d[ad] = v
            parcalar.append(f"{etiket}={_sayi(v)}")
            if ad == "yaricap":
                parcalar.append(f"diameter={_sayi(2 * v)}")
    d["satir"] = f"{nesne.Name}.{alt}: " + (" ".join(parcalar) or "could not measure")
    if yaz:
        print(d["satir"])
    return d


# --------------------------------------------------------------------------
# 6. OVERLAP — the DETERMINISTIC answer to "do they touch, does one pass through"
# --------------------------------------------------------------------------

# Volume threshold: an OCC boolean may return volumes very close to, but
# not exactly, zero on tangent faces. 1e-3 mm3 is smaller than a 0.1 mm cube
# — no real overlap falls below it.
_HACIM_ESIGI = 1e-3
# Intersection-curve length threshold: if two surfaces really intersect,
# section() returns edges with length. A single tangent point gives zero.
_KESIT_ESIGI = 1e-6
# Distance counted as zero (numeric noise of distToShape).
_TEMAS_ESIGI = 1e-7


def _bbox_kesisiyor_mu(a, b, pay: float = 0.0) -> bool:
    """Do the two objects' bounding boxes overlap. A CHEAP pre-filter.

    Why it is needed: n objects give n*(n-1)/2 pairs and every boolean call
    is expensive in OCC. A 52-object document means 1326 pairs; the bbox
    test drops the vast majority in microseconds.
    """
    ka, kb = _kutu(a), _kutu(b)
    if ka is None or kb is None:
        return True              # if we don't know we don't drop, let measuring decide
    return not (ka.XMax + pay < kb.XMin or kb.XMax + pay < ka.XMin
                or ka.YMax + pay < kb.YMin or kb.YMax + pay < ka.YMin
                or ka.ZMax + pay < kb.ZMin or kb.ZMax + pay < ka.ZMin)


def _kati_mi(sekil) -> bool:
    """Does the shape have volume (solid) or is it thin (surface/shell/wire)."""
    try:
        return bool(sekil.Solids) and abs(sekil.Volume) > _HACIM_ESIGI
    except Exception:                                            # noqa: BLE001
        return False


def _sinirda_mi(nokta, sekil) -> bool:
    """Is the point on the shape's EDGE (i.e. boundary, not interior).

    Why it is needed: when two surfaces TOUCH end to end, `section()` also
    returns a curve with length (measured: 10 mm). What separates touching
    from PASSING THROUGH is whether the intersection curve is INSIDE a
    shape or on its BOUNDARY.
    """
    try:
        import Part as _Part

        kenarlar = sekil.Edges
        if not kenarlar:
            return False
        return _Part.Compound(kenarlar).distToShape(
            _Part.Vertex(nokta))[0] < 1e-6
    except Exception:                                            # noqa: BLE001
        return False


def _egri_ici_geciyor_mu(kesit, sa, sb) -> bool:
    """Does the intersection curve run through the interior of AT LEAST ONE of the shapes.

    If it lies on the boundary of both, it is TOUCHING (end to end, edge to
    edge), which is not a defect here. If it is inside one of them it is
    passing through — exactly the case in the log: "the EDGE of each jib
    running to the mast cuts one of these strips", i.e. A's boundary passes
    through B's interior.
    """
    for e in kesit.Edges:
        try:
            orta = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
        except Exception:                                        # noqa: BLE001
            continue
        if not (_sinirda_mi(orta, sa) and _sinirda_mi(orta, sb)):
            return True
    return False


def _cift_olc(a, b) -> dict:
    """Measurement for one pair — the right test is chosen by shape KIND.

    MEASURED in a real session and measured again here with real OCC
    geometry:

      solid x solid     -> `common().Volume`. For two boxes TOUCHING side by
                           side the volume is 0 but `section()` gives 40 mm;
                           so section MISLEADS in this case, volume does not.
      solid x surface   -> `common()` returns an AREA; but it also returns
                           area when the surface lies exactly on one of the
                           solid's faces (measured: 100 mm2 in both cases).
                           `isInside` makes the distinction: is the centroid
                           of the common part REALLY inside the solid.
      surface x surface -> the `section()` curve; to tell touching from
                           passing through, we check whether the curve lies
                           on the BOUNDARY of both (see _egri_ici_geciyor_mu).

    `distToShape` is measured in every case: it answers "do they touch".

    Returns: {"hukum", "mesafe", "hacim", "kesit_uzunluk", "satir", "gecis"}
    """
    sa, sb = _sekil_al(a), _sekil_al(b)
    ad_a = getattr(a, "Name", "a")
    ad_b = getattr(b, "Name", "b")
    d: dict = {"a": ad_a, "b": ad_b, "hacim": 0.0, "kesit_uzunluk": 0.0,
               "gecis": False}

    if sa is None or sb is None:
        # Mesh side: NO common/section. Only distance can be measured and
        # that is SAID — the "do not make up what you could not measure" rule.
        m = mesafe(a, b, yaz=False)
        if not m:
            d["hukum"] = "not measured"
            d["mesafe"] = float("nan")
            d["satir"] = f"{ad_a} <-> {ad_b}: not measured (neither shape nor mesh)"
            return d
        d["mesafe"] = m.get("mesafe", 0.0)
        d["hukum"] = "touching" if d["mesafe"] < _TEMAS_ESIGI else "apart"
        d["satir"] = (f"{ad_a} <-> {ad_b}: {_sayi(d['mesafe'])} mm "
                      f"(mesh — pass-through test NOT RUN, distance only)")
        return d

    try:
        d["mesafe"] = float(sa.distToShape(sb)[0])
    except Exception:                                            # noqa: BLE001
        d["mesafe"] = float("nan")

    kati_a, kati_b = _kati_mi(sa), _kati_mi(sb)
    ortak = None
    try:
        ortak = sa.common(sb)
        d["hacim"] = float(getattr(ortak, "Volume", 0.0) or 0.0)
        d["ortak_alan"] = float(getattr(ortak, "Area", 0.0) or 0.0)
    except Exception:                                            # noqa: BLE001
        d["hacim"] = 0.0
        d["ortak_alan"] = 0.0

    kesit = None
    try:
        kesit = sa.section(sb)
        d["kesit_uzunluk"] = float(sum(e.Length for e in kesit.Edges))
    except Exception:                                            # noqa: BLE001
        d["kesit_uzunluk"] = 0.0

    nasil: list[str] = []
    if kati_a and kati_b:
        # Volume does not mislead; section also returns the contact curve here.
        if d["hacim"] > _HACIM_ESIGI:
            d["gecis"] = True
            nasil.append(f"common volume {_sayi(d['hacim'])} mm3")
            # SIZE OF THE DEFECT — the raw volume does NOT TELL it.
            # MEASURED: the model waved the line "common volume 5.791e+04
            # mm3" through as "an intentional joint overlap". But that
            # volume was the ENTIRE bulb: the bulb was buried inside the
            # lampshade, i.e. the shade was a solid cone when it should
            # have been hollow. In the same session a 2872 mm3 joint overlap
            # really was intentional. What separates the two is not the SIZE
            # of the volume but how much of the smaller part is swallowed.
            # Without that ratio the model only decides right by luck.
            try:
                ha, hb = float(sa.Volume), float(sb.Volume)
                kucuk = min(ha, hb)
                ad_kucuk = ad_a if ha <= hb else ad_b
                if kucuk > 0:
                    oran = d["hacim"] / kucuk
                    d["oran"] = oran
                    d["oran_nesne"] = ad_kucuk
                    yuzde = oran * 100
                    if oran >= 0.98:
                        nasil.append(f"{ad_kucuk} FULLY BURIED "
                                     f"(100% of its volume inside)")
                    elif yuzde < 1.0:
                        # We will NOT write "0%". Measured: a real 237.8 mm3
                        # overlap came out as "0% of AltKol's volume" —
                        # rounding dropped it to zero and the line read like
                        # "no overlap". Writing a number that makes the
                        # defect look ABSENT while reporting it breaks the
                        # report itself.
                        nasil.append(f"less than 1% of {ad_kucuk}'s volume")
                    else:
                        nasil.append(f"{yuzde:.0f}% of {ad_kucuk}'s volume")
            except Exception:                                    # noqa: BLE001
                pass
    elif kati_a or kati_b:
        # How much of the surface is INSIDE the solid. A surface lying on a
        # face also gives an area, so we check whether the centre of the
        # common part is really inside.
        kati_sekil = sa if kati_a else sb
        if ortak is not None and d.get("ortak_alan", 0.0) > _KESIT_ESIGI:
            iceride = False
            try:
                for f in ortak.Faces:
                    if kati_sekil.isInside(f.CenterOfMass, 1e-7, False):
                        iceride = True
                        break
            except Exception:                                    # noqa: BLE001
                iceride = True          # if we cannot decide, we do not stay silent
            if iceride:
                d["gecis"] = True
                nasil.append(f"{_sayi(d['ortak_alan'])} mm2 of the surface "
                             f"is inside the solid")
    else:
        # Two surfaces: if the curve is on both boundaries it is TOUCHING,
        # otherwise passing through.
        if (kesit is not None and d["kesit_uzunluk"] > _KESIT_ESIGI
                and _egri_ici_geciyor_mu(kesit, sa, sb)):
            d["gecis"] = True
            nasil.append(f"intersection curve {_sayi(d['kesit_uzunluk'])} mm")

    if d["gecis"]:
        d["hukum"] = "INTERSECTS"
        d["satir"] = f"{ad_a} x {ad_b}: INTERSECTS — " + ", ".join(nasil)
    elif d["mesafe"] < _TEMAS_ESIGI:
        d["hukum"] = "touching"
        d["satir"] = (f"{ad_a} <-> {ad_b}: touching (0 mm) — does NOT pass "
                      f"through (no common volume, no intersection curve)")
    else:
        d["hukum"] = "apart"
        d["satir"] = f"{ad_a} <-> {ad_b}: {_sayi(d['mesafe'])} mm apart"
    return d


# INTERSECTIONS ALREADY WRITTEN TO THE MODEL IN THIS BLOCK.
#
# MEASURED: after every new part the model calls `cakisma_kontrol(odak=...)`,
# and THEN the host's verification scan finds the same pairs again and
# writes them as FINDINGS. The same number, in two different sentences,
# inside one prompt:
#
#   FINDING RollbarKiris: intersects - common volume 10.42 mm3,
#         16% of RollbarDikme1's volume (with RollbarDikme1)
#   RollbarKiris x RollbarDikme1: INTERSECTS - common volume 10.42 mm3,
#         16% of RollbarDikme1's volume
#
# ~950 characters in that one block, and in most of the session's 52
# blocks. In a session whose context reached 788k that is a cost not worth
# paying; worse, a model reading the same finding twice can take it for two
# SEPARATE problems.
#
# THE `cakisma_kontrol` OUTPUT WINS, not the scan. Because (a) it is what
# the model ITSELF asked, (b) its output is richer - how many objects, how
# many pairs, how many dropped by bbox, how long it took, (c) the scan's
# job is to catch what the model DID NOT ask. It need not repeat what was
# asked.
#
# ONLY `yaz=True` calls are recorded: `yaz=False` (the visual path) prints
# nothing, so suppressing its finding would really lose it.
_bildirilen_gecisler: set = set()


def bildirilen_gecisleri_sifirla() -> None:
    """Called at the START of every code block (see executor.calistir).

    The record is valid for a single block: an intersection written in a
    previous turn must not be suppressed in this turn's scan - the model
    must see it again.
    """
    _bildirilen_gecisler.clear()


def gecis_bildirildi_mi(ad_a: str, ad_b: str) -> bool:
    return tuple(sorted((ad_a, ad_b))) in _bildirilen_gecisler


def cakisma_kontrol(*nesneler, odak=None, sure_butcesi: float = 2.0,
                    yaz: bool = True) -> dict:
    """Measures whether the given objects pass THROUGH EACH OTHER.

    WHY IT EXISTS (measured): the model looked at images from three angles
    and said "they do not go into each other", the user saw the overlap;
    later the same model found the same overlap in 20 seconds with a trio it
    wrote BY HAND (common + distToShape + slice) — 2.7 mm3. The image could
    not have shown it: ~4 pixels/mm in a 900x640 frame, the overlapping
    strip ~4 pixels and BEHIND the sail.

    So this is a measurement not to be left to the model's reasoning — ready:

        cakisma_kontrol()                       # every relevant pair in the document
        cakisma_kontrol(a, b)                   # only these two
        cakisma_kontrol(a, b, c)                # all pairs of the three
        cakisma_kontrol(odak=a)                 # ONLY pairs involving a

    WHY ODAK EXISTS (measured): the panel asked about overlap for a single
    object in a close-up, but the code crossed it with ALL objects in the
    document — 44 objects, 946 pairs, the 2 s budget ran out and **431
    pairs were never measured**. So even the pair that was asked about
    could go unchecked. With `odak`, pairs are only `odak x others`: n-1
    instead of n(n-1)/2.

    CONSUMED OBJECTS ARE DROPPED (when called with no arguments or with
    `odak`): a cut base or a mirror source of course overlaps its result,
    and that is not a defect — see kesif.tuketilmis_mi. If you pass objects
    EXPLICITLY, no filtering happens: we measure what is asked, we do not
    censor it.

    Pairs are first filtered by BBOX (see _bbox_kesisiyor_mu), then all
    three measurements run (see _cift_olc). If the time budget runs out it
    STOPS and writes how many pairs were not checked — the same honesty
    rule as the verification layer.

    "Touching" IS NOT A DEFECT and is not reported as one: in real models a
    sail touches the mast and a rail touches the hull on purpose (so as not
    to go back to the false alarm repeated 31 times). What is a defect is
    PASSING THROUGH.
    """
    import time

    from . import kesif as _kesif

    adaylar = [n for n in nesneler if n is not None]
    elenen_tuketilmis = 0
    if not adaylar:
        doc = App.ActiveDocument
        bulunan = _kesif.ilgili_nesneler(doc) if doc is not None else []
        # Thin sketches/2D scaffolding are noise for this question:
        # intersection curves show up everywhere and none is a defect.
        bulunan = [o for o in bulunan
                   if _mesh_al(o) is not None
                   or (_sekil_al(o) is not None and _sekil_al(o).Faces)]
        # Objects that are someone else's raw material go out. The focus
        # object ITSELF is never dropped: the user asked about it, they get
        # an answer.
        adaylar = [o for o in bulunan
                   if (odak is not None and o is odak)
                   or not _kesif.tuketilmis_mi(o)]
        elenen_tuketilmis = len(bulunan) - len(adaylar)
    if odak is not None and not any(o is odak for o in adaylar):
        adaylar = [odak] + adaylar

    if len(adaylar) < 2:
        satir = ("cakisma_kontrol: needs at least two objects "
                 "(could not find two measurable parts in the document)")
        if yaz:
            print(satir)
        return {"ciftler": [], "gecisler": [], "bakilan_cift": 0,
                "toplam_cift": 0, "bakilmayan": 0, "sure_sn": 0.0,
                "satir": satir}

    t0 = time.time()
    ciftler: list[dict] = []
    gecisler: list[dict] = []
    degenler = 0
    elenen = 0
    bakilmayan = 0
    toplam = 0

    # With ODAK the pair count is n-1, not n(n-1)/2: pairs that do not
    # involve the asked object do not eat the budget.
    if odak is not None:
        ham = [(odak, o) for o in adaylar if o is not odak]
    else:
        ham = [(adaylar[i], adaylar[j])
               for i in range(len(adaylar))
               for j in range(i + 1, len(adaylar))]

    for a, b in ham:
        toplam += 1
        if time.time() - t0 > sure_butcesi:
            bakilmayan += 1
            continue
        if not _bbox_kesisiyor_mu(a, b):
            elenen += 1
            continue
        d = _cift_olc(a, b)
        ciftler.append(d)
        if d.get("gecis"):
            gecisler.append(d)
        elif d.get("hukum") == "touching":
            degenler += 1

    sonuc = {"ciftler": ciftler, "gecisler": gecisler,
             "bakilan_cift": len(ciftler), "toplam_cift": toplam,
             "bakilmayan": bakilmayan, "sure_sn": time.time() - t0}

    bas = f"check_overlap — "
    if odak is not None:
        bas += f"focus {getattr(odak, 'Name', '?')}, "
    bas += (f"{len(adaylar)} objects, {toplam} pairs "
            f"({elenen} pairs dropped by bbox)")
    if elenen_tuketilmis:
        # HONESTY: we have to say what we did not measure, otherwise a
        # "clean" report gives false confidence.
        bas += (f"; {elenen_tuketilmis} objects left out "
                f"(someone else's cut base/mirror source)")
    satirlar = [bas + f", {sonuc['sure_sn']:.2f} s"]
    for d in gecisler:
        satirlar.append("  " + d["satir"])
    if not gecisler:
        satirlar.append("  NO INTERSECTING PAIRS.")
    if degenler:
        satirlar.append(f"  touching (0 mm) pairs: {degenler} — not a defect, "
                        f"may be intentional contact")
    if bakilmayan:
        satirlar.append(f"  NOT RUN: {bakilmayan} pairs (time limit "
                        f"{sure_butcesi:g} s exceeded)")
    sonuc["satir"] = "\n".join(satirlar)
    if yaz:
        print(sonuc["satir"])
        # These pairs are now in the model's PROMPT; the verification scan
        # must not write them again.
        for d in gecisler:
            _bildirilen_gecisler.add(tuple(sorted((d["a"], d["b"]))))
    return sonuc


# --------------------------------------------------------------------------
# 7. HEALTH — "is this shape really sound"
# --------------------------------------------------------------------------
#
# WHY IT EXISTS (COUNTED in the logs):
#   isValid              156 times / 9 files
#   isSolid              125 times / 4 files
#   hasSelfIntersections  96 times / 4 files
#   len(Shape.Solids)     86 times / 7 files
#   hasNonManifolds       48 times / 3 files
# The model writes this BY HAND in every session, and in two DIFFERENT idioms:
#   solid -> sh.isValid() and len(sh.Solids) == 1 and sh.isClosed()
#   mesh  -> m.isSolid() and not m.hasNonManifolds() and
#            not m.hasSelfIntersections()
# So it also has to choose which test applies to which kind of object. This
# function takes over that choice.
#
# REJECTED CANDIDATES (NO EVIDENCE in the logs, so not written):
#   MatrixOfInertia / inertia tensor ...  0 times
#   deviation map (Inspection) .........  0 times
#   removeSplitter / Part::Refine ......  0 times (mentioned in the model's
#                                         words, never called in its code)

def _saglik_kati(s) -> tuple:
    """(defects, info) for a Part shape."""
    kusur: list[str] = []
    bilgi: list[str] = []

    try:
        if not s.isValid():
            kusur.append("isValid=False — does not pass OCC validation")
    except Exception:
        pass

    # A SHAPE WITHOUT FACES IS NOT A CANDIDATE FOR BEING A SOLID. Measured:
    # the `saglik()` document scan wrote `DEFECT Origin001: NO SOLID`; that
    # object was a datum POINT (App::Point, Shape=Vertex). Applying solid
    # tests to a point/edge/wire is a category error — and filling the
    # defect report with noise is the shortest way to devalue real defects.
    # The survey side now drops this type; this is the second layer: the
    # wrong defect must not be written even if the object is passed by hand.
    try:
        yuz_sayisi = len(s.Faces)
    except Exception:                                            # noqa: BLE001
        yuz_sayisi = None
    if yuz_sayisi == 0:
        bilgi.append("no faces (point/edge/wire) — solid tests not applied")
        return kusur, bilgi

    kati = None
    try:
        kati = len(s.Solids)
    except Exception:
        pass
    if kati == 0:
        kusur.append("NO SOLID (surface/shell only) — volume and printing meaningless")
    elif kati and kati > 1:
        # NOT a defect: a compound shape can be intentional. But the logs
        # show the model looking for exactly this, so it is mentioned.
        bilgi.append(f"{kati} separate solids — may not be fused")

    if kati:
        try:
            if not s.isClosed():
                kusur.append("not closed — open shell")
        except Exception:
            pass

    try:
        h = float(s.Volume)
        if kati and h <= 0:
            kusur.append(f"volume {_sayi(h)} mm3 — inside-out solid")
        else:
            bilgi.append(f"volume {_sayi(h)} mm3")
    except Exception:
        pass

    try:
        bilgi.append(f"{len(s.Faces)} faces")
    except Exception:
        pass
    return kusur, bilgi


# (name, value counted as a defect, message) — each is called guarded,
# because not every FreeCAD version has all of these methods.
_MESH_TESTLERI = (
    ("isSolid", False, "NOT A CLOSED SOLID — has holes/open edges; "
                       "volume and printing unreliable"),
    ("hasNonManifolds", True, "has non-manifold edges"),
    ("hasSelfIntersections", True, "has self-intersecting surfaces"),
    ("hasInvalidPoints", True, "has invalid points"),
    ("hasDegeneratedFacets", True, "has zero-area (degenerate) triangles"),
)


def _saglik_mesh(m) -> tuple:
    """(defects, info) for a Mesh."""
    kusur: list[str] = []
    bilgi: list[str] = []
    for ad, kotu, mesaj in _MESH_TESTLERI:
        try:
            deger = bool(getattr(m, ad)())
        except Exception:
            continue
        if deger is kotu:
            kusur.append(mesaj)
    try:
        bilgi.append(f"{m.CountFacets} triangles")
    except Exception:
        pass
    try:
        bilgi.append(f"volume {_sayi(m.Volume)} mm3")
    except Exception:
        pass
    return kusur, bilgi


def saglik(*nesneler, yaz: bool = True) -> dict:
    """Is the shape/mesh SOUND — catches broken booleans and unprintable meshes.

        saglik()          # every relevant object in the document
        saglik(a, b)      # only these

    Solids and meshes go through DIFFERENT tests (see _saglik_kati /
    _saglik_mesh); this function chooses which applies.

    DEFECTS and INFO are separated — the project's rule. "3 separate solids"
    is not a defect, it is information; "no solid" is a defect. Nothing that
    comes out broken is rounded off: a test that cannot be measured is
    SKIPPED silently, never made up.
    """
    import time

    from . import kesif as _kesif

    adaylar = [n for n in nesneler if n is not None]
    if not adaylar:
        doc = App.ActiveDocument
        adaylar = _kesif.ilgili_nesneler(doc) if doc is not None else []

    if not adaylar:
        satir = "saglik: no objects to check"
        if yaz:
            print(satir)
        return {"nesneler": [], "kusurlu": [], "satir": satir}

    t0 = time.time()
    kayitlar: list[dict] = []
    for o in adaylar:
        ad = getattr(o, "Name", "?")
        m = _mesh_al(o)
        if m is not None:
            kusur, bilgi = _saglik_mesh(m)
            tur = "mesh"
        else:
            s = _sekil_al(o)
            if s is None:
                continue
            kusur, bilgi = _saglik_kati(s)
            tur = "solid"
        # We SAY it is raw material but we do not drop it: a broken cut base
        # is the broken result itself.
        try:
            hammadde = _kesif.tuketilmis_mi(o)
        except Exception:
            hammadde = False
        kayitlar.append({"ad": ad, "tur": tur, "kusurlar": kusur,
                         "bilgiler": bilgi, "hammadde": hammadde})

    kusurlu = [k for k in kayitlar if k["kusurlar"]]
    temiz = [k for k in kayitlar if not k["kusurlar"]]
    sure = time.time() - t0

    satirlar = [f"health — {len(kayitlar)} objects, {len(kusurlu)} with defects, "
                f"{sure:.2f} s"]
    for k in kusurlu:
        etiket = k["ad"] + (" (raw material)" if k["hammadde"] else "")
        for mesaj in k["kusurlar"]:
            satirlar.append(f"  DEFECT {etiket}: {mesaj}")
    if not kusurlu:
        satirlar.append("  NO DEFECTS.")
    # Info lines AFTER the defects and trimmed: so they are not noise.
    # "not applied" is included too: if an object was NOT CHECKED we must
    # say so, otherwise "0 with defects" reads as clean — this function's
    # version of the project's "do not make up what you could not measure"
    # rule.
    notlar = [f"  note {k['ad']}: {b}"
              for k in kayitlar for b in k["bilgiler"]
              if "may not be fused" in b or "not applied" in b]
    satirlar.extend(notlar)
    if temiz:
        adlar = ", ".join(k["ad"] for k in temiz[:8])
        if len(temiz) > 8:
            adlar += f", +{len(temiz) - 8}"
        satirlar.append(f"  clean: {adlar}")

    sonuc = {"nesneler": kayitlar, "kusurlu": kusurlu, "sure_sn": sure,
             "satir": "\n".join(satirlar)}
    if yaz:
        print(sonuc["satir"])
    return sonuc


# --------------------------------------------------------------------------
# 8. SYMMETRY — "is the left half the same as the right half"
# --------------------------------------------------------------------------
#
# WHY IT EXISTS (COUNTED in the logs): "symmetry" appears 38 times in 5
# separate logs and the model sets it up BY HAND every time — taking the
# middle axis from the bbox and counting points in bands. Once it found a
# REAL defect that way: "in the Y=111-143 band there is only positive X,
# no point on the negative side — the missing piece is the left half of
# the horizontal tail wing." A defect that could slip past in a frame at
# 4 pixels/mm.
#
# THE WEAKNESS OF THE HAND-WRITTEN VERSION: band counting only asks "are
# there any points"; it shows a half that is shifted but PRESENT as CLEAN.
# Here it is mirrored and the REAL deviation is measured.

_EKSEN_NO = {"x": 0, "y": 1, "z": 2}


def _eksen_adi(eksen) -> str:
    ad = str(eksen).lower().strip()
    if ad not in _EKSEN_NO:
        raise ValueError("axis must be 'x', 'y' or 'z' (given: %r)" % (eksen,))
    return ad


def _ayna_taban_normal(eksen: str, merkez: float):
    i = _EKSEN_NO[eksen]
    taban = App.Vector(*[merkez if k == i else 0.0 for k in range(3)])
    normal = App.Vector(*[1.0 if k == i else 0.0 for k in range(3)])
    return taban, normal


def _simetri_kati(s, eksen: str, merkez: float):
    """Symmetry on a solid: mirror it, take the TWO-WAY difference, measure its volume.

    A one-way difference (A - A') is not enough — it only sees excess, not
    what is MISSING. The symmetric difference is two-sided.
    """
    taban, normal = _ayna_taban_normal(eksen, merkez)
    try:
        ayna = s.mirror(taban, normal)
    except Exception:
        return None
    fark_h = 0.0
    kutular = []
    for a, b in ((s, ayna), (ayna, s)):
        try:
            f = a.cut(b)
        except Exception:
            return None
        try:
            h = abs(float(f.Volume))
        except Exception:
            h = 0.0
        if h > _HACIM_ESIGI:
            fark_h += h
            try:
                kutular.append(f.BoundBox)
            except Exception:
                pass
    try:
        toplam = abs(float(s.Volume))
    except Exception:
        toplam = 0.0
    if toplam <= 0:
        return None
    return {"yontem": "volume", "fark": fark_h, "toplam": toplam,
            "oran": fark_h / toplam, "kutular": kutular}


_SIMETRI_AZAMI_NOKTA = 20000


def _simetri_nokta(noktalar, eksen: str, merkez: float):
    """Symmetry on a point cloud: mirror it and measure each mirrored
    point's nearest distance to the ORIGINAL.

    Without scipy's cKDTree (120x faster than brute force per the module
    header's measurement) we DO NOT MEASURE and do not make it up -> None.
    """
    np = _np()
    if np is None or not noktalar:
        return None
    try:
        from scipy.spatial import cKDTree
    except Exception:
        return None

    P = np.array([[p.x, p.y, p.z] for p in noktalar], dtype=float)
    if len(P) > _SIMETRI_AZAMI_NOKTA:
        adim = int(len(P) / _SIMETRI_AZAMI_NOKTA) + 1
        P = P[::adim]
    Q = P.copy()
    i = _EKSEN_NO[eksen]
    Q[:, i] = 2.0 * merkez - Q[:, i]
    d, _bul = cKDTree(P).query(Q)
    en_kotu = int(np.argmax(d))
    return {"yontem": "points", "nokta_sayisi": int(len(P)),
            "azami": float(d.max()), "ortalama": float(d.mean()),
            "en_kotu_yer": tuple(float(v) for v in Q[en_kotu])}


def _simetri_hukum(olculen: dict, boy: float) -> tuple:
    """(verdict, explanation). Thresholds are RELATIVE — 0.1 mm is symmetric
    on a 200 mm part, not on a 2 mm part."""
    if olculen["yontem"] == "volume":
        oran = olculen["oran"]
        if oran < 0.001:
            return "symmetric", "difference volume %.3f%%" % (oran * 100)
        if oran < 0.01:
            return "nearly", "difference volume %.2f%%" % (oran * 100)
        return "ASYMMETRIC", "difference volume %.1f%%" % (oran * 100)
    azami = olculen["azami"]
    goreli = azami / boy if boy else 0.0
    if goreli < 0.001:
        return "symmetric", "max deviation %s mm" % _sayi(azami)
    if goreli < 0.01:
        return "nearly", "max deviation %s mm" % _sayi(azami)
    return "ASYMMETRIC", ("max deviation %s mm (%.1f%% of the size)"
                          % (_sayi(azami), goreli * 100))


def simetri(nesne=None, eksen=None, merkez=None, yaz: bool = True) -> dict:
    """Is the part SYMMETRIC about an axis — and if not, WHERE is it off.

        simetri()                       # single object, all three axes
        simetri(obj, "x")               # only x
        simetri(obj, "y", merkez=8.0)   # mirror plane by hand

    Without `eksen` ALL THREE are measured and the symmetric ones are named
    — that answers "which axis is this part symmetric about".
    Without `merkez` the mirror plane is the bbox middle (the same choice the
    model made by hand in the logs: X_C = (XMin + XMax) / 2).

    Measured by volume difference on solids and by point cloud on meshes.
    If the boolean fails (common on broken shapes) it FALLS BACK to the
    point cloud and SAYS so in the line. If neither can measure it gives no
    result — it does NOT say "symmetric".
    """
    nesne = _hedef(nesne)
    if nesne is None:
        satir = "simetri: object not found (pass the object or leave only one)"
        if yaz:
            print(satir)
        return {"satir": satir, "eksenler": {}}

    kutu = _kutu(nesne)
    if kutu is None:
        satir = "simetri: %s could not be measured (no shape)" % getattr(nesne, "Name", "?")
        if yaz:
            print(satir)
        return {"satir": satir, "eksenler": {}}

    eksenler = [_eksen_adi(eksen)] if eksen is not None else ["x", "y", "z"]
    ortalar = {"x": (kutu.XMin + kutu.XMax) / 2.0,
               "y": (kutu.YMin + kutu.YMax) / 2.0,
               "z": (kutu.ZMin + kutu.ZMax) / 2.0}
    boylar = {"x": kutu.XLength, "y": kutu.YLength, "z": kutu.ZLength}

    m = _mesh_al(nesne)
    s = None if m is not None else _sekil_al(nesne)
    noktalar = None
    if m is not None:
        try:
            noktalar = m.Topology[0]
        except Exception:
            noktalar = None

    sonuclar = {}
    for e in eksenler:
        orta = ortalar[e] if merkez is None else float(merkez)
        olculen = None
        if s is not None:
            olculen = _simetri_kati(s, e, orta)
            if olculen is None:
                try:
                    kose, _uc = s.tessellate(max(0.1, boylar[e] / 200.0))
                    olculen = _simetri_nokta(list(kose), e, orta)
                    if olculen:
                        olculen["yedek"] = True
                except Exception:
                    olculen = None
        elif noktalar:
            olculen = _simetri_nokta(noktalar, e, orta)
        if olculen is None:
            sonuclar[e] = {"hukum": "not measured", "merkez": orta}
            continue
        hukum, aciklama = _simetri_hukum(olculen, boylar[e])
        olculen.update({"hukum": hukum, "aciklama": aciklama, "merkez": orta})
        sonuclar[e] = olculen

    ad = getattr(nesne, "Name", "?")
    satirlar = ["symmetry — %s" % ad]
    for e in eksenler:
        r = sonuclar[e]
        if r["hukum"] == "not measured":
            satirlar.append("  %s: NOT MEASURED (plane %s) — boolean and point "
                            "cloud both failed"
                            % (e, _sayi(r["merkez"])))
            continue
        ek = " [fallback: point cloud]" if r.get("yedek") else ""
        satirlar.append("  %s (plane %s=%s): %s — %s%s"
                        % (e, e, _sayi(r["merkez"]), r["hukum"],
                           r["aciklama"], ek))
        if r["hukum"] == "ASYMMETRIC":
            # WHERE it is off is the information that actually helps.
            for b in r.get("kutular", [])[:2]:
                satirlar.append(
                    "      difference region: x %s..%s, y %s..%s, z %s..%s"
                    % (_sayi(b.XMin), _sayi(b.XMax), _sayi(b.YMin),
                       _sayi(b.YMax), _sayi(b.ZMin), _sayi(b.ZMax)))
            if "en_kotu_yer" in r:
                x, y, z = r["en_kotu_yer"]
                satirlar.append("      worst point: (%s, %s, %s)"
                                % (_sayi(x), _sayi(y), _sayi(z)))

    olculenler = [e for e in eksenler if sonuclar[e]["hukum"] != "not measured"]
    if len(olculenler) > 1:
        temiz = [e for e in olculenler if sonuclar[e]["hukum"] != "ASYMMETRIC"]
        if temiz:
            satirlar.append("  -> symmetric axis: %s" % ", ".join(temiz))
        else:
            satirlar.append("  -> not symmetric about any axis")

    sonuc = {"eksenler": sonuclar, "satir": "\n".join(satirlar)}
    if yaz:
        print(sonuc["satir"])
    return sonuc
