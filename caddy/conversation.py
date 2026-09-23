"""Turn orchestration — the brain between the panel and the transport/execution layers.

The UI knows NOTHING (imports no widgets); it only emits signals. That way
the chat logic can be tested independently of the UI.
"""

from __future__ import annotations

import re
import time

from PySide import QtCore

from . import config, gorunum, log
from .context import serializer
from .execution import blocks
from .execution.executor import CodeExecutor
from .sohbet_log import SohbetGunlugu
from .transport.transport import KaliciTransport, TurSonucu


# The marker the model uses to ask for a visual. The contract says "END
# your reply with this marker"; the two accepted spots are this: on its own
# line, or at the very end of the message. The marker appearing in the
# middle of the text does not trigger, otherwise a sentence like "I don't
# need to do a visual check" would take a picture.
# Both spellings are accepted in case it gets typed with Turkish characters.
# A trailing "3" means the model wants THREE ANGLES (a big change).
#
# WHY THE LINE END IS ACCEPTED TOO: measured — the model wrote
# "...baskiya hazir — GORSEL-KONTROL", the marker was not on its own line,
# so the host SILENTLY sent nothing and the model could not learn that.
# 1 in 5 requests was lost this way, and 41 seconds later the user had to
# type it.
#
# The "YAKIN <name>" suffix: zooms the camera in on those objects (see
# gorunum.yakala_yakin). The rationale was measured — when the whole model
# fits the frame, a square gives ~4 px/mm and fine work is invisible
# (MANTIK 39). The names are the FreeCAD INTERNAL names, comma-separated;
# no spaces allowed in the pattern, so the rest of the sentence is not
# mistaken for a name.
_VISUAL_MARKER = re.compile(
    r"(?:^[ \t]*|[ \t—:-][ \t]*)G[OÖ]RSEL-KONTROL(?:[ \t]+(3))?"
    r"(?:[ \t]+YAKIN[ \t]+([A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*))?[ \t]*$",
    re.MULTILINE | re.IGNORECASE)

# At most this many objects in a close-up. Beyond that it stops being
# "close": the camera pulls back to fit everything in the frame and we are
# left with a general view again.
_CLOSEUP_MAX = 3

# Does the marker APPEAR in the text but not match the pattern above? Then
# we don't stay silent: a single sentence is appended to the next automatic
# prompt. It costs no extra turn, it rides on the prompt that is already
# going out.
_VISUAL_KEYWORD = re.compile(r"G[OÖ]RSEL-KONTROL", re.IGNORECASE)
_VISUAL_WARNING = ("Note: your reply contained GORSEL-KONTROL but not at "
                   "the END, so no image was sent. If you really want to "
                   "look, end your reply with that marker alone.")

# At most this many visual-check turns in a row. The model can look at a
# picture and ask for another one; on the third we stop and hand the ball
# to the user.
_VISUAL_LIMIT = 2

# THE VISUAL SYSTEM IS OFF FOR NOW (user's decision, 2026-08-28).
#
# THE CODE WAS NOT DELETED, IT WAS DEACTIVATED — it can be fixed and
# switched back on later. To turn it on: set this to True and put the
# GORSEL-KONTROL clause back into transport.SISTEM_SOZLESMESI (both are
# needed; if the contract does not describe it, the model never writes
# the marker).
#
# WHY IT WAS TURNED OFF — an experiment was run (PLAN S9, same prompt
# three times):
#   A  with photo     6 blocks, 129 KB frame, 48.7k tokens -> good
#   B1 without photo  4 blocks,   0 KB,      37.2k tokens -> bad
#   B2 without photo  8 blocks,   0 KB,      50.6k tokens -> BEST
# The best and the worst run were in the SAME arm. So what separated
# quality was not the image but the STEP COUNT (4 -> bad, 6 -> good,
# 8 -> best), and the measured cost of the photo in this pair was +31%
# tokens, +44% time. The image's contribution is below measurement noise;
# not enough samples for a firm verdict, but the cost is certain and the
# benefit is not.
VISUAL_ENABLED = False

# The marker the model uses to undo its OWN change.
# The user's question: "can't the AI do the undoing too, why force it on
# the user?" It can — only what it undoes has to be checked.
_UNDO_MARKER = re.compile(r"^[ \t]*GER[İI]-AL[ \t]*$",
                          re.MULTILINE | re.IGNORECASE)

# At most this many automatic undos in a row. The model could undo and undo
# again; such a loop tears the user's work down turn by turn.
_UNDO_LIMIT = 2

# The prefix on operations opened by the executor. The ONLY thing that
# tells whether the top undo record was left by the AI or by the user.
_AI_PREFIX = "AI: "

# How many AUTOMATIC repair turns are requested when the code blows up.
# PLAN M4's budget. More than two turns into a long chain without the user
# knowing.
_REPAIR_LIMIT = 2


