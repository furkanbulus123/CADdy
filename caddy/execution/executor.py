"""Runs the generated FreeCAD Python on the LIVE document.

The heart of the design. Three things are non-negotiable:

1. **One clean undo.** However many objects the code creates, Ctrl+Z must
   undo all of them in one step. `App.setActiveTransaction(name,
   persist=True)` + `closeActiveTransaction()` provide that. `persist=True`
   is required: in FreeCAD 1.1 a transaction opened OUTSIDE a Gui::Command
   stack closes automatically when the command stack empties — and since
   our code runs inside a signal callback, we land exactly in that case.

2. **Error = full rollback.** If an exception is raised the transaction is
   ABORTED; the document is never left with half of the code applied.

3. **The traceback must show the source line.** Unless we put the source
   into linecache by hand after `compile()`, the traceback says
   "File "<caddy:...>", line 12" and DOES NOT SHOW THE LINE; the model has
   to guess what to fix. That one-line record directly raises the success
   rate of automatic repair.

Note: aborting only rolls back the DOCUMENT. If the code wrote a file or
changed something global, that stays — the UI tells the user.
"""

from __future__ import annotations

import io
import linecache
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field

import FreeCAD as App

from .. import log
from . import dogrulama, islem, kesif, olcum

# Window (seconds) in which running the same code a second time gets
# QUESTIONED. The measured accidents were 2 seconds apart; a deliberate
# repeat usually comes minutes later. See CodeExecutor._tekrar_engeli.
TEKRAR_PENCERESI = 60.0

# Runs longer than this get a STAGE BREAKDOWN in the log.
#
# WHY. Measured: the first block of a session, creating a single Part::Box,
# took 17.1 s, while later blocks in the same session took 0.1-0.3 s. The
# log only had the TOTAL time, so where the 17 seconds went could not be
# worked out afterwards. The same path was measured stage by stage on
# another machine (FreeCAD 1.1.3, GUI, same code) and ALL of it came to
# 0.02 s — so the culprit is not something fixed in this code path but
# something specific to that moment (cold disk, virus scan, the first
# `import Draft` in the GUI).
#
# Instead of guessing, stages are measured so that next time it TELLS us
# itself. There is a threshold because a normal turn takes 0.1 s: writing a
# breakdown on every line would drown the log in noise, and the one thing
# to find would get lost in it.
YAVAS_ESIGI = 2.0


def isit() -> float:
    """Does `_hazirla`'s expensive imports AHEAD of time. Returns: seconds spent.

    Called when the panel opens (see ui/dock). Off the critical path: the
    user is reading the model's reply at that moment, so the time spent
    here does not show up as waiting.

    Measured (real GUI): `Draft` 0.19 s, the others 0.00 s. So the gain here
    is small — but there is NO other candidate in that part of `calistir`
    and the cost is near zero. If warming does not explain the 17.1 s, the
    stage breakdown (see YAVAS_ESIGI) will name the culprit.

    NEVER raises: a missing module must not block the work, and `_hazirla`
    catches each of them one by one anyway.
    """
    t0 = time.time()
    for ad in ("Part", "Sketcher", "Draft", "Mesh", "PartDesign"):
        try:
            __import__(ad)
        except Exception:                                        # noqa: BLE001
            pass
    gecen = time.time() - t0
    log.ayik(f"warm-up: {gecen:.2f} s")
    return gecen

# Last lines that carry NO information. OCC exceptions can arrive without a
# message and `str(e)` returns "No error" — measured in a log, the summary
# of the only error literally read "ERROR — No error". The model could only
# find the right diagnosis from its own prints.
_BOS_HATA = {"no error", "none", "unknown", "unknown error", ""}


def _hata_ozeti(iz: str) -> str:
    """ONE meaningful line from a traceback.

    The last line is normally "TypeName: message" and does the job. If the
    message is empty or "No error", that line says nothing; in that case we
    give the exception TYPE together with the last informative line of the
    traceback.
    """
    satirlar = [s.strip() for s in (iz or "").strip().splitlines() if s.strip()]
    if not satirlar:
        return "error"
    son = satirlar[-1]
    tip, _, mesaj = son.partition(":")
    if mesaj.strip().lower() not in _BOS_HATA:
        return son
    # Empty message: the type itself is still valuable (like Part.OCCError).
    # Add the last traceback line that points at the culprit.
    tip = (tip or son).strip() or "error"
    for s in reversed(satirlar[:-1]):
        if s.startswith("File ") or s.startswith("Traceback"):
            continue
        return f"{tip} (no message) — last line: {s}"
    return f"{tip} (no message)"


