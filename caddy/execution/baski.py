"""Design-for-additive-manufacturing FACTS: overhangs, supports, orientation, walls.

Shared by three existing helpers instead of adding new ones (the user's
rule: "if it already exists, merge it"):

  print_check(obj, process="FDM")   -> the full report (analyse_and_print)
  wall_thickness(obj)               -> wall sampling over the whole body
  place_on_bed(obj, minimize_support=True) -> the least-support orientation

SOURCE. The method and the limit table come from earthtojake/text-to-cad
(skills/dfam-check, MIT): measure facts first, compare them with a CITED
process limit, report PASS / FAIL / REVIEW / NOT MEASURED, and give every
FAIL a location and a target number. The same discipline CADdy already took
from that repository for verification (MANTIK 17): a limit with no
measurement behind it is not a finding, it is "NOT MEASURED".

Everything works on a MESH. A solid is meshed exactly the way it would be
exported for the slicer (0.1 mm deflection) and nothing is added to the
document.

LAYER RULE: no Qt here.
"""

from __future__ import annotations

import math
import random
import time

import FreeCAD as App

# Conservative defaults per process. From text-to-cad's
# skills/dfam-check/references/process-limits.md (Hubs, Formlabs, HP MJF and
# EOS design guides; ISO/ASTM 52910 for the structure). A user's machine or
# material datasheet overrides these.
#   wall_s: min SUPPORTED wall, wall_u: min UNSUPPORTED wall (mm)
#   angle:  self-supporting angle from horizontal (deg); None = powder bed
#   hole, feature, bridge: limits we do NOT measure yet (reported as such)
LIMITS = {
    "FDM":   {"wall_s": 1.2, "wall_u": 1.6, "angle": 45, "hole": 2.0,
              "feature": 0.8, "bridge": 10},
    "SLA":   {"wall_s": 0.5, "wall_u": 1.0, "angle": 30, "hole": 0.5,
              "feature": 0.2, "bridge": 5},
    "SLS":   {"wall_s": 0.7, "wall_u": 0.7, "angle": None, "hole": 1.5,
              "feature": 0.8, "bridge": None},
    "MJF":   {"wall_s": 0.5, "wall_u": 0.5, "angle": None, "hole": 1.0,
              "feature": 0.5, "bridge": None},
    "METAL": {"wall_s": 0.4, "wall_u": 0.5, "angle": 45, "hole": 1.5,
              "feature": 0.4, "bridge": 2},
}
_ALIASES = {"FFF": "FDM", "PLA": "FDM", "RESIN": "SLA", "DLP": "SLA",
            "PBF": "METAL", "SLM": "METAL", "DMLS": "METAL", "PA12": "SLS"}

WALL_BUDGET_S = 1.5        # wall sampling time budget per object
WALL_RAYS = 400            # rays per object (split across bodies)

# The six axis-aligned "this side down" candidates (text-to-cad measures the
# same six). The vector is the part direction that ends up facing the bed.
_SIDES = [("-Z", (0, 0, -1)), ("+Z", (0, 0, 1)), ("-X", (-1, 0, 0)),
          ("+X", (1, 0, 0)), ("-Y", (0, -1, 0)), ("+Y", (0, 1, 0))]


def process_key(surec) -> str | None:
    k = str(surec or "FDM").strip().upper()
    k = _ALIASES.get(k, k)
    return k if k in LIMITS else None


def _sayi(x) -> str:
    try:
        v = float(x)
        if abs(v) >= 10000:
            return f"{v:.0f}"
        return f"{v:.3g}" if abs(v) < 100 else f"{v:.0f}"
    except Exception:
        return str(x)


def _nokta(p) -> str:
    return "(" + ", ".join(f"{c:.1f}" for c in p) + ")"


def mesh_of(nesne):
    """(mesh, generated_from_solid) or (None, False). Adds NO object."""
    try:
        m = nesne.Mesh
        if hasattr(m, "CountFacets"):
            return m, False
    except Exception:
        pass
    try:
        import MeshPart

        s = getattr(nesne, "Shape", None)
        if s is None or not s.Faces:
            return None, False
        return MeshPart.meshFromShape(Shape=s, LinearDeflection=0.1,
                                      AngularDeflection=0.4), True
    except Exception:
        return None, False


