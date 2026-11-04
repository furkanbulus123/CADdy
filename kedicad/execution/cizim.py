"""drawing() — a dimensioned engineering drawing with FreeCAD's TechDraw.

WHY. For a CNC shop, a sheet-metal supplier or a mould maker the STEP file
is not the whole handoff: they want a drawing with the overall dimensions,
the hole sizes and a title block. text-to-cad ships this as its
"Engineering Drawing" skill; in FreeCAD the machinery already exists
(TechDraw), it only needed one call.

MEASURED (freecadcmd 1.1, a 60x40x20 block with a 10 mm hole):
  * a Front/Top/Right projection group recomputes in 0.03 s headless;
  * makeExtentDim(view, [], 0/1) gives 60 / 20 (front), 60 / 40 (top),
    40 / 20 (right) — the raw values are model millimetres;
  * a "Diameter" DrawViewDimension on the circle edge of the top view
    gives 10.0;
  * HardHidden=True turns on hidden lines (front: 4 visible, 6 hidden);
  * writeDXFPage works headless; PDF/SVG need TechDrawGui, which only
    loads inside the FreeCAD GUI (that is where KediCAD runs).

What it does NOT do, and says so: tolerances beyond the general note,
GD&T, section views, thread callouts, surface finish.

LAYER RULE: no Qt here (TechDrawGui is imported only to export).
"""

from __future__ import annotations

import datetime
import math
import os

import FreeCAD as App

_SAYFALAR = {"A4": "A4_Landscape_ISO5457_minimal.svg",
             "A3": "A3_Landscape_ISO5457_minimal.svg"}
AZAMI_CAP_OLCUSU = 6


def _sayi(x) -> str:
    v = float(x)
    return f"{v:.0f}" if abs(v - round(v)) < 1e-6 else f"{v:.2f}".rstrip("0")


def _sablon(sayfa: str):
    ad = _SAYFALAR.get(str(sayfa).upper(), _SAYFALAR["A4"])
    kok = os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Templates")
    yedek = None
    for r, _d, dosyalar in os.walk(kok):
        if ad in dosyalar:
            return os.path.join(r, ad)
        for f in dosyalar:
            if yedek is None and f.startswith(ad[:12]) and f.endswith(".svg"):
                yedek = os.path.join(r, f)
    return yedek


def _olcek_metni(olcek: float) -> str:
    if olcek <= 0:
        return ""
    if olcek >= 1:
        return f"{_sayi(olcek)} : 1"
    return f"1 : {_sayi(1 / olcek)}"