@dataclass
class CalismaSonucu:
    basarili: bool = False
    hata_izi: str = ""
    cikti: str = ""
    uyarilar: list[str] = field(default_factory=list)
    eklenen: list[str] = field(default_factory=list)
    sure_sn: float = 0.0
    islem_adi: str = ""

    # Deterministic geometry check. The visual check catches SEMANTIC
    # mistakes; this catches broken topology that looks normal. See
    # dogrulama.py.
    dogrulama: "dogrulama.Rapor | None" = None
    # Objects the code TOUCHED (added + changed). Different from added:
    # "pad.Length = 20" adds nothing but can break the model.
    dokunulan: list[str] = field(default_factory=list)
    # Path of the backup taken before the FIRST AI change in this document.
    # Only filled when a backup was actually taken — the panel shows it once.
    yedek: str = ""

    # The code NEVER RAN: the repeat guard stopped it (see
    # Executor._tekrar_engeli). It must be kept apart from an error — this
    # is not an error, it is a question; it must not go to the model as
    # "your code failed".
    engellendi: bool = False

    # Captured from FreeCAD's own console — the ORANGE (warning) and RED
    # (error) lines in the Report view.
    konsol_uyari: list[str] = field(default_factory=list)
    konsol_hata: list[str] = field(default_factory=list)

    # Stages WITHIN the run: {"exec": 0.02, "recompute": 0.01, ...}.
    # For diagnosis only; it does NOT go to the model (see modele_metin) —
    # the model cannot fix anything about it, it would be noise.
    asamalar: dict[str, float] = field(default_factory=dict)

    @property
    def ozet(self) -> str:
        if self.engellendi:
            return "BLOCKED — the same code just ran"
        if not self.basarili:
            return f"ERROR — {_hata_ozeti(self.hata_izi)}"
        p = []
        if self.eklenen:
            p.append(f"{len(self.eklenen)} object(s) added")
        n = len(self.uyarilar) + len(self.konsol_uyari) + len(self.konsol_hata)
        if n:
            p.append(f"{n} warning(s)")
        if self.dogrulama is not None and self.dogrulama.bulgular:
            p.append(f"{len(self.dogrulama.bulgular)} geometry finding(s)")
        p.append(f"{self.sure_sn:.1f} s")
        return " · ".join(p)

    def asama_metni(self, esik: float = YAVAS_ESIGI) -> str:
        """Stage breakdown — ONLY if the run took longer than the threshold.

        Returning empty is the normal case: a breakdown of a 0.1 second turn
        tells nobody anything, and writing it on every line drowns the log.
        A long turn happened once in this project and the cause was never
        found — if it happens again, the line will be here.
        """
        if self.sure_sn < esik or not self.asamalar:
            return ""
        p = [f"{ad} {sn:.2f} s"
             for ad, sn in sorted(self.asamalar.items(),
                                  key=lambda kv: -kv[1]) if sn >= 0.05]
        return " · ".join(p)

    def modele_metin(self) -> str:
        """Summary sent back to the model - including console lines."""
        p = [f"result: {'SUCCESS' if self.basarili else 'ERROR'} ({self.ozet})"]
        if self.eklenen:
            p.append("added objects: " + ", ".join(self.eklenen))
        for u in self.uyarilar:
            p.append("warning: " + u)
        for u in self.konsol_hata:
            p.append("FreeCAD ERROR: " + u)
        for u in self.konsol_uyari:
            p.append("FreeCAD warning: " + u)
        if self.dogrulama is not None:
            d = self.dogrulama.metin()
            if d:
                p.append(d)
        if self.cikti:
            p.append("output:\n" + self.cikti[:2000])
        if not self.basarili:
            p.append("traceback:\n" + self.hata_izi.strip()[-2000:])
        return "\n".join(p)


def _katinin_meshi(o):
    """What a SOLID object will look like in the slicer. None if not possible.

    0.1 mm deflection is the same as the export default; the point is to
    see exactly that file in advance. Adds NO object to the document.
    """
    try:
        import MeshPart

        sekil = getattr(o, "Shape", None)
        if sekil is None or not sekil.Faces:
            return None
        return MeshPart.meshFromShape(Shape=sekil, LinearDeflection=0.1,
                                      AngularDeflection=0.4)
    except Exception:                                            # noqa: BLE001
        return None