def _short_num(n: int) -> str:
    """12400 -> '12.4k'. The panel is cramped, raw numbers are unreadable."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class ConversationController(QtCore.QObject):
    # role: "user" | "ai" | "sistem"
    mesaj = QtCore.Signal(str, str)          # role, text
    akis_basladi = QtCore.Signal()           # open the live reply box
    akis_parcasi = QtCore.Signal(str)        # reply text, as it streams
    dusunce_parcasi = QtCore.Signal(str)     # the model's thinking text (if any)
    dusunce_olcusu = QtCore.Signal(int)      # estimated thinking tokens
    akis_bitti = QtCore.Signal()
    asama = QtCore.Signal(str)               # idle | thinking | writing
    oneri = QtCore.Signal(object)            # blocks.KodBloku
    calisma_sonucu = QtCore.Signal(object)   # executor.CalismaSonucu
    durum = QtCore.Signal(str)               # idle | running | dying
    bilgi_satiri = QtCore.Signal(str, str)   # text, tooltip

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.transport = KaliciTransport(self)
        self.executor = CodeExecutor()
        self.gunluk = SohbetGunlugu()

        # Tokens accumulated over the session — "how much did I spend in
        # this chat".
        self._tk_total = 0
        self._turn_count = 0
        self._streaming = False

        # Visual-check state. `_visual_pending`: the model asked for
        # GORSEL-KONTROL but the same reply also had code -> capture AFTER
        # the code has run.
        self._visual_pending = False
        self._visual_turns = 0
        # Did the model ask for THREE ANGLES this time ("GORSEL-KONTROL 3").
        self._visual_multi = False
        # "GORSEL-KONTROL YAKIN Name1,Name2" — objects to zoom the camera
        # in on.
        self._visual_closeup: list[str] = []
        # The marker appeared in the text but not at the end of the reply
        # -> a one-sentence note will be appended to the next AUTOMATIC
        # prompt.
        self._visual_warning = False
        # Objects ADDED by the last block that ran. The host grants the
        # three-frame allowance based on this (see _frame_count).
        self._last_added: list[str] = []
        self._undo_turns = 0
        self._repair_turns = 0
        self._last_error = ""

        self.transport.tur_bitti.connect(self._turn_done)
        self.transport.durum_degisti.connect(self.durum.emit)
        self.transport.metin_parcasi.connect(self._text_chunk)
        self.transport.dusunce_parcasi.connect(self.dusunce_parcasi.emit)
        self.transport.dusunce_olcusu.connect(self.dusunce_olcusu.emit)
        self.transport.asama.connect(self.asama.emit)
        self.transport.limit_bilgisi.connect(
            lambda text: self.mesaj.emit("sistem", text))

        self.gunluk.oturum_ac(self.transport.oturum)

    # -- public -----------------------------------------------------------

    def mesgul_mu(self) -> bool:
        return self.transport.mesgul_mu()

    def gonder(self, metin: str, gorsel: bytes | None = None,
               kullanici_mi: bool = True) -> None:
        metin = (metin or "").strip()
        if not metin:
            return
        if self.mesgul_mu():
            self.mesaj.emit("sistem", "The previous request is still running. "
                                      "Wait for it or press Cancel.")
            return

        # A REAL user message resets the visual-check counter; an
        # automatically sent visual turn does not reset it, otherwise the
        # limit would never be reached.
        if kullanici_mi:
            self._visual_turns = 0
            self._undo_turns = 0
            self._repair_turns = 0
            self._last_error = ""
            self._visual_warning = False
        elif self._visual_warning:
            # A dropped visual request does NOT stay silent. We open no
            # extra turn; it rides at the end of the automatic prompt that
            # is already going out.
            metin = metin + "\n\n" + _VISUAL_WARNING
            self._visual_warning = False

        if kullanici_mi:
            self.mesaj.emit("user", metin)
        self.gunluk.oturum_ac(self.transport.oturum)
        # A message the human typed and a turn the panel sent on its own
        # must be DISTINGUISHABLE in the log.
        (self.gunluk.kullanici if kullanici_mi else self.gunluk.otomatik)(metin)

        self.executor.oturumu_ayarla(self.transport.oturum)
        self._streaming = False
        self._t0 = time.time()
        try:
            context = serializer.belge_metni()
        except Exception as e:
            log.uyari(f"belge baglami alinamadi: {e}")
            context = "<document>okunamadi</document>"

        self.transport.tur_gonder(f"{context}\n\n<request>\n{metin}\n</request>",
                                  gorsel=gorsel)

    def iptal(self) -> None:
        self.transport.iptal()

    def yeni_sohbet(self) -> None:
        self.transport.yeni_oturum()
        self.executor.namespace_temizle()
        self._tk_total = 0
        self._turn_count = 0
        # New session = NEW FILE. The "1 session = 1 log" rule.
        self.gunluk.oturum_ac(self.transport.oturum)
        self.mesaj.emit("sistem", "New chat started — previous context forgotten.")
        self.bilgi_satiri.emit("", "")

    def sohbeti_surdur(self, oturum: str, dosya) -> None:
        """Returns to an old chat picked from the library.

        Two deliberate differences from `yeni_sohbet`, and both are
        intentional:
        - we do NOT clear the namespace; the user keeps working in the
          same FreeCAD document, wiping their variables helps nothing.
        - the log does NOT open a new file, it continues the old one (see
          `sohbet_log.dosyaya_devam`) — one chat, one file.

        The counters reset: the token total and the turn count count THIS
        session's turns; our counter does not know the inherited history,
        and pretending it does would produce a false number.
        """
        self.transport.oturumu_surdur(oturum)
        self._tk_total = 0
        self._turn_count = 0
        try:
            self.gunluk.dosyaya_devam(oturum, dosya)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"gunluge devam edilemedi: {e}")
        self.executor.oturumu_ayarla(oturum)
        self.bilgi_satiri.emit("", "")

    def blogu_calistir(self, blok: blocks.KodBloku) -> None:
        """When 'Run' is pressed in the panel."""
        self.gunluk.kod(blok.kod, blok.baslik)
        redo_vardi = self._redo_count()
        result = self.executor.calistir(blok.kod, blok.baslik)
        self.gunluk.calisma(result)
        # WORK HAPPENED IN BETWEEN: the visual counter counts the
        # "look - look again" chain, not "look - change - look again"
        # (see _send_visual). If code ran, there is something new to look
        # at.
        if not result.engellendi:
            self._visual_turns = 0
            self._last_added = list(getattr(result, "eklenen", None) or [])
        # Code that runs AFTER an undo burns the redo stack (measured, see
        # ileri_al). Don't let it vanish silently: the user thinks they can
        # get back to what they undid, and pressing the button finds an
        # empty stack.
        if redo_vardi and self._redo_count() == 0:
            self.mesaj.emit("sistem",
                            f"Redo history cleared ({redo_vardi} steps) "
                            "— a new change was made on top.")
            self.gunluk.sistem(f"REDO STACK CLEARED ({redo_vardi} steps)")
        self.calisma_sonucu.emit(result)

        try:
            import FreeCADGui as Gui
            Gui.updateGui()
        except Exception:
            pass

        # The repeat guard stopped it, so the code NEVER ran. That is not
        # an error, it is a question asked of the user; telling the model
        # "your code crashed" would send it pointlessly looking for another
        # way.
        if result.engellendi:
            return

        # The model wanted to SEE this code's RESULT. Capturing now: the
        # code ran, the 3D is current. updateGui() was called above so the
        # image contains the new geometry.
        if self._visual_pending:
            if result.basarili:
                # If there is output it RIDES ON the same turn — spending a
                # separate turn is pointless and the model should see the
                # two messages in order, together.
                self._send_visual(result.cikti)
                return
            # The code blew up, the operation was rolled back — there is
            # nothing new to show.
            self._visual_pending = False

        if not result.basarili:
            self._auto_repair(result)
        elif result.cikti:
            self._send_output(result)

    def _send_output(self, result) -> None:
        """The code SUCCEEDED and printed something: send it back to the model.

        WHY. A log review (2026-08-21, item 1) measured this: 8 blocks with
        print() ran, and NONE of their output ever reached the model. The
        executor was capturing the output, writing it to the log, showing
        it in the panel — just never sending it to the model. The "Send
        result to AI" button on the card only appeared when there was a
        WARNING, so there was NO way at all to forward a result that was
        pure output.

        The model's response to that is on record in the log, and this was
        its cost:

          * producing objects in the document to measure something (adding
            a Draft circle to learn a number, then reading its radius a
            turn LATER),
          * deliberately embedding the result in an exception to get it
            back automatically — its own words: "sonucu kasitli bir hataya
            gomup size otomatik olarak geri gelmesini saglayacagim". It
            worked, because the ERROR path was fed automatically and the
            SUCCESS path was not. The model found the one hole the host
            left open.

        Now the success path is fed too; both of those patterns are
        unnecessary. No loop risk: every turn starts with the user pressing
        Run, it never chains on its own.
        """
        if self.mesgul_mu():
            return
        self.gunluk.sistem("OUTPUT sent automatically "
                           f"({len(result.cikti)} chars)")
        self.sonucu_gonder(result, kullanici_mi=False)

    # -- auto-repair -------------------------------------------------------

    @staticmethod
    def _error_signature(result) -> str:
        """The last line of the traceback — the error's identity.

        Line numbers and paths can change; if what changes is not the TYPE
        and message of the error, the model keeps hitting the same wall.
        """
        lines = (result.hata_izi or "").strip().splitlines()
        return lines[-1].strip() if lines else ""

    def _auto_repair(self, result) -> None:
        """When the code blows up, the error goes to the model ON ITS OWN.

        WHY. It used to take the user pressing the "Send error to AI"
        button; without the press the model never knew its code had blown
        up. That is exactly the undo problem's (MANTIK 19) pattern: work
        the host could do on its own was being done by a human. The log
        shows the user pressed that button three times — the flow was the
        same every time, the only difference one click and the chance the
        user was looking elsewhere at that moment.

        TWO LIMITS. PLAN M4 said "a 2-attempt budget":

        1. At most _REPAIR_LIMIT automatic turns. Then we stop and hand the
           ball to the user — the button is still there, it can be sent by
           hand.
        2. If the SAME error comes twice, stop IMMEDIATELY. Filling the
           budget is pointless: the model is hitting the same wall and the
           third attempt hits the same spot. This is the real limit, and it
           kicks in earlier than the budget limit.
        """
        signature = self._error_signature(result)

        if signature and signature == self._last_error:
            self._last_error = ""
            self.mesaj.emit("sistem",
                            "The same error repeated; auto-repair "
                            "stopped. Please describe a different "
                            "approach.")
            self.gunluk.sistem("AUTO-REPAIR stopped: same error repeated")
            return

        if self._repair_turns >= _REPAIR_LIMIT:
            self.mesaj.emit("sistem",
                            f"{_REPAIR_LIMIT} auto-repair attempts "
                            "were not enough; stopped. You can continue "
                            "with “Send error to AI”.")
            self.gunluk.sistem("AUTO-REPAIR budget exhausted")
            return

        if self.mesgul_mu():
            return                     # keep the manual-send path open

        self._repair_turns += 1
        self._last_error = signature
        self.mesaj.emit("sistem",
                        f"Error sent to AI automatically "
                        f"({self._repair_turns}/{_REPAIR_LIMIT}).")
        self._send_error(result, kullanici_mi=False)

    # -- undo --------------------------------------------------------------

    def geri_al(self, ai_mi: bool = False) -> tuple[bool, str]:
        """Undoes the last AI change. Returns: (did_it, explanation).

        Both the panel button and the model's GERI-AL marker enter HERE,
        because the dangerous thing is the same in both: WHOSE work is on
        top of the stack.

        The old button called `doc.undo()` unconditionally and was labeled
        "Undo last AI change". If the user had done something by hand after
        the AI's code, the button undid THEIR work — the label was lying.
        Now the top record's prefix is checked.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "No document is open."
        names = list(getattr(doc, "UndoNames", ()) or ())
        if not names:
            return False, "Nothing to undo."

        top = names[0]
        if not top.startswith(_AI_PREFIX):
            return False, (
                f"The top of the undo stack is not an AI change — it is "
                f"“{top}”, your own edit. Stopped so it is not lost. "
                f"Use Ctrl+Z if you want to undo it yourself.")

        doc.undo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"geri alma sonrasi recompute: {e}")
        # A stale binding = HARD CRASH risk (see executor.namespace_temizle).
        self.executor.namespace_temizle()
        who = "AI" if ai_mi else "User"
        self.gunluk.sistem(f"UNDO ({who}): {top}")
        return True, top

    @staticmethod
    def _redo_count() -> int:
        """Steps in the redo stack. 0 if there is no document."""
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return 0
        return len(list(getattr(doc, "RedoNames", ()) or ()))

    def ileri_al(self) -> tuple[bool, str]:
        """RE-APPLIES the last undone change. Returns: (did_it, explanation).

        MEASURED (LOG/2026-08-24_3ad4cef1.txt, 12:09:33 -> 12:09:58): the
        user undid a result they had just called "yes, that's what I
        wanted" — three times in six seconds. Then they tried rerunning the
        old code block, got the same error twice ("no bunny or
        Karin_dolgusu" — because the undo had deleted the fill) and the
        session ended there. At that moment FreeCAD's redo stack still held
        THREE records; 25 minutes of work were lost for a missing button.

        UNLIKE GERI-AL, the user's own record can be redone too. The
        asymmetry is deliberate: undoing DELETES work (if the user's effort
        is on top of the stack it destroys it — hence the check there),
        redoing BRINGS BACK. There is nothing for a refusal to protect, so
        only what came back is reported.

        MEASURED — exactly when the redo stack is cleared (FreeCAD 1.1.1):

            empty transaction (commit or abort)   -> KEPT
            read-only code (print only)           -> KEPT
            SyntaxError (transaction never opened) -> KEPT
            operation that CHANGED then aborted  -> CLEARED
            new successful operation             -> CLEARED (normal behavior)

        So the two failed runs in the log had NOT touched the stack; had
        the button existed that day, the work would have come back. Still,
        code that changes things and then blows up burns the stack —
        blogu_calistir says so when it notices.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "No document is open."
        names = list(getattr(doc, "RedoNames", ()) or ())
        if not names:
            return False, ("Nothing to redo. If you made a new change after "
                           "undoing, the redo history was cleared.")

        top = names[0]
        doc.redo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"ileri alma sonrasi recompute: {e}")
        # A stale binding = HARD CRASH risk — same rationale as in undo.
        self.executor.namespace_temizle()
        self.gunluk.sistem(f"REDO: {top}")
        return True, top

    def _ai_undo(self) -> None:
        """Carries out the model's GERI-AL request.

        MEASURED (LOG/2026-08-20_baa70fa4.txt) — the absence of this feature
        caused three separate losses:

          15:32:51  AI: "Ilk adim kod degil: Ctrl+Z ile ... geri don."
          15:46:12  USER: "geri aldim"
                    -> 13 minutes 21 seconds, the session stalled completely.

          16:04:52  AI said the same thing again.
          16:05:20  AI: "GERI ALINDIGININ VARSAYIP devam ediyorum"
                    -> and wrote code on top of that assumption. The user
                       said "tamam"; whether that meant "I undid it" or "go
                       on" is unclear. The model wrote code against a state
                       it could not verify.

        The third is the real one: this is not a speed problem, it is a
        CORRECTNESS problem.
        """
        if self._undo_turns >= _UNDO_LIMIT:
            self.mesaj.emit("sistem",
                            f"The AI asked to undo {_UNDO_LIMIT} times in a "
                            "row; stopped. You can tell it where to go "
                            "back to.")
            return

        done, note = self.geri_al(ai_mi=True)
        if done:
            self._undo_turns += 1
            self.mesaj.emit("sistem", f"AI undid: {note}")
            return

        # FAILED. The model THINKS its request was carried out and will
        # build its next step on that assumption — measured loss #3
        # itself. So we don't stay silent: one automatic turn is spent
        # telling the model what did not happen. On success no turn is
        # SPENT, because there the model's assumption is already right.
        self.mesaj.emit("sistem", "The AI asked to undo but it was not done: "
                                  + note)
        self.gunluk.sistem("UNDO refused: " + note)
        self.gonder(
            "Your undo request was NOT carried out. Reason: " + note +
            "\nThe document is unchanged. Do NOT assume it was undone. "
            "Either ask the user in one sentence what they want, or give "
            "a step that continues from the current state.",
            kullanici_mi=False)

    def sonucu_gonder(self, sonuc, kullanici_mi: bool = True) -> None:
        """Sends an execution result (output and console warnings included) to the model.

        The user's request: "let the AI see the warning and info codes too,
        the orange parts." FreeCAD's console warnings usually don't raise;
        the code looks successful but something went wrong.

        If there is output, _send_output gets here on its own; the button is
        only needed when the user wants to send something extra.
        """
        self.gonder(
            "The code you just gave was run. The result is below, "
            "including its print() output and warnings from FreeCAD's own "
            "console. If something is wrong, say what went wrong and give "
            "ONLY the first step of the fix; if not, confirm in one sentence "
            "— if a number was asked for, state the number directly.\n\n"
            f"<execution_result>\n{sonuc.modele_metin()}\n</execution_result>",
            kullanici_mi=kullanici_mi)

    def hatayi_gonder(self, sonuc) -> None:
        """The panel's "Send error to AI" button.

        The button is still there after auto-repair (see _auto_repair)
        kicked in: when the budget is spent or the same error repeats, the
        user may still want to send it.
        """
        self._send_error(sonuc, kullanici_mi=True)

    def _send_error(self, result, kullanici_mi: bool) -> None:
        self.gonder(
            "The code you just gave failed when run on the live document. "
            "The transaction was rolled back, the document is unchanged. "
            "Give a corrected COMPLETE block; do not apologise or pad the "
            "explanation. If the error calls for it, choose a DIFFERENT "
            "approach instead of retrying the same one.\n\n"
            f"<execution_error>\n{result.hata_izi.strip()}\n</execution_error>",
            kullanici_mi=kullanici_mi)

    # -- internal ----------------------------------------------------------

    def _text_chunk(self, chunk: str) -> None:
        # We don't open the live box until the first chunk arrives; on
        # codeless/empty replies it should not leave an empty bubble.
        if not self._streaming:
            self._streaming = True
            self.akis_basladi.emit()
        self.akis_parcasi.emit(chunk)

    def _turn_done(self, result: TurSonucu) -> None:
        if self._streaming:
            self.akis_bitti.emit()
            self._streaming = False

        if result.hata_mi:
            self.mesaj.emit("sistem", result.aciklama or "Unknown error.")
            self.gunluk.sistem("ERROR: " + (result.aciklama or "unknown"))
            self.bilgi_satiri.emit("hata", result.aciklama or "")
            return

        self._turn_count += 1
        self._tk_total += result.tk_toplam

        plain, found = blocks.ayikla(result.metin)

        # Is GORSEL-KONTROL wanted? We don't show the marker to the user —
        # it is a protocol word, not part of the message.
        visual_match = _VISUAL_MARKER.search(plain or "")
        visual_requested = visual_match is not None
        if visual_requested:
            # "GORSEL-KONTROL 3" = the model itself asked for three angles
            # (it made a big change and doesn't trust a single frame).
            self._visual_multi = bool(visual_match.group(1))
            # "YAKIN Name1,Name2" = zoom the camera in on them.
            names = (visual_match.group(2) or "").strip()
            self._visual_closeup = [a for a in names.split(",")
                                    if a][:_CLOSEUP_MAX]
            plain = _VISUAL_MARKER.sub("", plain).strip()
        elif _VISUAL_KEYWORD.search(plain or ""):
            # The marker is there but not in place. We don't leave the
            # channel SILENT: it goes into the log and rides the next
            # automatic prompt as a note (see gonder).
            self._visual_warning = True
            self.gunluk.sistem("GORSEL-KONTROL marker was not at the end "
                               "of the reply — no image sent, the model "
                               "will be told")

        undo_requested = _UNDO_MARKER.search(plain or "") is not None
        if undo_requested:
            plain = _UNDO_MARKER.sub("", plain).strip()

        if plain:
            self.mesaj.emit("ai", plain)
        elif not found:
            self.mesaj.emit("ai", "(empty reply)")

        # Undoing comes BEFORE the code cards. The same reply can hold both
        # "undo that" and the corrected code; when the user presses Run the
        # document must be at the right point.
        if undo_requested:
            self._ai_undo()

        for block in found:
            self.oneri.emit(block)

        self.gunluk.oturum_ac(result.oturum or self.transport.oturum, result.model)
        # SPENDING and CONTEXT go into the log separately; folding both
        # into one number produced the jump that showed context at 2x.
        # `api=` is here too: if the jump happens again, the cause is
        # visible in the log.
        usage = f"{result.tk_toplam} token · context {result.tk_baglam}"
        if result.api_cagrisi > 1:
            usage += f" · api={result.api_cagrisi}"
        self.gunluk.ai(result.metin, result.model, result.sure_ms / 1000.0, usage)

        self.bilgi_satiri.emit(*self._status_line(result, len(found)))

        if visual_requested:
            if found:
                # There is code: capturing now would show the old state.
                # It will be captured after it runs (see blogu_calistir).
                self._visual_pending = True
            else:
                self._send_visual()

    # -- visual check ------------------------------------------------------

    def _overlap_text(self, names: list[str]) -> str:
        """Overlap measurement of the close-up objects — as text.

        Why the host does it instead of asking the model: measured
        (MANTIK 39), the model looked at the image, said "no overlap", and
        was wrong. The moment it wants a closer look, we HAND it the right
        answer; it spends no extra turn and there is no chance of
        forgetting.

        FOCUS MODE (2026-08-27). This used to put the objects in a list and
        call `cakisma_kontrol(*all of them)` which — contrary to its
        docstring — scanned the WHOLE document. Measured
        (LOG/2026-08-27_9564dc71.txt): 44 objects, 946 pairs, the 2 s
        budget ran out, **431 pairs never measured**, and most of the 38
        returned lines were hidden cutting bases — i.e. the answer asked
        for never came, noise did.

        Now `odak=` is used: only pairs involving the close-up object. Same
        document: 16 pairs, 0.38 s, 2 lines.
        """
        try:
            import FreeCAD as App

            from .execution import olcum

            doc = App.ActiveDocument
            if doc is None:
                return ""
            objects = [doc.getObject(a) for a in names]
            objects = [o for o in objects if o is not None]
            if not objects:
                return ""
            if len(objects) == 1:
                # One object: the pairs that INVOLVE it. The candidates are
                # found by cakisma_kontrol itself and the consumed ones are
                # filtered out (see kesif.tuketilmis_mi).
                result = olcum.cakisma_kontrol(odak=objects[0], yaz=False)
                return result.get("satir", "")
            # More than one object was EXPLICITLY asked for: exactly those
            # are measured, no filtering — the model gets what it asked.
            result = olcum.cakisma_kontrol(*objects, yaz=False)
            return result.get("satir", "")
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"yakin cekim cakisma olcumu yapilamadi: {e}")
            return ""

    def _output_instead_of_visual(self, output: str, reason: str) -> None:
        """The visual could not be sent. THE OUTPUT WAS RIDING ON IT — don't swallow that too.

        MEASURED (LOG/2026-08-24_3ad4cef1.txt, 12:03:26): after a
        successful run NOTHING landed in the log — neither output nor
        visual. The cause was the visual budget, but the bill went to the
        output: the output RIDES ON this call (see blogu_calistir), and
        when the visual path returned early,
        `dolgu alani: 3080 mm2 | cakisma: 0.00 mm2` went with it. The
        model got zero feedback about a successful run.

        And now the suppression is ALSO written to the LOG. It used to go
        only to the panel via `mesaj.emit`; every other suppression path
        (e.g. "AUTO-REPAIR budget exhausted") writes to the log. So someone
        reviewing the log later could find no reason for that gap.
        """
        self.gunluk.sistem("IMAGE NOT SENT: " + reason)
        if not output:
            return
        self.gunluk.sistem(f"OUTPUT sent anyway ({len(output)} chars)")
        self.gonder(
            "The code you just gave was run; its output is below. The 3D "
            "image you asked for could NOT be sent (" + reason + "), so do not "
            "talk as if you had looked at it. Continue with the numbers you "
            "have if you can; if you really need to look, ask the user to "
            "describe what you need to see.\n\n"
            f"<execution_result>\n{output}\n</execution_result>",
            kullanici_mi=False)

    def _frame_count(self) -> tuple[bool, str]:
        """Three frames or one — THE HOST DECIDES, not the model.

        WHY IT CHANGED (measured, LOG/2026-08-27_9564dc71.txt). The old rule
        was "three frames if the model says 'GORSEL-KONTROL 3'", i.e. the
        decision was the model's. Result: **27 of 30** visual sends were
        three frames (90%), and the ratio stayed 90% even AFTER the
        contract said "three frames is not the default". One system-prompt
        line does not beat 40 examples in the model's own context. If the
        rule doesn't hold, move it to where it gets enforced.

        The cost was measured: 30 sends, 916 KB, ~30 KB per turn on
        average, and it grows as the model gets complicated (22 KB in the
        first half, 47 KB in the second) — roughly a third of the context
        window.

        The gain was not measured, because there IS none: in 7 of the 30
        turns with a visual return the model found a problem, and in **all
        seven** the evidence was a printed number (bbox, volume,
        cakisma_kontrol) — things like a "0.2 mm overhang" are invisible at
        4 px/mm anyway. There is not a single finding the image caught on
        its own.

        The three-frame allowance is granted in two cases:
          * the last block added NEW OBJECTS — something sits in space
            whose position was never proven; one angle doesn't settle "is
            it floating"; or
          * this is the second look in a row — the first frame didn't
            settle the question.
        With neither, a single frame goes out and the model is told WHY it
        is a single frame; otherwise it repeats the same request.
        """
        asked = self._visual_multi
        new_objects = bool(self._last_added)
        second_look = self._visual_turns >= 1
        if new_objects or second_look:
            return True, ""
        if asked:
            return False, (
                "\n\nNOTE: you asked for three frames, one was sent — no "
                "new object was added this turn (you changed an existing "
                "one) and this is the first look. Three frames eat a large "
                "part of the context window, and it was measured that "
                "NUMBERS give the findings anyway. If one frame is not "
                "enough, measure in the next block: bbox, volume, "
                "check_overlap(focus=...). If you really need the angles, "
                "end your reply with GORSEL-KONTROL 3 again; the second look "
                "gets them.")
        return False, ""

    def _send_visual(self, output: str = "") -> None:
        """Captures the 3D view and sends it to the model. Never stays silent on failure.

        If `output` is given it rides on the same message: when the code
        both printed something and a visual was asked for, spending two
        turns makes no sense.
        """
        self._visual_pending = False

        # THE VISUAL IS OFF (see VISUAL_ENABLED). It sits at the very top
        # so that none of the counters below get polluted; when it is
        # switched back on, the old behavior returns as it was.
        #
        # The model may still ask (old habit, even if the contract no
        # longer has the clause). So we do NOT STAY SILENT: the output is
        # sent and it is told not to talk as if it had looked at the image.
        if not VISUAL_ENABLED:
            self._visual_multi = False
            self._last_added = []
            self._visual_closeup = []
            self._output_instead_of_visual(
                output, "visual system is off — measure instead")
            return

        # LOOP SAFETY: the model can look at a picture and ask for another
        # one. Two turns are enough; on the third we stop and hand the ball
        # to the user.
        #
        # WHAT THE COUNTER COUNTS. Only BACK-TO-BACK looks with no work in
        # between. It resets when code runs (see blogu_calistir), because
        # the guard's target was "look and look again", not "look - change -
        # look again". Measured (LOG/2026-08-24_3ad4cef1.txt): Opus looked
        # at 11:46 / 11:53 / 11:58, gave a GERI-AL and wrote new code
        # between every look — exactly the loop we want — and was punished
        # on the fourth because the budget was full.
        if self._visual_turns >= _VISUAL_LIMIT:
            self.mesaj.emit("sistem",
                            f"The AI asked for a visual check {_VISUAL_LIMIT} "
                            "times in a row; stopped. You can describe "
                            "what it should look at.")
            self._output_instead_of_visual(
                output, f"asked {_VISUAL_LIMIT} times in a row, stopped")
            return

        if not gorunum.yakalanabilir_mi():
            self.mesaj.emit("sistem",
                            "The AI wanted to see the 3D view but there "
                            "is no active 3D window. Open a document and retry.")
            self._output_instead_of_visual(output, "no open 3D window")
            return

        multi_angle, frame_note = self._frame_count()
        self._visual_multi = False
        # The allowance is used ONCE. Without clearing, an object added in
        # a previous turn would keep granting the three-frame allowance to
        # later looks.
        self._last_added = []
        closeup = list(self._visual_closeup)
        self._visual_closeup = []

        if closeup:
            # CLOSE-UP. A general frame doesn't show fine work: on a 201 mm
            # model a 900x640 frame is ~4 px/mm, so a 0.6 mm part is 2
            # pixels (measured, MANTIK 39). The camera moves in on the
            # object.
            frames = gorunum.yakala_yakin(closeup, cok_aci=multi_angle)
            if not frames:
                # If we couldn't zoom in we do NOT stay silent: we fall
                # back to the normal frame and tell the model (in the prompt
                # text below).
                single = gorunum.yakala()
                frames = [single] if single else []
                closeup_fell_back = True
            else:
                closeup_fell_back = False
        elif multi_angle:
            frames = gorunum.yakala_cok()
            closeup_fell_back = False
        else:
            single = gorunum.yakala()
            frames = [single] if single else []
            closeup_fell_back = False

        if not frames:
            self.mesaj.emit("sistem",
                            "The AI asked for the 3D view but the capture "
                            "failed (details in the Report view).")
            self._output_instead_of_visual(output, "capture failed")
            return

        data = frames if len(frames) > 1 else frames[0]
        size_bytes = sum(len(k) for k in frames)
        label = (f"{len(frames)}-angle view" if len(frames) > 1
                 else "3D view")

        self._visual_turns += 1
        closeup_suffix = f", CLOSE-UP: {', '.join(closeup)}" if closeup else ""
        self.mesaj.emit("sistem",
                        f"{label} sent to AI ({size_bytes // 1024} KB"
                        f"{closeup_suffix}).")
        self.gunluk.sistem(f"GORSEL-KONTROL: {len(frames)} frame(s) sent "
                           f"({size_bytes} bytes){closeup_suffix}")
        if len(frames) > 1:
            prompt = (f"The 3D images you asked for are attached, from "
                      f"{len(frames)} angles: 1) the angle the user sees on "
                      f"screen, 2) FRONT view (from -Y), 3) TOP view (from "
                      f"+Z). Look at all three — what one angle hides (whether "
                      f"something floats, whether an alignment is off) shows "
                      f"in the others. Then: if it looks right, confirm in one "
                      f"sentence; if something is wrong, say what and give "
                      f"ONLY the first step of the fix.")
        else:
            prompt = ("The 3D image you asked for is attached. Then: if it "
                      "looks right, confirm in one sentence; if something is "
                      "wrong, say what and give ONLY the first step of the "
                      "fix. If one angle is not enough to be sure, do not "
                      "guess: end your reply with GORSEL-KONTROL 3 to look "
                      "from three angles.")
        # If the host reduced three frames to one, we say WHY. Reducing it
        # silently pushes the model to repeat the same request.
        prompt += frame_note

        # THE MEASUREMENT GOES WITH THE CLOSE-UP. The user's decision:
        # "look closely and examine in detail" + the number alongside the
        # image. The overlap question doesn't settle with the image anyway
        # (MANTIK 39), so the same message also carries the deterministic
        # answer — no extra turn spent.
        if closeup:
            prompt = (f"CLOSE-UP: the camera zoomed in on — "
                      f"{', '.join(closeup)}. " + prompt)
            if closeup_fell_back:
                prompt += ("\n\nNOTE: the camera could not zoom in, this frame "
                           "is the GENERAL view (details in the Report view).")
            overlap_text = self._overlap_text(closeup)
            if overlap_text:
                prompt += ("\n\nDETERMINISTIC overlap measurement of the same "
                           "objects (the image cannot settle this, this does):\n"
                           f"<execution_result>\n{overlap_text}\n"
                           "</execution_result>")
        if output:
            prompt += (f"\n\nprint() output of the same code:\n"
                       f"<execution_result>\n{output[:2000]}\n"
                       f"</execution_result>")
        self.gonder(prompt, gorsel=data, kullanici_mi=False)

    def _status_line(self, turn: TurSonucu, block_count: int) -> tuple[str, str]:
        """Bottom status bar text + tooltip.

        Dollars are NOT shown, tokens are: the subscription doesn't charge
        dollars, that number was only the "at API prices" equivalent and it
        was misread as "I'm spending money". Tokens are the resource
        actually used.
        """
        parts = [f"{turn.sure_ms / 1000:.1f} s"]
        if turn.model:
            parts.append(turn.model)
        parts.append(f"{_short_num(turn.tk_toplam)} token")
        # CONTEXT FULLNESS. The CLI doesn't report the limit (all of the
        # init and result fields were scanned), so the model's catalog value
        # is written as a constant — see config.BAGLAM_SINIRI. The used side
        # is a real measurement.
        parts.append(f"{_short_num(turn.tk_baglam)}/{config.baglam_siniri_kisa()} context")
        # We don't write "0 code blocks": noise that carries no information,
        # the user was right to call it "what's that, delete it if it's
        # useless". It is meaningful when above zero.
        if block_count:
            parts.append(f"{block_count} code block" + ("s" if block_count > 1 else ""))

        tooltip = [
            "Runs through your Claude Code subscription "
            "(drawn from its monthly Agent SDK credit).",
            "",
            f"Context: {turn.tk_baglam:,} / {config.BAGLAM_SINIRI:,} tokens",
            "  (input + cache; output does not count)",
            "  Limit is the model's catalog value - the CLI does not report it.",
            "",
            "This turn:",
            f"  input            {turn.tk_girdi:>9,}",
            f"  cache read       {turn.tk_onbellek_okuma:>9,}   (cheap)",
            f"  cache write      {turn.tk_onbellek_yazma:>9,}",
            f"  output           {turn.tk_cikti:>9,}",
            f"  TOTAL            {turn.tk_toplam:>9,}",
            "",
            f"This chat so far: {self._tk_total:,} tokens / {self._turn_count} turns",
        ]
        if turn.maliyet_usd:
            tooltip += ["",
                        f"At API prices this would cost ~${turn.maliyet_usd:.3f} -",
                        "covered by your plan's credit until it runs out."]
        if self.gunluk.dosya:
            tooltip += ["", f"Chat log: {self.gunluk.dosya}"]

        log.ayik(" · ".join(parts))
        return " · ".join(parts), "\n".join(tooltip)