def _arrays(m):
    """numpy points, facets, unit normals, areas, centroids — or None."""
    try:
        import numpy as np
    except Exception:
        return None
    pts, fac = m.Topology
    if not fac:
        return None
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float)
    F = np.array(fac, dtype=int)
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    cr = np.cross(b - a, c - a)
    L = np.linalg.norm(cr, axis=1)
    ok = L > 1e-12
    N = np.zeros_like(cr)
    N[ok] = cr[ok] / L[ok][:, None]
    return {"np": np, "P": P, "F": F, "N": N, "A": 0.5 * L,
            "C": (a + b + c) / 3.0}


# --------------------------------------------------------------------------
# OVERHANGS AND SUPPORT
# --------------------------------------------------------------------------

def _overhang(d, up, angle: float) -> dict:
    """Overhang facts for one build direction `up` (unit tuple).

    A down-facing facet needs support when it is closer to horizontal than
    the self-supporting angle: -(n . up) > cos(angle). A ceiling (n = -up)
    gives 1, a 45 deg chamfer gives 0.707, a wall gives 0. Facets resting on
    the bed are excluded. Support volume is the prism from each facet down to
    the bed: an UPPER bound (a support may stop on the part below), so it is
    a cost signal, not a slicer figure.
    """
    np = d["np"]
    u = np.array(up, dtype=float)
    h_pts = d["P"] @ u
    taban = float(h_pts.min())
    yukseklik = float(h_pts.max()) - taban
    nu = d["N"] @ u
    h = d["C"] @ u - taban
    tol = max(1e-3, 1e-5 * yukseklik)
    on_bed = (h < tol) & (nu < -0.99)
    mask = (-nu > math.cos(math.radians(angle)) + 1e-9) & ~on_bed
    alan = float(d["A"][mask].sum())
    hacim = float((d["A"][mask] * -nu[mask] * h[mask]).sum())
    return {"mask": mask, "area": alan, "volume": hacim, "height": yukseklik}


def _regions(d, mask, azami: int = 5) -> list:
    """Connected overhang regions (facets sharing a vertex), largest first."""
    np = d["np"]
    idx = np.nonzero(mask)[0]
    if len(idx) == 0:
        return []
    ebeveyn = {}

    def bul(x):
        while ebeveyn.get(x, x) != x:
            ebeveyn[x] = ebeveyn.get(ebeveyn[x], ebeveyn[x])
            x = ebeveyn[x]
        return x

    sahip = {}
    for f in idx:
        for v in d["F"][f]:
            v = int(v)
            if v in sahip:
                ra, rb = bul(int(f)), bul(sahip[v])
                if ra != rb:
                    ebeveyn[ra] = rb
            else:
                sahip[v] = int(f)
    gruplar = {}
    for f in idx:
        gruplar.setdefault(bul(int(f)), []).append(int(f))
    out = []
    for fs in gruplar.values():
        a = d["A"][fs]
        tot = float(a.sum())
        if tot <= 0:
            continue
        c = (d["C"][fs] * a[:, None]).sum(axis=0) / tot
        out.append({"area": tot, "center": tuple(float(x) for x in c),
                    "facets": len(fs)})
    out.sort(key=lambda r: -r["area"])
    return out[:azami]


def orientations(m, angle: float = 45.0) -> list:
    """The six "side down" candidates with support area/volume and height.

    Sorted best first: least support area, then volume, then height. The
    first element with side "-Z" is the current orientation.
    """
    d = _arrays(m)
    if d is None:
        return []
    out = []
    for ad, down in _SIDES:
        up = tuple(-c for c in down)
        o = _overhang(d, up, angle)
        out.append({"side": ad, "down": down, "area": o["area"],
                    "volume": o["volume"], "height": o["height"]})
    return sorted(out, key=lambda r: (round(r["area"], 3),
                                      round(r["volume"], 1), r["height"]))