def _baski_kontrol_yap(nesne=None) -> bool:
    """Print-readiness check the model can call from its code.

    WHY IN THE NAMESPACE. Users ask "is it ready now", "is it ready to
    print" in almost every session, and the model used to answer from
    OPINION. FreeCAD provides the deterministic answer out of the box; the
    only missing piece was letting the model ask it in one line.

    The output goes via print, and print output now returns to the model
    automatically — so writing `baski_kontrol(cup)` means an answer in one
    turn.

    Without `nesne` it looks at ALL meshes in the document. Returns: are
    all of them ready.
    """
    nesneler = []
    if nesne is None:
        doc = App.ActiveDocument
        if doc is not None:
            nesneler = [o for o in doc.Objects
                        if dogrulama._mesh_al(o) is not None]
        if not nesneler:
            print("baski_kontrol: no mesh objects in the document. "
                  "For a solid, convert it to a mesh with "
                  "MeshPart.meshFromShape first (export recipe in CLAUDE.md).")
            return False
    else:
        nesneler = [nesne]

    hepsi = True
    for o in nesneler:
        m = dogrulama._mesh_al(o)
        if m is None:
            # SOLID object: this used to say "not a mesh, not checked" and
            # stop. MEASURED: the model called `baski_kontrol(result)` on the
            # result of a fusion and that line was the only answer it got —
            # yet what goes to the slicer is a mesh anyway, so the question
            # made sense. Printing questions CAN be answered for solids: make
            # the mesh the slicer will see and check that.
            m = _katinin_meshi(o)
            if m is None:
                print(f"{getattr(o, 'Name', o)}: neither mesh nor solid — "
                      f"could not be checked")
                hepsi = False
                continue
            print(f"{getattr(o, 'Name', o)}: solid — the mesh the slicer will "
                  f"see was generated and checked (0.1 mm deflection)")
        hazir, engeller, olcumler = dogrulama.baskiya_hazir_mesh(m)
        ad = getattr(o, "Name", "mesh")
        print(f"{ad}: print-ready = {'YES' if hazir else 'NO'}"
              f"  ({' '.join(olcumler)})")
        for tur, ayrinti in engeller:
            print(f"    - {tur}: {ayrinti}")
        hepsi = hepsi and hazir
    return hepsi


