"""English names for the helpers bound into the model's namespace.

The implementations live in olcum.py / islem.py / kesif.py / executor.py
under their original names. These thin wrappers only rename the function
and its keyword arguments, so the model (and anyone reading its code) sees
an English API. The original names stay bound too, so older chats that
resume with them keep working.
"""

from __future__ import annotations

from . import islem, kesif, olcum

# English keyword -> original keyword. Positional arguments pass through.
_KW = {
    "obj": "nesne", "focus": "odak", "echo": "yaz", "time_budget": "sure_butcesi",
    "axis": "eksen", "center": "merkez", "element": "alt",
    "thickness": "kalinlik", "open_face": "acik_yuz", "max_facets": "azami_facet",
    "prop": "ozellik", "expr": "ifade", "text": "metin", "size": "boyut",
    "radius": "yaricap", "pitch": "hatve", "length": "boy", "internal": "ic_mi",
    "material": "malzeme", "infill": "doluluk", "count": "adet", "angle": "aci",
    "direction": "yon", "spacing": "aralik", "step": "sik",
}


def _sar(fn, ad: str):
    def sarmal(*a, **k):
        return fn(*a, **{_KW.get(x, x): v for x, v in k.items()})
    sarmal.__name__ = ad
    sarmal.__doc__ = fn.__doc__
    return sarmal


def bagla(ns: dict, baski_kontrol) -> None:
    """Binds the English names into the namespace `ns`."""
    eslesme = {
        "survey": kesif.kesif,
        "measure": olcum.olc,
        "section_diameter": olcum.kesit_capi,
        "wall_thickness": olcum.duvar_kalinligi,
        "distance": olcum.mesafe,
        "measure_element": olcum.olcu,
        "check_overlap": olcum.cakisma_kontrol,
        "health": olcum.saglik,
        "symmetry": olcum.simetri,
        "print_check": baski_kontrol,
        "repair_mesh": islem.mesh_onar,
        "make_solid": islem.kati_yap,
        "hollow": islem.icini_bosalt,
        "dimension_table": islem.olcu_tablosu,
        "bind": islem.bagla,
        "text3d": islem.yazi,
        "screw_thread": islem.vida_disi,
        "weight": islem.agirlik,
        "split_for_print": islem.baskiya_bol,
        "polar_array": islem.dizi_polar,
        "linear_array": islem.dizi_dogrusal,
        "place_on_bed": islem.tabana_otur,
        "join": islem.birlestir,
        "section_contour": islem.kesit_konturu,
    }
    for ad, fn in eslesme.items():
        ns[ad] = _sar(fn, ad)
