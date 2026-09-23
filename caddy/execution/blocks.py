"""Extracts code blocks from the model's reply.

Contract: ```freecad-python ... ```
Plain ```python is accepted too, but marked `guvenilir=False`; the UI shows
it with a yellow badge. So when the model breaks the contract we tolerate it
visibly, not silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Blocks opened with ``` or ~~~ and carrying an info string.
# The closing fence must use the same character, at least as long (CommonMark).
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
    guvenilir: bool = True     # did it come with the contract's tag

    @property
    def bos_mu(self) -> bool:
        return not self.kod.strip()


def _baslik_cikar(bilgi: str) -> str:
    """Returns `title="..."` if present, otherwise an empty string."""
    m = re.search(r'title\s*=\s*"([^"]*)"', bilgi)
    if m:
        return m.group(1).strip()
    m = re.search(r"title\s*=\s*'([^']*)'", bilgi)
    return m.group(1).strip() if m else ""


def ayikla(metin: str) -> tuple[str, list[KodBloku]]:
    """Returns (plain text without code, blocks)."""
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
            continue  # block in another language — keep it as part of the text

        parcalar.append(metin[son:m.start()])
        son = m.end()

    parcalar.append(metin[son:])
    duz = "".join(parcalar).strip()
    return duz, [b for b in bloklar if not b.bos_mu]