class _KonsolYakalayici:
    """Captures FreeCAD's console output — the orange lines in the Report view.

    The user's request: "let the AI see the warning and info messages too,
    the orange parts." Most of these lines DO NOT RAISE: a recompute fails
    silently, writes something to the console, the code looks "successful"
    and the model cannot see what went wrong.

    THREE PATHS WERE TRIED, two rejected (measured, not guessed):

      1. `App.Console.AddObserver(...)`  -> DOES NOT EXIST in FreeCAD 1.1.
         The Console module only has GetObservers/GetStatus/SetStatus and
         Print*; AddObserver was removed (AttributeError).
      2. `redirect_stdout` / `redirect_stderr` -> captures NOTHING.
         Console writes from the C++ side, it never touches Python streams.
      3. Reading the Report view widget -> WORKS, and it is what we really
         want: the very lines the user sees on screen.

    Monkey-patching (wrapping the Print* functions) also WORKS but is NOT
    ENOUGH: it only catches calls made from Python. Measured - when an empty
    Part::Cut was recomputed, the C++ warning NEVER went through the patch.
    So both are used: the Report view is the main source, the monkey-patch
    is the fallback that works without a GUI (in tests).

    Colour classification: in the Report view warnings are orange, errors
    red. The text has no prefix to tell them apart, so the foreground colour
    of the character format is checked. If the colour cannot be read the
    line counts as a "warning" - showing too much beats losing it.
    """

    SINIR = 40          # max lines kept per run
    UZUNLUK = 400       # max length of one line

    def __init__(self) -> None:
        self.uyarilar: list[str] = []
        self.hatalar: list[str] = []
        self._metin_alani = None
        self._blok_sayisi = 0
        self._asil = {}

    # -- setup / teardown --------------------------------------------------

    def bagla(self) -> None:
        self._report_view_bagla()
        self._patch_bagla()

    def coz(self) -> None:
        self._patch_coz()
        self._report_view_oku()

    # -- 1) Report view (main source, GUI only) ----------------------------

    def _report_view_bul(self):
        try:
            import FreeCADGui as Gui
            from PySide import QtWidgets
        except Exception:
            return None
        try:
            mw = Gui.getMainWindow()
            if mw is None:
                return None
            # The Report view's objectName can change between versions;
            # try the name first, then the dock title (also localized ones).
            for ad in ("Report view", "ReportView", "Report View"):
                w = mw.findChild(QtWidgets.QTextEdit, ad)
                if w is not None:
                    return w
            for dock in mw.findChildren(QtWidgets.QDockWidget):
                baslik = (dock.windowTitle() or "").lower()
                if "report" in baslik or "rapor" in baslik:
                    w = dock.findChild(QtWidgets.QTextEdit)
                    if w is not None:
                        return w
        except Exception:
            return None
        return None

    def _report_view_bagla(self) -> None:
        self._metin_alani = self._report_view_bul()
        if self._metin_alani is None:
            return
        try:
            self._blok_sayisi = self._metin_alani.document().blockCount()
        except Exception:
            self._metin_alani = None

    def _report_view_oku(self) -> None:
        if self._metin_alani is None:
            return
        try:
            belge = self._metin_alani.document()
            for i in range(self._blok_sayisi, belge.blockCount()):
                blok = belge.findBlockByNumber(i)
                if blok is None or not blok.isValid():
                    continue
                metin = (blok.text() or "").strip()
                if not metin:
                    continue
                if self._hata_rengi_mi(blok):
                    self._ekle(self.hatalar, metin)
                elif self._uyari_rengi_mi(blok):
                    self._ekle(self.uyarilar, metin)
                # Black/grey = normal message and log: noise, not taken.
        except Exception as e:
            log.uyari(f"could not read the Report view: {e}")
        finally:
            self._metin_alani = None

    @staticmethod
    def _renk(blok):
        try:
            it = blok.begin()
            if it.atEnd():
                return None
            return it.fragment().charFormat().foreground().color()
        except Exception:
            return None

    @classmethod
    def _hata_rengi_mi(cls, blok) -> bool:
        r = cls._renk(blok)
        if r is None:
            return False
        # Red: red dominant, green and blue low.
        return r.red() > 130 and r.green() < 90 and r.blue() < 90

    @classmethod
    def _uyari_rengi_mi(cls, blok) -> bool:
        r = cls._renk(blok)
        if r is None:
            # Colour unreadable: count it as a warning rather than lose it.
            return True
        # Orange/yellow: red high, green MEDIUM, blue low.
        return r.red() > 130 and 60 <= r.green() < 200 and r.blue() < 120

    # -- 2) Monkey-patch (fallback; the only path without a GUI) -----------

    def _patch_bagla(self) -> None:
        try:
            self._asil = {
                "PrintWarning": App.Console.PrintWarning,
                "PrintError": App.Console.PrintError,
            }

            def sar(liste, asil):
                def _f(*a, **k):
                    try:
                        metin = next((x for x in a if isinstance(x, str)), "")
                        self._ekle(liste, metin.strip())
                    except Exception:
                        pass          # capturing must never break the real work
                    return asil(*a, **k)
                return _f

            App.Console.PrintWarning = sar(self.uyarilar,
                                           self._asil["PrintWarning"])
            App.Console.PrintError = sar(self.hatalar,
                                         self._asil["PrintError"])
        except Exception as e:
            log.uyari(f"could not wrap the console: {e}")
            self._asil = {}

    def _patch_coz(self) -> None:
        for ad, fn in self._asil.items():
            try:
                setattr(App.Console, ad, fn)
            except Exception:
                pass
        self._asil = {}

    # -- shared ------------------------------------------------------------

    def _ekle(self, liste: list, metin: str) -> None:
        try:
            metin = (metin or "").strip()
            if not metin or len(liste) >= self.SINIR:
                return
            kisa = metin[:self.UZUNLUK]
            if kisa not in liste:      # the Report view and the patch may
                liste.append(kisa)     # deliver the same line twice
        except Exception:
            pass