# --------------------------------------------------------------------------
# WALL THICKNESS OVER THE WHOLE BODY
# --------------------------------------------------------------------------

def walls(m, rays: int = WALL_RAYS, butce: float = WALL_BUDGET_S) -> dict:
    """Wall thickness sampled over every body of the mesh.

    METHOD. From a facet's centre, a ray goes INTO the material (against
    the outward normal); the first surface it meets is the other side of
    the wall. FreeCAD's own `foraminate` does the ray test. Facets are
    picked area-weighted with a fixed seed, so the same mesh gives the
    same numbers.

    PER BODY. The mesh is split into its separate components first and
    every ray only sees its own body: a ray crossing a fit clearance into
    a neighbour would otherwise record the GAP as a wall (text-to-cad hit
    the same trap and reports per body for this reason).

    `min` is a sampled minimum, not an exhaustive one; `p05` (the thinnest
    5 %) is the robust number to compare with a limit.
    """
    t0 = time.perf_counter()
    try:
        govdeler = m.getSeparateComponents() or [m]
    except Exception:
        govdeler = [m]
    govdeler = [g for g in govdeler if g.CountFacets >= 4]
    if not govdeler:
        return {"bodies": [], "partial": False}
    toplam_alan = sum(max(g.Area, 1e-9) for g in govdeler)
    sonuc = {"bodies": [], "partial": False}
    rnd = random.Random(1)
    for gi, g in enumerate(govdeler):
        d = _arrays(g)
        if d is None:
            continue
        np = d["np"]
        n = max(40, int(rays * max(g.Area, 1e-9) / toplam_alan))
        n = min(n, len(d["A"]))
        w = d["A"] / d["A"].sum()
        if n >= len(w):
            secim = list(range(len(w)))
        else:
            kum = np.cumsum(w)
            secim = sorted({int(np.searchsorted(kum, rnd.random()))
                            for _ in range(n)})
        bb = g.BoundBox
        eps = max(1e-4, 1e-6 * bb.DiagonalLength)
        olcum = []
        for f in secim:
            if time.perf_counter() - t0 > butce:
                sonuc["partial"] = True
                break
            nv = d["N"][f]
            if not nv.any():
                continue
            c = d["C"][f]
            yon = -nv
            bas = c + yon * eps
            try:
                vur = g.foraminate(tuple(bas), tuple(yon))
            except Exception:
                continue
            uz = [float((np.array(p) - bas) @ yon) for p in vur.values()]
            uz = [x for x in uz if x > 1e-6]
            if uz:
                olcum.append((min(uz) + eps, tuple(float(x) for x in c)))
        if not olcum:
            continue
        olcum.sort()
        deger = [x for x, _ in olcum]
        sonuc["bodies"].append({
            "index": gi, "samples": len(deger), "min": deger[0],
            "p05": deger[int(0.05 * (len(deger) - 1))],
            "median": deger[len(deger) // 2], "at": olcum[0][1],
            "bbox": (bb.XLength, bb.YLength, bb.ZLength)})
    sonuc["seconds"] = time.perf_counter() - t0
    return sonuc


# --------------------------------------------------------------------------
# THE REPORT print_check PRINTS
# --------------------------------------------------------------------------

def analyse_and_print(m, ad: str, surec="FDM") -> bool:
    """Prints the DfAM section of print_check. Returns False on a FAIL."""
    key = process_key(surec)
    if key is None:
        print(f"    print analysis: unknown process {surec!r}. "
              f"Known: {', '.join(LIMITS)}")
        return True
    lim = LIMITS[key]
    kaynak = f"{key} default limits (text-to-cad process table)"
    print(f"  print analysis for {key} — limits: {kaynak}; a machine or "
          f"material datasheet overrides them")
    basarisiz = False

    bb = m.BoundBox
    if bb.DiagonalLength < 1.0 or bb.DiagonalLength > 5000:
        print(f"    UNITS SUSPECT: bounding-box diagonal "
              f"{_sayi(bb.DiagonalLength)} mm — the source may be in metres "
              f"or inches. Confirm the units before comparing any limit; "
              f"the numbers below mean nothing until then.")

    d = _arrays(m)
    if d is None:
        print("    NOT MEASURED: overhangs and walls (numpy unavailable or "
              "empty mesh)")
        return True

    # 1. Walls
    w = walls(m)
    if not w["bodies"]:
        print("    walls: NOT MEASURED — no ray found a second surface")
    for b in w["bodies"]:
        etiket = (f"body {b['index'] + 1}" if len(w["bodies"]) > 1
                  else "wall")
        satir = (f"{etiket}: p05 {_sayi(b['p05'])} mm, min {_sayi(b['min'])}"
                 f" mm at {_nokta(b['at'])}, median {_sayi(b['median'])} mm "
                 f"({b['samples']} rays)")
        if b["p05"] < lim["wall_s"]:
            basarisiz = True
            print(f"    FAIL   {satir} — below the {lim['wall_s']} mm "
                  f"minimum wall")
            print(f"           -> thicken the wall near {_nokta(b['at'])} "
                  f"from {_sayi(b['p05'])} mm to >= {lim['wall_s']} mm")
        elif b["p05"] < lim["wall_u"]:
            print(f"    REVIEW {satir} — fine where supported, below the "
                  f"{lim['wall_u']} mm unsupported-wall limit")
        elif b["min"] < lim["wall_s"]:
            print(f"    REVIEW {satir} — one thin spot below "
                  f"{lim['wall_s']} mm; may be a sampling outlier at an edge")
        else:
            print(f"    PASS   {satir}")
    if w["partial"]:
        print(f"    (wall sampling stopped at the {WALL_BUDGET_S} s budget — "
              f"partial)")

    # 2. Overhangs, support, orientation
    if lim["angle"] is None:
        print(f"    overhangs: not applicable for {key} (the powder supports "
              f"the part). Trapped powder in closed cavities: NOT MEASURED "
              f"— add >= 2 escape holes per cavity.")
    else:
        aci = lim["angle"]
        o = _overhang(d, (0, 0, 1), aci)
        hacim = abs(m.Volume) if m.isSolid() else 0.0
        if o["area"] < 1e-6:
            print(f"    PASS   overhangs: nothing steeper than {aci} deg "
                  f"from horizontal needs support in this orientation")
        else:
            oran = (f", ~{o['volume'] / hacim * 100:.0f}% of the part "
                    f"volume" if hacim > 0 else "")
            print(f"    SUPPORT overhangs past {aci} deg: "
                  f"{_sayi(o['area'])} mm2 of down-facing surface, support "
                  f"volume <= {_sayi(o['volume'])} mm3{oran} (upper bound, "
                  f"a cost signal)")
            for r in _regions(d, o["mask"], 3):
                print(f"           region {_sayi(r['area'])} mm2 around "
                      f"{_nokta(r['center'])} -> chamfer it to >= {aci} deg, "
                      f"support it, or reorient")
        yon = orientations(m, aci)
        if yon:
            simdi = next(r for r in yon if r["side"] == "-Z")
            en = yon[0]
            if (en["side"] != "-Z" and simdi["area"] - en["area"] > 1.0
                    and en["area"] < 0.75 * simdi["area"]):
                print(f"    ORIENT {en['side']} side down needs "
                      f"{_sayi(en['area'])} mm2 of support instead of "
                      f"{_sayi(simdi['area'])} (height {_sayi(en['height'])}"
                      f" vs {_sayi(simdi['height'])} mm) -> "
                      f"place_on_bed(obj, minimize_support=True)")

    nm = [f"min hole {lim['hole']} mm", f"min feature {lim['feature']} mm"]
    if lim["bridge"]:
        nm.append(f"max bridge {lim['bridge']} mm")
    print(f"    NOT MEASURED: {', '.join(nm)} — check these by dimension, "
          f"not by eye")
    return not basarisiz
