"""Chat log - writes the session to disk after every message.

Location: <addon>/LOG/<date>_<session>.txt  (e.g. 2026-08-18_0c44b5ad.txt)

Why one SESSION per file: each chat lives in its own file, and pressing
"New chat" opens a new one. That makes a piece of work easy to find later.

Why it is written AFTER EVERY MESSAGE (unbuffered): if FreeCAD crashes or
the user closes the window, the conversation must not be lost. A few KB
appended per turn costs nothing.

RULE: no error here ever affects the panel. Disk full, path not writable,
file locked - all are swallowed and only land in the FreeCAD log. The chat
record is not more important than the chat itself.

THE HEADER IS WRITTEN LAZILY. `oturum_ac` used to open the file and print
the header right away; a session opened with no message written left a
298-byte empty file behind. MEASURED: 43 of 106 files under LOG/ were
exactly that. The header now waits for the FIRST REAL ENTRY — a session with
no conversation produces no file.

TEST ROOT. The root directory can be changed with the `CADDY_LOG_DIR`
environment variable. The reason was measured: tests were writing into the
real LOG/ folder (the small files contained test data such as "SilenKutu",
"patlayan", "birinci hata") and every suite run left ~10 files behind.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

from . import log

_GECERSIZ = re.compile(r"[^A-Za-z0-9_.-]")


def _acik_belge() -> tuple:
    """(label, file_path) — ('', '') if there is no document.

    The FreeCAD import is GUARDED: the log module must load without FreeCAD
    in tests and headless tools. This file's rule is unchanged — no error
    here ever affects the panel.
    """
    try:
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return "", ""
        ad = str(getattr(doc, "Name", "") or "")
        etiket = str(getattr(doc, "Label", "") or ad)
        # Both are written because both are needed: the LABEL is the name
        # shown to the user, the NAME is the backup file's name (`_yedek_al`
        # uses `doc.Name`). When they differ, picking one would leave
        # whoever looks for the other blind.
        return (etiket if etiket == ad else f"{etiket} ({ad})",
                str(getattr(doc, "FileName", "") or ""))
    except Exception:                                            # noqa: BLE001
        return "", ""


class SohbetGunlugu:
    def __init__(self, kok: Path | None = None) -> None:
        from . import config

        cevre = os.environ.get("CADDY_LOG_DIR", "").strip()
        self._kok = Path(kok) if kok else Path(
            cevre or (config.eklenti_dizini() / "LOG"))
        self._dosya: Path | None = None
        self._oturum = ""
        self._kapali = False        # once it fails we never try again
        self._model_yazildi = False
        # The document identity goes into the header too. The file path may
        # appear in the MIDDLE of a session: users mostly save at the end.
        # So every entry checks until a path is found, then never again.
        self._belge_yazildi = False
        # Header lines NOT YET WRITTEN. Empty list = no header to write
        # (either already written or continuing an existing file).
        self._baslik: list[str] = []

    # -- lifecycle ---------------------------------------------------------

    def dosyaya_devam(self, oturum: str, dosya: Path) -> None:
        """CONTINUES an existing log file (resuming from history).

        Why `oturum_ac` is not enough: the file name comes from TODAY's date.
        When resuming a chat started yesterday, `oturum_ac` would open a
        SECOND file with today's name and split one chat in two. Here the
        path comes from outside, the header is not rewritten, and a visible
        separator is added — so that when reading later, "FreeCAD was
        restarted here" is not lost.
        """
        self._oturum = oturum or "nosession"
        self._dosya = Path(dosya)
        self._baslik = []
        self._model_yazildi = True      # header already exists, leave it
        # The resumed log's header records the OLD document, and that is the
        # whole point: writing the currently open one over it would erase,
        # with our own hands, which model the chat was about.
        self._belge_yazildi = True
        zaman = datetime.datetime.now().isoformat(timespec="seconds")
        self._ekle("", "-" * 72,
                   f"RESUMED — chat continued from history  [{zaman}]",
                   "-" * 72)

    def oturum_ac(self, oturum: str, model: str = "") -> None:
        """One session = one file. Calling it again for the same session does nothing.

        The early return matters: the file name comes from today's date, but
        if the session id is the same we do NOT recompute the path. Otherwise
        a chat running past midnight would be split into a second file.

        DOES NOT TOUCH THE DISK. It only computes the path and PREPARES the
        header; `_ekle` writes it at the top of the file when the first real
        entry arrives. That is why an empty session leaves no file (see the
        module header).
        """
        oturum = oturum or "nosession"
        if self._dosya is not None and oturum == self._oturum:
            return

        self._oturum = oturum
        self._model_yazildi = bool(model)
        kisa = _GECERSIZ.sub("", oturum)[:8] or "nosession"
        gun = datetime.date.today().isoformat()
        self._dosya = self._kok / f"{gun}_{kisa}.txt"

        if self._dosya.exists():
            self._baslik = []        # continuing the same file, no repeated header
            return

        # EFFORT goes into the header too. It was forgotten when the model
        # was added, and right in the next session we could not answer "which
        # effort level did it run with" from the log — yet it decides 91-94%
        # of the latency (see config.EFORLAR).
        try:
            from . import config

            e = config.efor()
            efor_metni = next((x[2] for x in config.EFORLAR if x[0] == e),
                              e or "(default)")
        except Exception:                                        # noqa: BLE001
            efor_metni = "(unreadable)"

        self._baslik = [
            "=" * 72,
            "CADdy chat log",
            f"session : {self._oturum}",
            f"model   : {model or '(unknown)'}",
            f"effort  : {efor_metni}",
            "document: (unknown)",
            "file    : (unsaved)",
            f"started : {datetime.datetime.now().isoformat(timespec='seconds')}",
            "=" * 72,
        ]

    # -- entries -----------------------------------------------------------

    def kullanici(self, metin: str) -> None:
        self._blok("USER", metin)

    def otomatik(self, metin: str) -> None:
        """A turn the panel sent BY ITSELF (visual check, error repair).

        It has its own header because these used to be logged as "USER" too,
        and someone reading the log later (logs are the only source of
        quality analysis in this project) could not tell human messages from
        automatic turns.
        """
        self._blok("AUTO", metin)

    def ai(self, metin: str, model: str = "", sure_sn: float = 0.0,
           token: str = "") -> None:
        if model:
            self._basliga_model_yaz(model)
        ek = " · ".join(x for x in (model,
                                    f"{sure_sn:.1f} s" if sure_sn else "",
                                    token) if x)
        self._blok("AI" + (f"  ({ek})" if ek else ""), metin)

    def _basliga_model_yaz(self, model: str) -> None:
        """Replaces the header's '(unknown)' with the real model.

        WHY. The header is written when the session opens, but the model is
        only known once the first reply arrives; because of that gap every
        file in LOG/ started with `model : (unknown)`. Once we started
        comparing two models (same task, Sonnet then Opus) this became a real
        obstacle — you could not tell from the top of the file which model
        was used, you had to read every turn.

        Written once. If the user switches models mid-session the header
        shows the FIRST model; the turn lines already record each turn's own
        model, which is the right place for it.
        """
        if self._model_yazildi or self._kapali or self._dosya is None:
            return
        self._model_yazildi = True        # even on failure we do not retry
        self._baslik_satirini_degistir("model   : (unknown)",
                                       f"model   : {model}")

    def _baslik_satirini_degistir(self, eski: str, yeni: str) -> bool:
        """Replaces a single header line in place.

        Has to handle two cases because the header is written LAZILY: if it
        has not reached the disk yet it is fixed in the pending list,
        otherwise the file is read and rewritten. Leaving the distinction to
        callers was an invitation to make the same mistake in two places.
        """
        if self._kapali or self._dosya is None:
            return False
        if self._baslik:
            if eski not in self._baslik:
                return False
            self._baslik = [yeni if s == eski else s for s in self._baslik]
            return True
        try:
            metin = self._dosya.read_text(encoding="utf-8")
            if eski not in metin:
                return False
            self._dosya.write_text(metin.replace(eski, yeni, 1),
                                   encoding="utf-8")
            return True
        except Exception as e:                                   # noqa: BLE001
            log.ayik(f"could not update the log header: {e}")
            return False

    def _belgeyi_tazele(self) -> None:
        """Fills the header's document/file lines with the real values.

        WHY THIS EXISTS. When a chat was resumed from history the chat came
        back but the DOCUMENT did not: code runs in whatever document is
        open. If names collide (Box, Body, Base — not a remote chance) the
        wrong model changes silently. To warn about that, we first have to
        record WHICH document the chat was about; what is not recorded
        cannot be compared later.

        THE IDENTITY IS THE FILE PATH, NOT THE NAME. Measured (freecadcmd):
        a document opened as `ProbeAc`, saved, closed and reopened became
        `caddy_probe_ac` — the internal name is RE-derived from the file
        name. So `doc.Name` is not stable across sessions; comparison is by
        path, the name is only shown to humans.

        Cost: two attribute reads. The disk is only touched when a value
        CHANGES, i.e. at most twice in a typical session.
        """
        if self._belge_yazildi or self._kapali or self._dosya is None:
            return
        ad, yol = _acik_belge()
        if ad:
            self._baslik_satirini_degistir("document: (unknown)",
                                           f"document: {ad}")
        if yol:
            self._baslik_satirini_degistir("file    : (unsaved)",
                                           f"file    : {yol}")
            # Path found; no point looking again on every entry.
            self._belge_yazildi = True

    def kod(self, kod: str, baslik: str = "") -> None:
        self._blok(f"CODE{f'  ({baslik})' if baslik else ''}", kod)

    def calisma(self, sonuc) -> None:
        satir = [f"result: {'SUCCESS' if sonuc.basarili else 'ERROR'}",
                 f"summary: {sonuc.ozet}"]
        if getattr(sonuc, "yedek", ""):
            satir.append(f"backup: {sonuc.yedek}")
        # Only filled for SLOW turns (see executor.YAVAS_ESIGI). We once saw
        # a 17.1 second turn, and since the log only had the total time the
        # cause could not be found later; if it happens again the line will
        # be here.
        asama = getattr(sonuc, "asama_metni", None)
        if callable(asama):
            dokum = asama()
            if dokum:
                satir.append(f"stages: {dokum}")
        if sonuc.eklenen:
            satir.append(f"added objects: {', '.join(sonuc.eklenen)}")
        dokunulan = getattr(sonuc, "dokunulan", None)
        if dokunulan:
            satir.append(f"touched: {', '.join(dokunulan)}")
        for u in sonuc.uyarilar:
            satir.append(f"warning: {u}")
        # Deterministic geometry check. It MUST be logged: logs are the only
        # source of quality analysis in this project, and what we do not
        # record we cannot measure later.
        d = getattr(sonuc, "dogrulama", None)
        if d is not None:
            metin = d.metin()
            if metin:
                satir.append(metin)
        if sonuc.cikti:
            satir.append("output:\n" + sonuc.cikti)
        if getattr(sonuc, "engellendi", False):
            # The code DID NOT RUN. This must be distinguishable from an
            # error in the log: it must not count toward the "error rate" in
            # the next quality measurement.
            satir.append("reason:\n" + sonuc.hata_izi.strip())
        elif not sonuc.basarili:
            satir.append("traceback:\n" + sonuc.hata_izi.strip())
        self._blok("RUN", "\n".join(satir))

    def sistem(self, metin: str) -> None:
        self._blok("SYSTEM", metin)

    # -- internal ----------------------------------------------------------

    def _blok(self, baslik: str, govde: str) -> None:
        an = datetime.datetime.now().strftime("%H:%M:%S")
        self._belgeyi_tazele()
        self._ekle("", f"--- {baslik}  [{an}] " + "-" * max(0, 50 - len(baslik)),
                   (govde or "").rstrip())

    def _ekle(self, *satirlar: str) -> None:
        if self._kapali:
            return
        if self._dosya is None:
            self.oturum_ac(self._oturum or "nosession")
            if self._dosya is None:
                return
        # A pending header goes FIRST — this is the moment the file is born.
        hepsi = self._baslik + list(satirlar)
        self._baslik = []
        try:
            self._kok.mkdir(parents=True, exist_ok=True)
            with open(self._dosya, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(hepsi) + "\n")
        except Exception as e:
            # Go quiet once and never retry - printing an error on every
            # message would drown the user and get in the way of the work.
            self._kapali = True
            log.uyari(f"could not write the chat log ({e}); logging disabled")

    @property
    def dosya(self) -> Path | None:
        return self._dosya