class _NamespaceKorumasi:
    """Empties the persistent namespace when an object is DELETED from the document.

    WHY. The persistent namespace is a deliberate decision: the model tends
    to write `body = doc.addObject(...)` in turn 1 and say `body.Tip` in
    turn 2. The risk is documented too — a name pointing at a deleted C++
    object causes a HARD CRASH, not an exception.

    The guard was `namespace_temizle()`, but it was ONLY called on undos
    coming from the panel/AI. When the user pressed FreeCAD's OWN Ctrl+Z —
    the normal path — nothing was cleared. So in the most ordinary scenario
    we were unprotected.

    Why a WHOLESALE clear rather than per object: finding which name in the
    namespace points at the deleted object means looking at the values'
    `.Name` — and some of those values may already be stale; we would touch
    exactly what we are avoiding. The cost of a wholesale clear is only
    variable continuity, and the contract already says "re-resolve objects
    by name in every block".

    DEFERRED DURING OUR OWN RUN. While `exec` runs, the namespace is exec's
    globals; emptying it midway would turn every name into a NameError at
    once. So a flag is set and it is cleared when the run ends.
    """

    def __init__(self, sahip: "CodeExecutor") -> None:
        self._sahip = sahip
        self._acik = False

    # Name called by FreeCAD — cannot be changed. It MUST NOT RAISE: it runs
    # inside the notification chain.
    def slotDeletedObject(self, nesne):
        try:
            self._sahip.silme_bildir()
        except Exception:
            pass

    def bagla(self) -> None:
        if self._acik:
            return
        try:
            App.addDocumentObserver(self)
            self._acik = True
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not attach the namespace guard: {e}")

    def coz(self) -> None:
        if not self._acik:
            return
        try:
            App.removeDocumentObserver(self)
        except Exception:
            pass
        self._acik = False


