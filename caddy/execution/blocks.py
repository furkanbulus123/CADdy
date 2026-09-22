"""Modelin yanitindan kod bloklarini ayiklar.

Sozlesme: ```freecad-python ... ```
Duz ```python de kabul edilir ama `guvenilir=False` isaretlenir; arayuz bunu
sari rozetle gosterir. Boylece model sozlesmeye uymadiginda sessizce degil,
gorunur bicimde tolere etmis oluruz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ``` ya da ~~~ ile acilan, bilgi dizesi olan bloklar.
# Kapanis ayni karakterden en az acilis kadar olmali (CommonMark).
_BLOK = re.compile(
    r"^(?P<cit>`{3,}|~{3,})[ \t]*(?P<bilgi>[^\n]*)\n"
    r"(?P<govde>.*?)"
    r"^(?P=cit)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

_KOD_ETIKETLERI = ("freecad-python", "freecad", "fcpython")
_YEDEK_ETIKETLER = ("python", "py")


@dataclass
class KodBloku:
    kod: str
    baslik: str = ""
    guvenilir: bool = True     # sozlesmeye uygun etiketle mi geldi

    @property
    def bos_mu(self) -> bool:
        return not self.kod.strip()


def _baslik_cikar(bilgi: str) -> str:
    """`title="..."` varsa onu, yoksa bos dondurur."""
    m = re.search(r'title\s*=\s*"([^"]*)"', bilgi)
    if m:
        return m.group(1).strip()
    m = re.search(r"title\s*=\s*'([^']*)'", bilgi)
    return m.group(1).strip() if m else ""


def ayikla(metin: str) -> tuple[str, list[KodBloku]]:
    """(kodsuz duz metin, bloklar) dondurur."""
    bloklar: list[KodBloku] = []
    parcalar: list[str] = []
    son = 0

    for m in _BLOK.finditer(metin or ""):
        bilgi = (m.group("bilgi") or "").strip()
        etiket = bilgi.split()[0].lower() if bilgi else ""
        govde = m.group("govde")

        if etiket in _KOD_ETIKETLERI:
            bloklar.append(KodBloku(govde, _baslik_cikar(bilgi), True))
        elif etiket in _YEDEK_ETIKETLER:
            bloklar.append(KodBloku(govde, _baslik_cikar(bilgi), False))
        else:
            continue  # baska dilde blok — duz metnin parcasi olarak kalsin

        parcalar.append(metin[son:m.start()])
        son = m.end()

    parcalar.append(metin[son:])
    duz = "".join(parcalar).strip()
    return duz, [b for b in bloklar if not b.bos_mu]
