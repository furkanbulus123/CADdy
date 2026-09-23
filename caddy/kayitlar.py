"""Turns the log folder into a readable HISTORY LIST.

Why a separate module: the history button used to only open the folder —
which was exactly the user's complaint: "there's no starting from a log, I
can only see the log, I can't continue it in FreeCAD". To RESUME a chat we
first have to read the session id from the log header; keeping that reading
Qt-free makes it testable headless (layer rule: no Qt outside ui).

Resuming goes through `claude --resume <session>`. That is the path
transport already uses (when the process dies the next turn continues that
way); the only new thing is being able to take the id from an OLD log.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

_OTURUM = re.compile(r"^session\s*:\s*(\S+)", re.MULTILINE)
_MODEL = re.compile(r"^model\s*:\s*(.+?)\s*$", re.MULTILINE)
_BASLAMA = re.compile(r"^started\s*:\s*(\S+)", re.MULTILINE)
_BELGE = re.compile(r"^document\s*:\s*(.+?)\s*$", re.MULTILINE)
_DOSYA = re.compile(r"^file\s*:\s*(.+?)\s*$", re.MULTILINE)
_KULLANICI = re.compile(r"^--- USER\b.*$", re.MULTILINE)

# No need to read the whole file for the header; a chunk big enough to also
# catch the first message is enough. Measured: the largest log was 195 KB,
# reading all of it would slow the list down for nothing.
_ONBELLEK_BAYT = 4096


class Kayit:
    """Summary of a single log file."""

    def __init__(self, dosya: Path, oturum: str, model: str, baslama: str,
                 ilk_mesaj: str, boyut: int, tur: int,
                 belge: str = "", belge_yolu: str = "") -> None:
        self.dosya = dosya
        self.oturum = oturum
        self.model = model
        self.baslama = baslama
        self.ilk_mesaj = ilk_mesaj
        self.boyut = boyut
        self.tur = tur
        # CAREFUL: `dosya` is the LOG file, `belge_yolu` is the FreeCAD
        # document. Two different things; mixing up the names is the
        # easiest mistake to make here.
        self.belge = belge
        self.belge_yolu = belge_yolu

    @property
    def surdurulebilir(self) -> bool:
        """Without a session id `--resume` is impossible — the button stays disabled."""
        return bool(self.oturum) and self.oturum != "nosession"

    def etiket(self) -> str:
        tarih = self.baslama.replace("T", " ")[:16] or self.dosya.stem
        ozet = self.ilk_mesaj or "(no messages)"
        if len(ozet) > 60:
            ozet = ozet[:57] + "…"
        return "%s · %d turns · %s" % (tarih, self.tur, ozet)

    def __repr__(self) -> str:                                   # pragma: no cover
        return "<Kayit %s %s>" % (self.dosya.name, self.oturum[:8])


def _ilk_deger(desen, metin: str, yer_tutucu: str = "") -> str:
    """Returns the FIRST match in the header; a placeholder counts as empty.

    First match, because the header is at the top of the file: if a user
    message starts with "file : ...", we want the header, not that.
    """
    m = desen.search(metin)
    if not m:
        return ""
    d = m.group(1).strip()
    return "" if d == yer_tutucu else d


def _ilk_kullanici_mesaji(metin: str) -> str:
    """First line of the first USER block after the header."""
    m = _KULLANICI.search(metin)
    if not m:
        return ""
    for satir in metin[m.end():].splitlines():
        s = satir.strip()
        if s:
            return s
    return ""


def kok(kok_dizin: Path | None = None) -> Path:
    """Finds the log root — SAME rule as `sohbet_log` (including the test root)."""
    if kok_dizin is not None:
        return Path(kok_dizin)
    cevre = os.environ.get("CADDY_LOG_DIR", "").strip()
    if cevre:
        return Path(cevre)
    from . import config

    return config.eklenti_dizini() / "LOG"


def listele(kok_dizin: Path | None = None, azami: int = 60) -> list:
    """Summarises the logs, NEWEST FIRST.

    An unreadable file does not break the list, it is skipped: not being
    able to open the history at all because of one corrupt file would be
    the worst behaviour.
    """
    d = kok(kok_dizin)
    if not d.is_dir():
        return []
    dosyalar = sorted((p for p in d.glob("*.txt") if p.is_file()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    kayitlar = []
    for p in dosyalar[:azami]:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                bas = f.read(_ONBELLEK_BAYT)
            oturum = (_OTURUM.search(bas).group(1) if _OTURUM.search(bas)
                      else "")
            model = (_MODEL.search(bas).group(1) if _MODEL.search(bas) else "")
            baslama = (_BASLAMA.search(bas).group(1) if _BASLAMA.search(bas)
                       else "")
            belge = _ilk_deger(_BELGE, bas, "(unknown)")
            belge_yolu = _ilk_deger(_DOSYA, bas, "(unsaved)")
            with open(p, encoding="utf-8", errors="replace") as f:
                tam = f.read()
            kayitlar.append(Kayit(
                dosya=p, oturum=oturum, model=model, baslama=baslama,
                ilk_mesaj=_ilk_kullanici_mesaji(tam),
                boyut=p.stat().st_size,
                tur=len(_KULLANICI.findall(tam)),
                belge=belge, belge_yolu=belge_yolu,
            ))
        except Exception:                                        # noqa: BLE001
            continue
    return kayitlar


def son_mesajlar(dosya: Path, adet: int = 6) -> list:
    """Returns the last N (role, text) pairs to show in the panel.

    So the chat window is not EMPTY when resuming: a user returning to old
    work should see what was said. We do not redraw the whole log — code
    blocks, verification reports and backup lines are in that file; the
    goal here is a reminder, not a copy of the archive.
    """
    try:
        metin = open(dosya, encoding="utf-8", errors="replace").read()
    except Exception:                                            # noqa: BLE001
        return []
    bloklar = []
    desen = re.compile(r"^--- (USER|AI)\b.*?-*\s*$", re.MULTILINE)
    isaretler = list(desen.finditer(metin))
    for i, m in enumerate(isaretler):
        son = isaretler[i + 1].start() if i + 1 < len(isaretler) else len(metin)
        govde = metin[m.end():son].strip()
        # Code blocks and tool output are summarised away: this is reminder
        # text, not something to run again.
        govde = re.split(r"^```", govde, maxsplit=1, flags=re.MULTILINE)[0]
        govde = govde.strip()
        if govde:
            rol = "kullanici" if m.group(1) == "USER" else "ai"
            bloklar.append((rol, govde))
    return bloklar[-adet:]


def bugun() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# DOCUMENT MATCHING
#
# The problem in the user's words: "it resumes in the wrong place... ok it
# gets the right chat but it's not the model it left off at." The chat comes
# back with `--resume`, the DOCUMENT does not; the code runs in whatever
# document is open. If `doc.getObject("Chassis")` returns None it fails
# anyway and is harmless — the real danger is when names COLLIDE: two
# projects both having `Box`, `Body`, `Base` is not remote at all, and then
# the code silently changes the wrong model.
#
# THE IDENTITY IS THE FILE PATH. Measured (freecadcmd 1.1.3): a document
# opened as `ProbeAc`, saved, closed and reopened became `caddy_probe_ac` —
# the internal name is RE-derived from the FILE NAME, it is not stable
# across sessions. The name is only shown to humans; comparison is by path.
# Same measurement: opening an already open file with `openDocument` does
# NOT create a SECOND COPY, it returns the same object (`d2 is d`), and a
# missing file raises OSError. So both calls below are safe.
# ---------------------------------------------------------------------------

DURUM_BILINMIYOR = "bilinmiyor"
DURUM_ACIK = "acik"
DURUM_KAPALI = "kapali"
DURUM_KAYIP = "kayip"
DURUM_KAYDEDILMEMIS = "kaydedilmemis"


def _ayni_yol(a: str, b: str) -> bool:
    """On Windows, case and `..` differences must not separate the same file."""
    try:
        return (os.path.normcase(os.path.abspath(str(a)))
                == os.path.normcase(os.path.abspath(str(b))))
    except Exception:                                            # noqa: BLE001
        return False


def _acik_belgeyi_bul(yol: str):
    """Returns the OPEN document whose path matches, else None."""
    if not yol:
        return None
    try:
        import FreeCAD as App

        for doc in list(App.listDocuments().values()):
            if _ayni_yol(getattr(doc, "FileName", "") or "", yol):
                return doc
    except Exception:                                            # noqa: BLE001
        return None
    return None


def _ic_ad(belge: str) -> str:
    """Extracts the FreeCAD internal name from the `document` line.

    The header uses `Label (InternalName)` when the two differ, a single
    word when they are the same. The internal name is needed because BACKUP
    files are named with `doc.Name` (`executor._yedek_al`).
    """
    d = (belge or "").strip()
    if d.endswith(")") and "(" in d:
        return d[d.rindex("(") + 1:-1].strip()
    return d


def _son_yedek(belge: str) -> str:
    """Path of the NEWEST backup copy of this document; empty if none.

    A backup is NOT something to OPEN, only an information line.
    `_yedek_al` takes the copy BEFORE the first AI change — so its content
    is the state at the START of the work. Opening it as "your model is
    back" would show everything done as deleted; the very definition of a
    silent wrong answer.
    """
    ad = _ic_ad(belge)
    if not ad:
        return ""
    try:
        from . import config

        d = config.yedek_dizini()
        adaylar = sorted(Path(d).glob("%s_*.FCStd" % ad),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        return str(adaylar[0]) if adaylar else ""
    except Exception:                                            # noqa: BLE001
        return ""


def belge_durumu(kayit) -> dict:
    """What state the resumed chat's document is in right now — one of four branches.

    It makes NO decision, it only produces the state and a human sentence;
    opening is the UI's job (and the user is asked). That keeps this
    function testable without Qt.
    """
    yol = (getattr(kayit, "belge_yolu", "") or "").strip()
    ad = (getattr(kayit, "belge", "") or "").strip()
    sonuc = {"durum": DURUM_BILINMIYOR, "ad": ad, "yol": yol,
             "belge": None, "yedek": "", "mesaj": ""}

    if not yol:
        if not ad:
            # Old logs (no document line in the header). We do not make
            # things up: writing what we do not know as a warning would
            # devalue the real warnings too.
            return sonuc
        sonuc["durum"] = DURUM_KAYDEDILMEMIS
        sonuc["yedek"] = _son_yedek(ad)
        sonuc["mesaj"] = (
            "This chat worked on “%s”, but that document was never "
            "saved — there is no file to bring back. Code will run in the "
            "currently open document." % ad)
        if sonuc["yedek"]:
            sonuc["mesaj"] += ("\nA copy of the state at the START is kept: "
                               "%s (not the state at the end of the chat.)"
                               % sonuc["yedek"])
        return sonuc

    doc = _acik_belgeyi_bul(yol)
    if doc is not None:
        sonuc["durum"] = DURUM_ACIK
        sonuc["belge"] = doc
        sonuc["mesaj"] = "The chat's document (%s) is already open." % (
            ad or Path(yol).name)
        return sonuc

    if not Path(yol).is_file():
        sonuc["durum"] = DURUM_KAYIP
        sonuc["mesaj"] = (
            "This chat worked on this file, but it is not there anymore:\n%s\n"
            "It may have been moved or deleted. Code will run in the "
            "currently open document." % yol)
        return sonuc

    sonuc["durum"] = DURUM_KAPALI
    sonuc["mesaj"] = ("This chat worked on “%s”:\n%s"
                      % (ad or Path(yol).name, yol))
    return sonuc


def belgeyi_ac(yol: str):
    """Opens the document (returns the same object if already open) and activates it.

    Returns: (document, error_text). If the document is None the error text
    is filled — it is shown in the panel; swallowing it would leave the user
    not knowing whether it opened or not.
    """
    try:
        import FreeCAD as App

        doc = App.openDocument(str(yol))
    except Exception as e:                                       # noqa: BLE001
        return None, "Could not open the document: %s" % e
    try:
        App.setActiveDocument(doc.Name)
        App.ActiveDocument = doc
    except Exception:                                            # noqa: BLE001
        pass
    try:
        import FreeCADGui as Gui

        # In the GUI every document has its own tab; opening does NOT close
        # your open document, a tab is added next to it. We move the focus
        # there too so the user sees the result of what they clicked.
        Gui.ActiveDocument = Gui.getDocument(doc.Name)
    except Exception:                                            # noqa: BLE001
        # Headless runs (freecadcmd) and tests land here — the document
        # still opened, this is not an error.
        pass
    return doc, ""