class CodeExecutor:
    """The executor that lives for the duration of one chat session."""

    def __init__(self) -> None:
        self._ns: dict = {}
        self._sayac = 0
        self._oturum = "0"
        # Documents already backed up (doc.Name). ONCE per document.
        self._yedekli: set[str] = set()
        self._calisiyor = False
        self._silme_bekliyor = False
        # Repeat guard: code text -> last SUCCESSFUL run time, and the ones
        # the user confirmed by pressing again after a block.
        self._son_kosan: dict[str, float] = {}
        self._tekrar_onayli: set[str] = set()
        self._koruma = _NamespaceKorumasi(self)
        self._koruma.bagla()

    def oturumu_ayarla(self, oturum: str) -> None:
        self._oturum = (oturum or "0")[:8]

    def kapat(self) -> None:
        """When the panel closes. A leaked observer fires on every document event."""
        self._koruma.coz()

    def silme_bildir(self) -> None:
        """Comes from the observer: an object was deleted from the document."""
        if self._calisiyor:
            # Our own code is running; the namespace is exec's globals now.
            self._silme_bekliyor = True
            return
        if self._ns:
            self.namespace_temizle("object deleted")

    def namespace_temizle(self, sebep: str = "") -> None:
        """Called after undo/redo/delete.

        Reason: a name bound in a previous block as `body = doc.addObject(...)`
        points at a DELETED C++ object after the user presses Ctrl+Z.
        Touching it causes a HARD CRASH, not an exception. Cutting the
        binding is the cheapest defence; the system prompt also has the rule
        "re-resolve objects by name in every block".
        """
        self._ns.clear()
        log.ayik("namespace cleared" + (f" ({sebep})" if sebep else ""))

    # -- backup ------------------------------------------------------------

    def _yedek_al(self, doc) -> str:
        """Leaves a copy before the FIRST AI change in this document.

        The second safety layer. Over a long session the model can pile its
        own damage on top of itself (measured: a boolean chain built on the
        broken BRep of an imported STEP) and the Ctrl+Z stack may not reach
        back far enough.

        NEVER blocks the work: if the backup fails, it warns and carries on.
        The document does not need to be saved to be backed up.
        """
        try:
            ad = doc.Name
        except Exception:
            return ""
        if ad in self._yedekli:
            return ""
        # Count it as tried once: retrying a failing backup on every turn
        # would slow every turn down.
        self._yedekli.add(ad)

        try:
            from .. import config

            damga = time.strftime("%Y-%m-%d_%H%M%S")
            yol = config.yedek_dizini() / f"{ad}_{damga}.FCStd"
            doc.saveCopy(str(yol))
            log.bilgi(f"backup saved: {yol}")
            return str(yol)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"backup failed ({e}); continuing")
            return ""

    # -- repeat guard ------------------------------------------------------

    def _tekrar_engeli(self, kod: str) -> str:
        """Stops the same code ONCE if it runs a second time within a short window.

        WHY HERE AND NOT ON THE CARD. This guard used to live in the panel
        (code_card: "ask for confirmation on the second press") and it WAS
        NOT ENOUGH — measured in a log, WITH the confirmation dialog in place:

            16:05:24  "Just fix the 2 patch centres"  SUCCESS
            16:05:26  same code, verbatim            SUCCESS
            16:05:28  same code, verbatim            SUCCESS

        The mesh was patched again each time and the session ended there.
        The card's guard looks at its own `_sonuc` field; if a new card
        object is created or the result is written to the wrong card (dock:
        the `k.blok is blok` identity match), the guard is bypassed. Running
        code is CUMULATIVE: a second run does not "repeat", it ADDS ON TOP.
        So the guard must sit where the DAMAGE happens, not where the click
        happens — every path goes through here.

        The user's own words: "I ran it too many times by mistake, I pressed
        run again, put it back the way it was".

        THE CONFIRMATION MECHANISM IS REPEATING: the blocked code is marked,
        and if the user still wants to run it, it runs on the second press.
        No Qt here (layer rule), so we cannot ask a question — but "press it
        again" is as clear as a confirmation.

        Only SUCCESSFUL runs count: code that failed wrote nothing to the
        document, repeating it is harmless and must not block the automatic
        repair path.
        """
        anahtar = (kod or "").strip()
        if not anahtar:
            return ""

        zaman = self._son_kosan.get(anahtar)
        if zaman is None or (time.time() - zaman) > TEKRAR_PENCERESI:
            return ""
        if anahtar in self._tekrar_onayli:
            self._tekrar_onayli.discard(anahtar)
            return ""

        self._tekrar_onayli.add(anahtar)
        gecen = time.time() - zaman
        log.uyari(f"the same code ran {gecen:.0f} s ago, blocked")
        return (f"This exact code ran {gecen:.0f} seconds ago and was "
                f"blocked.\n\nRunning code is cumulative: running it again "
                f"does NOT redo the work, it adds another copy on top "
                f"(a second body, a second patch, a second hole).\n\n"
                f"If you really want to run it again, press Run once "
                f"more — it will run this time.")

    def _tekrar_kaydet(self, kod: str) -> None:
        anahtar = (kod or "").strip()
        if not anahtar:
            return
        self._son_kosan[anahtar] = time.time()
        # Do not grow unbounded: old entries are outside the window anyway.
        if len(self._son_kosan) > 40:
            eski = sorted(self._son_kosan.items(), key=lambda kv: kv[1])
            for k, _ in eski[:20]:
                self._son_kosan.pop(k, None)

    # -- main entry --------------------------------------------------------

    def calistir(self, kod: str, baslik: str = "") -> CalismaSonucu:
        doc = App.ActiveDocument
        if doc is None:
            return CalismaSonucu(
                hata_izi="No document is open. Create one with File > New first.",
                islem_adi="")

        self._sayac += 1
        ad = (baslik or "change").strip().replace("\n", " ")[:60]
        islem_adi = f"AI: {ad}"

        engel = self._tekrar_engeli(kod)
        if engel:
            return CalismaSonucu(hata_izi=engel, engellendi=True,
                                 islem_adi=islem_adi)
        dosya_adi = f"<caddy:{self._oturum}:tur{self._sayac}>"

        # A COMPILE ERROR must be caught without opening a transaction —
        # there is no point leaving an empty undo entry.
        try:
            kod_nesnesi = compile(kod, dosya_adi, "exec")
        except SyntaxError:
            return CalismaSonucu(hata_izi=traceback.format_exc(),
                                 islem_adi=islem_adi)

        # So the traceback can show the source line (see the module header)
        linecache.cache[dosya_adi] = (
            len(kod), None, kod.splitlines(True), dosya_adi)

        # Backup BEFORE the FIRST change. Before opening the transaction,
        # because the backup must be a copy of the document as it is NOW,
        # not of the code.
        #
        # The call site is guarded too: _yedek_al catches internally, but
        # that PROMISE should be structural, not something verified by eye.
        # A safety mechanism blocking the real work would be worse than what
        # it tries to prevent.
        try:
            yedek_yolu = self._yedek_al(doc)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"backup failed ({e}); continuing")
            yedek_yolu = ""

        onceki = {o.Name for o in doc.Objects}
        cikti, hata_akisi = io.StringIO(), io.StringIO()
        konsol = _KonsolYakalayici()
        izleyici = dogrulama.Izleyici()
        # The block's own `cakisma_kontrol` output and the verification
        # scan's FINDING lines wrote the same pair twice; the record starts
        # fresh in every block (see olcum._bildirilen_gecisler).
        olcum.bildirilen_gecisleri_sifirla()
        # Stage clock. Knowing the total time was not enough: where 17.1
        # seconds went could not be found in the log (see YAVAS_ESIGI).
        asamalar: dict[str, float] = {}
        t0 = _onceki_asama = time.time()

        def _asama(ad: str) -> None:
            nonlocal _onceki_asama
            simdi = time.time()
            asamalar[ad] = simdi - _onceki_asama
            _onceki_asama = simdi

        App.setActiveTransaction(islem_adi, True)
        _asama("open transaction")
        konsol.bagla()
        izleyici.bagla()
        _asama("attach observers")
        self._calisiyor = True
        self._silme_bekliyor = False
        try:
            with redirect_stdout(cikti), redirect_stderr(hata_akisi):
                # `_hazirla` is on a SEPARATE line, not in exec's argument:
                # the imports that can be expensive on the first turn are
                # there, and without their own stage they stayed invisible
                # inside `exec`.
                ns = self._hazirla(doc)
                _asama("prepare")
                exec(kod_nesnesi, ns)
                _asama("exec")
                doc.recompute()
                _asama("recompute")
            App.closeActiveTransaction(False)          # commit
            basarili, iz = True, ""
        except BaseException:
            App.closeActiveTransaction(True)           # abort -> one clean undo
            basarili, iz = False, traceback.format_exc()
        finally:
            # A leaked observer fires on every user action.
            izleyici.coz()
            konsol.coz()
            self._calisiyor = False
            # If the code failed, some stages above were never recorded; the
            # rest of the time goes here so the breakdown adds up to sure_sn.
            _asama("close")
            sure = time.time() - t0

        # If the code (or the abort) deleted an object, the namespace can no
        # longer be trusted. exec is finished, so emptying it now is harmless.
        if self._silme_bekliyor:
            self._silme_bekliyor = False
            self.namespace_temizle("deleted during run")

        sonuc = CalismaSonucu(
            basarili=basarili,
            hata_izi=iz,
            cikti=(cikti.getvalue() + hata_akisi.getvalue()).strip(),
            sure_sn=sure,
            islem_adi=islem_adi,
            yedek=yedek_yolu,
            asamalar=asamalar,
        )

        # Slow turn: the breakdown goes to the Report view too. sohbet_log
        # writes the log; they are separate channels and it must be in both,
        # because when users complain they look at the Report view first.
        dokum = sonuc.asama_metni()
        if dokum:
            log.uyari(f"slow run ({sure:.1f} s): {dokum}")

        # FreeCAD's OWN console (orange/red lines in the Report view). These
        # often DO NOT raise — a recompute fails silently, writes "Links go
        # out of the allowed scope" and the code looks "successful". The
        # model needs to see them.
        sonuc.konsol_uyari = konsol.uyarilar
        sonuc.konsol_hata = konsol.hatalar

        if basarili:
            # Only a successful run counts for the repeat guard: failing code
            # wrote nothing to the document.
            self._tekrar_kaydet(kod)
            sonuc.eklenen = [o.Name for o in doc.Objects if o.Name not in onceki]
            # Touched = what the observer saw + added. If the observer could
            # not attach (old version, odd install), at least the added
            # objects get checked — verification must not go fully silent.
            mevcut = {o.Name for o in doc.Objects}
            sonuc.dokunulan = sorted((izleyici.adlar | set(sonuc.eklenen))
                                     & mevcut)
            sonuc.uyarilar = self._yumusak_hatalar(doc, sonuc.eklenen, kod)
            try:
                sonuc.dogrulama = dogrulama.dogrula(doc, sonuc.dokunulan)
            except Exception as e:                       # noqa: BLE001
                # Verification runs on top of a successful job. Failing here
                # would turn a job that ended well into one that ended badly.
                log.uyari(f"verification did not run: {e}")
            log.bilgi(f"{islem_adi} — {sonuc.ozet}")
        else:
            log.hata(f"{islem_adi} failed, transaction rolled back")

        return sonuc

    # -- internal ----------------------------------------------------------

    def _hazirla(self, doc) -> dict:
        """Refreshes the persistent namespace on every run.

        Persistence is deliberate: the model tends to write `body = ...` in
        turn 1 and say `body.Tip` in turn 2. Against the stale-binding risk
        there is namespace_temizle() and a system-prompt rule.
        """
        import Part

        ns = self._ns
        ns.update({
            "__name__": "__caddy__",
            "App": App,
            "FreeCAD": App,
            "Part": Part,
            "doc": doc,
            "Vector": App.Vector,
            "Placement": App.Placement,
            "Rotation": App.Rotation,
        })

        # These may be missing in some installs or be expensive to load;
        # their absence must not block the run.
        for ad in ("Sketcher", "Draft", "Mesh", "PartDesign"):
            if ad in ns:
                continue
            try:
                ns[ad] = __import__(ad)
            except Exception:
                pass

        try:
            import FreeCADGui
            ns["Gui"] = ns["FreeCADGui"] = FreeCADGui
        except Exception:
            pass

        import math
        ns.setdefault("math", math)
        # Measurement helpers. The user's words: "it would be better if
        # caddy measured directly". A mesh has no faces/edges, so dimensions
        # must be computed; these reduce that to a single call. See olcum.py.
        ns["baski_kontrol"] = _baski_kontrol_yap
        ns["olc"] = olcum.olc
        ns["kesit_capi"] = olcum.kesit_capi
        ns["duvar_kalinligi"] = olcum.duvar_kalinligi
        ns["mesafe"] = olcum.mesafe
        ns["olcu"] = olcum.olcu
        # "Do they touch, does one pass through" — a question NOT to ask the
        # image. Measured: the model looked at 3 frames, said "no overlap"
        # and was wrong; the same model found the same overlap with a trio
        # it wrote by hand.
        ns["cakisma_kontrol"] = olcum.cakisma_kontrol
        # Two patterns the model wrote BY HAND in the logs. Counted:
        # isValid 156, isSolid 125, hasSelfIntersections 96, Solids 86
        # times; "symmetry" 38 times in 5 separate logs. Neither is new
        # geometry, both wrap FreeCAD's own calls.
        ns["saglik"] = olcum.saglik
        ns["simetri"] = olcum.simetri
        # FIRST step when working on existing work: measure everything.
        ns["kesif"] = kesif.kesif
        # FreeCAD's ready-made capabilities. They replace the model writing
        # geometry by hand; see the islem.py module header.
        for _ad in ("mesh_onar", "kati_yap", "icini_bosalt", "olcu_tablosu",
                    "bagla", "yazi", "vida_disi", "agirlik", "baskiya_bol",
                    "dizi_polar", "dizi_dogrusal", "tabana_otur",
                    "birlestir", "kesit_konturu"):
            ns[_ad] = getattr(islem, _ad)
        # English API — what the contract and CLAUDE.md teach. The names
        # above stay bound so resumed older chats keep working.
        from . import api_en
        api_en.bagla(ns, _baski_kontrol_yap)
        return ns

    def _yumusak_hatalar(self, doc, eklenen: list[str], kod: str) -> list[str]:
        """The code DID NOT FAIL but the result may still be broken.

        These do not count as errors (the transaction committed), but they
        go to the next turn as context — the model must see the garbage it
        produced.

        SHAPE checks are NOT here: they moved to dogrulama.py, which looks
        at a wider set (touched, not only added) and deeper (volume sign,
        closed shell). What remains here has nothing to do with shape:
        object state and policy. Reporting in both places would tell the
        model the same thing twice.
        """
        u: list[str] = []

        for ad in eklenen:
            o = doc.getObject(ad)
            if o is None:
                continue
            durum = " ".join(getattr(o, "State", []) or [])
            if "Invalid" in durum or "Error" in durum:
                u.append(f"{ad}: invalid state ({durum})")

        # Parametric policy violation: dead shape output. The whole point of
        # this addon is to leave geometry a human can edit later.
        if "Part::Feature" in kod or "Part.show(" in kod:
            u.append("dead shape (Part::Feature/Part.show) created — "
                     "a human cannot edit it parametrically")

        try:
            kalan = [o.Name for o in doc.Objects if o.MustExecute]
            if kalan:
                u.append(f"objects still not recomputed: {', '.join(kalan[:5])}")
        except Exception:
            pass

        return u