def teknik_resim(nesne=None, yol: str = "", sayfa: str = "A4",
                 baslik: str = "", malzeme: str = "", yaz: bool = True):
    """Front/Top/Right views with hidden lines, overall dimensions, hole
    diameters and a filled title block, on an ISO A4/A3 sheet.

        drawing(part)                                  # page in the document
        drawing(part, path=r"C:\\out\\part.pdf", material="AlMg3")

    `path` exports: .pdf / .svg (FreeCAD GUI), .dxf (always). Returns the
    TechDraw page object, or None.
    """
    from . import olcum

    doc = App.ActiveDocument
    nesne = olcum._hedef(nesne)
    s = olcum._sekil_al(nesne) if nesne is not None else None
    if s is None or s.isNull() or not s.Faces:
        if yaz:
            print("drawing: needs a solid object (a mesh has no edges to "
                  "dimension — make_solid it first, or draw the source part)")
        return None
    try:
        import TechDraw
    except Exception as e:                                       # noqa: BLE001
        if yaz:
            print(f"drawing: TechDraw is not available ({e})")
        return None

    sablon = _sablon(sayfa)
    page = doc.addObject("TechDraw::DrawPage", f"{nesne.Name}_Drawing")
    page.Label = f"{nesne.Label} drawing"
    if sablon:
        tpl = doc.addObject("TechDraw::DrawSVGTemplate",
                            f"{nesne.Name}_Template")
        tpl.Template = sablon
        page.Template = tpl

    grp = doc.addObject("TechDraw::DrawProjGroup", f"{nesne.Name}_Views")
    page.addView(grp)
    grp.Source = [nesne]
    for t in ("Front", "Top", "Right"):
        grp.addProjection(t)
    grp.ScaleType = "Automatic"
    for v in grp.Views:
        v.HardHidden = True
    doc.recompute()

    views = {v.Type: v for v in grp.Views}
    olculer = []

    def boyut(view, yon, ne):
        try:
            d = TechDraw.makeExtentDim(view, [], yon)
            doc.recompute()
            olculer.append((ne, d.getRawValue(), d))
        except Exception as e:                                   # noqa: BLE001
            olculer.append((ne, None, str(e)))

    if "Front" in views:
        boyut(views["Front"], 0, "width (front)")
        boyut(views["Front"], 1, "height (front)")
    if "Top" in views:
        boyut(views["Top"], 1, "depth (top)")

    # Hole diameters: full circles in the top view, one dimension per size.
    delikler = {}
    ust = views.get("Top")
    if ust is not None:
        for i in range(len(ust.getVisibleEdges())):
            try:
                e = ust.getEdgeByIndex(i)
                if "Circle" not in type(e.Curve).__name__:
                    continue
                r = e.Curve.Radius
                if abs(e.Length - 2 * math.pi * r) > 1e-3 * max(r, 1):
                    continue                                  # an arc, not a hole
                delikler.setdefault(round(2 * r / ust.Scale, 3), []).append(i)
            except Exception:                                    # noqa: BLE001
                continue
        for cap in sorted(delikler)[:AZAMI_CAP_OLCUSU]:
            try:
                d = doc.addObject("TechDraw::DrawViewDimension",
                                  f"{nesne.Name}_Dia")
                d.Type = "Diameter"
                d.References2D = [(ust, f"Edge{delikler[cap][0]}")]
                page.addView(d)
                doc.recompute()
                olculer.append((f"hole x{len(delikler[cap])}",
                                d.getRawValue(), d))
            except Exception as e:                               # noqa: BLE001
                olculer.append((f"hole {cap}", None, str(e)))

    olcek = float(grp.Scale)
    if sablon:
        try:
            alan = dict(tpl.EditableTexts)
            yeni = {"title": baslik or nesne.Label,
                    "drawing_number": nesne.Name,
                    "date_of_issue": datetime.date.today().strftime("%d %b %Y"),
                    "scale": _olcek_metni(olcek),
                    "part_material": malzeme,
                    "creator": "", "approval_person": "",
                    "general_tolerances": "ISO 2768-m",
                    "document_type": "Component Drawing"}
            for k, v in yeni.items():
                if k in alan:
                    alan[k] = v
            tpl.EditableTexts = alan
        except Exception:                                        # noqa: BLE001
            pass
    doc.recompute()

    disa = ""
    if yol:
        disa = _disa_aktar(page, yol)

    if yaz:
        print(f"drawing: {page.Name} on {os.path.basename(sablon or 'no template')}"
              f", scale {_olcek_metni(olcek)}, views Front/Top/Right with "
              f"hidden lines")
        for ne, deger, _d in olculer:
            if deger is None:
                print(f"    {ne}: NOT PLACED ({_d})")
            else:
                print(f"    {ne}: {_sayi(deger)} mm")
        if not delikler:
            print("    holes: none seen as full circles in the top view")
        print("    title block: title, number, date, scale"
              + (", material" if malzeme else " (material left blank — "
                 "pass material=...)")
              + "; general tolerance ISO 2768-m")
        print("    NOT INCLUDED: tighter tolerances, GD&T, section views, "
              "thread callouts, surface finish — add them if the shop needs "
              "them")
        if disa:
            print(f"    {disa}")
    return page


def _disa_aktar(page, yol: str) -> str:
    uz = os.path.splitext(yol)[1].lower()
    try:
        if uz == ".dxf":
            import TechDraw

            TechDraw.writeDXFPage(page, yol)
        elif uz in (".pdf", ".svg"):
            try:
                import TechDrawGui
            except Exception:                                    # noqa: BLE001
                return (f"export: {uz} needs the FreeCAD GUI (not available "
                        f"here) — use a .dxf path, or export from the page")
            if uz == ".pdf":
                TechDrawGui.exportPageAsPdf(page, yol)
            else:
                TechDrawGui.exportPageAsSvg(page, yol)
        else:
            return f"export: unknown format {uz!r} — use .pdf, .svg or .dxf"
    except Exception as e:                                       # noqa: BLE001
        return f"export FAILED: {type(e).__name__}: {e}"
    if os.path.isfile(yol) and os.path.getsize(yol) > 0:
        return f"exported: {yol} ({os.path.getsize(yol)} bytes)"
    return f"export: {yol} was NOT written"
