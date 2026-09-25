"""Turn orchestration - the brain between the panel and transport/execution.

It does NOT KNOW the UI (imports no widgets); it only emits signals. That way
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


# The marker the model uses to ask for an image. The contract says "END your
# reply with this marker"; the two accepted places are exactly that: on its
# own line or at the very end of the message. The marker appearing in the
# middle of the text does not trigger, otherwise a sentence like "no need
# for a GORSEL-KONTROL" would take a picture. Both spellings are accepted in
# case it is written with the Turkish character. A trailing "3" means the
# model wants THREE ANGLES (a big change).
#
# WHY END-OF-LINE IS ACCEPTED TOO: measured — the model wrote "...ready to
# print — GORSEL-KONTROL", and because the marker was not on its own line
# the host SILENTLY sent nothing and the model never found out. 1 in 5
# requests got lost this way; 41 seconds later the user had to type.
#
# The "YAKIN <name>" suffix: moves the camera close to those objects (see
# gorunum.yakala_yakin). The reason was measured — when the whole model fits
# in the frame, the frame gives ~4 pixels/mm and fine work is invisible
# (MANTIK 39). Names are FreeCAD INTERNAL NAMES, comma separated; the
# pattern does NOT allow spaces so the rest of the sentence is not mistaken
# for a name.
_GORSEL_ISARET = re.compile(
    r"(?:^[ \t]*|[ \t—:-][ \t]*)G[OÖ]RSEL-KONTROL(?:[ \t]+(3))?"
    r"(?:[ \t]+YAKIN[ \t]+([A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*))?[ \t]*$",
    re.MULTILINE | re.IGNORECASE)

# At most how many objects in a close-up. More than three is no longer
# "close": the camera pulls back to fit them all in the frame and we are
# left with the general frame again.
_YAKIN_AZAMI = 3

# Does the marker APPEAR in the text but not match the pattern above? Then
# we do not stay silent: one sentence is attached to the next automatic
# prompt. It costs no extra turn, it rides on the existing prompt.
_GORSEL_ANAHTAR = re.compile(r"G[OÖ]RSEL-KONTROL", re.IGNORECASE)
_GORSEL_UYARI = ("Note: your reply contained GORSEL-KONTROL but not at "
                 "the END, so no image was sent. If you really want to "
                 "look, end your reply with that marker alone.")

# At most how many visual check turns in a row. The model can look at the
# image and ask for an image again; on the third we stop and hand the ball
# to the user.
_GORSEL_SINIR = 2

# THE VISUAL SYSTEM IS OFF FOR NOW (user decision, 2026-08-28).
#
# THE CODE WAS NOT DELETED, IT WAS DISABLED — we may fix it and turn it back
# on in the future. To turn it on: set this to True and put the
# GORSEL-KONTROL clause back into transport.SISTEM_SOZLESMESI (both are
# needed; if the contract does not describe it, the model never writes the
# marker).
#
# WHY IT WAS TURNED OFF — an experiment was run (PLAN S9, same prompt three
# times):
#   A  with photos     6 blocks, 129 KB frames, 48.7k tokens -> good
#   B1 without photos  4 blocks,      0 KB,     37.2k tokens -> bad
#   B2 without photos  8 blocks,      0 KB,     50.6k tokens -> BEST
# The best and the worst run were in the SAME arm. So what separated quality
# was not the image but the NUMBER OF STEPS (4 -> bad, 6 -> good, 8 -> best),
# and the measured cost of the photo in that pair was 31% tokens, 44% time.
# The image's contribution stayed below the measurement noise; the sample is
# not enough for a firm verdict, but the cost is certain and the benefit is
# not.
GORSEL_ACIK = False

# The marker the model uses to undo its OWN change.
# The user's question: "can't the AI do the undo too, why does it force the
# user to do it?" It can — only what it undoes has to be checked.
_GERI_AL_ISARET = re.compile(r"^[ \t]*GER[İI]-AL[ \t]*$",
                             re.MULTILINE | re.IGNORECASE)

# At most how many automatic undos in a row. The model can undo and want to
# undo again; such a loop would take the user's work apart turn by turn.
_GERI_AL_SINIR = 2

# Prefix of the transactions the executor opens. It is the only thing that
# TELLS APART whether the top undo entry was left by the AI or the user.
_AI_ONEK = "AI: "

# How many AUTOMATIC repair turns are requested when code blows up. PLAN
# M4's budget. More than two turns into a long chain without the user
# knowing.
_ONARIM_SINIRI = 2


def _kisa_sayi(n: int) -> str:
    """12400 -> '12.4k'. Space in the panel is tight, raw digits don't read well."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class ConversationController(QtCore.QObject):
    # role: "user" | "ai" | "sistem"
    mesaj = QtCore.Signal(str, str)          # role, text
    akis_basladi = QtCore.Signal()           # open the live reply box
    akis_parcasi = QtCore.Signal(str)        # reply text, while streaming
    dusunce_parcasi = QtCore.Signal(str)     # the model's thinking text (if any)
    dusunce_olcusu = QtCore.Signal(int)      # estimated thinking tokens
    akis_bitti = QtCore.Signal()
    asama = QtCore.Signal(str)               # baglaniyor | dusunuyor | yaziyor
    oneri = QtCore.Signal(object)            # blocks.KodBloku
    calisma_sonucu = QtCore.Signal(object)   # executor.CalismaSonucu
    durum = QtCore.Signal(str)               # bosta | calisiyor | oluyor
    bilgi_satiri = QtCore.Signal(str, str)   # text, hint (tooltip)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.transport = KaliciTransport(self)
        self.executor = CodeExecutor()
        self.gunluk = SohbetGunlugu()

        # Tokens accumulated over the session - "how much did I spend in this chat"
        self._tk_toplam = 0
        self._tur_sayisi = 0
        self._akan_var = False

        # Visual check state. `_gorsel_bekliyor`: the model asked for
        # GORSEL-KONTROL but the same reply also had code -> capture AFTER
        # the code runs.
        self._gorsel_bekliyor = False
        self._gorsel_tur = 0
        # Did the model ask for THREE ANGLES this time ("GORSEL-KONTROL 3").
        self._gorsel_cok = False
        # "GORSEL-KONTROL YAKIN Name1,Name2" — objects to zoom the camera in on.
        self._gorsel_yakin: list[str] = []
        # The marker appeared in the text but was not at the end of the
        # reply -> a one-sentence note will be attached to the next
        # AUTOMATIC prompt.
        self._gorsel_uyari = False
        # Objects ADDED by the last block that ran. The host grants the
        # three-frame allowance based on this (see _kac_kare).
        self._son_eklenen: list[str] = []
        self._geri_al_tur = 0
        self._onarim_tur = 0
        self._son_hata = ""

        self.transport.tur_bitti.connect(self._tur_bitti)
        self.transport.durum_degisti.connect(self.durum.emit)
        self.transport.metin_parcasi.connect(self._metin_parcasi)
        self.transport.dusunce_parcasi.connect(self.dusunce_parcasi.emit)
        self.transport.dusunce_olcusu.connect(self.dusunce_olcusu.emit)
        self.transport.asama.connect(self.asama.emit)
        self.transport.limit_bilgisi.connect(
            lambda s: self.mesaj.emit("sistem", s))

        self.gunluk.oturum_ac(self.transport.oturum)

    # -- public ------------------------------------------------------------

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
        # automatically sent visual turn does not, otherwise the limit would
        # never fill up.
        if kullanici_mi:
            self._gorsel_tur = 0
            self._geri_al_tur = 0
            self._onarim_tur = 0
            self._son_hata = ""
            self._gorsel_uyari = False
        elif self._gorsel_uyari:
            # A dropped image request does not stay SILENT. We don't open an
            # extra turn; it rides at the end of the automatic prompt that is
            # going out anyway.
            metin = metin + "\n\n" + _GORSEL_UYARI
            self._gorsel_uyari = False

        if kullanici_mi:
            self.mesaj.emit("user", metin)
        self.gunluk.oturum_ac(self.transport.oturum)
        # A message a human typed and a turn the panel sent on its own must
        # be TELL-APART-ABLE in the log.
        (self.gunluk.kullanici if kullanici_mi else self.gunluk.otomatik)(metin)

        self.executor.oturumu_ayarla(self.transport.oturum)
        self._akan_var = False
        self._t0 = time.time()

        try:
            baglam = serializer.belge_metni()
        except Exception as e:
            log.uyari(f"could not read the document context: {e}")
            baglam = "<document>unreadable</document>"

        self.transport.tur_gonder(f"{baglam}\n\n<request>\n{metin}\n</request>",
                                  gorsel=gorsel)

    def iptal(self) -> None:
        self.transport.iptal()

    def yeni_sohbet(self) -> None:
        self.transport.yeni_oturum()
        self.executor.namespace_temizle()
        self._tk_toplam = 0
        self._tur_sayisi = 0
        # New session = NEW FILE. The "1 session = 1 log" rule.
        self.gunluk.oturum_ac(self.transport.oturum)
        self.mesaj.emit("sistem", "New chat started — previous context forgotten.")
        self.bilgi_satiri.emit("", "")

    def sohbeti_surdur(self, oturum: str, dosya) -> None:
        """Returns to an old chat picked from the library.

        It differs from `yeni_sohbet` in two ways, both deliberate:
        - we do NOT CLEAR the namespace; the user keeps working in the same
          FreeCAD document, deleting their variables would not help them.
        - the log does NOT open a new file, it continues the old one (see
          `sohbet_log.dosyaya_devam`) — one chat, one file.

        The counters are reset: the token total and turn count count the
        turns in THIS session; our counter does not know the inherited
        history, and pretending it did would produce a wrong number.
        """
        self.transport.oturumu_surdur(oturum)
        self._tk_toplam = 0
        self._tur_sayisi = 0
        try:
            self.gunluk.dosyaya_devam(oturum, dosya)
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"could not continue the log: {e}")
        self.executor.oturumu_ayarla(oturum)
        self.bilgi_satiri.emit("", "")

    def blogu_calistir(self, blok: blocks.KodBloku) -> None:
        """When 'Run' is pressed in the panel."""
        self.gunluk.kod(blok.kod, blok.baslik)
        ileri_vardi = self._ileri_sayisi()
        sonuc = self.executor.calistir(blok.kod, blok.baslik)
        self.gunluk.calisma(sonuc)
        # WORK WAS DONE IN BETWEEN: the visual counter counts the "look -
        # look again" chain, not "look - change - look again" (see
        # _gorseli_gonder). If code ran, there is something new to look at.
        if not sonuc.engellendi:
            self._gorsel_tur = 0
            self._son_eklenen = list(getattr(sonuc, "eklenen", None) or [])
        # Code that runs AFTER an undo burns the redo stack (measured, see
        # ileri_al). It should not vanish silently: the user thinks they can
        # go back to what they undid and finds an empty stack when they
        # press the button.
        if ileri_vardi and self._ileri_sayisi() == 0:
            self.mesaj.emit("sistem",
                            f"Redo history cleared ({ileri_vardi} steps) "
                            "— a new change was made on top.")
            self.gunluk.sistem(f"REDO STACK CLEARED ({ileri_vardi} steps)")
        self.calisma_sonucu.emit(sonuc)

        try:
            import FreeCADGui as Gui
            Gui.updateGui()
        except Exception:
            pass

        # If the repeat guard stopped it, the code NEVER ran. That is not an
        # error, it is a question put to the user; sending the model "your
        # code blew up" would push it to look for another way for nothing.
        if sonuc.engellendi:
            return

        # The model wanted to see the RESULT of this code. We capture it now:
        # the code ran, the 3D is up to date. Since updateGui() was called
        # above, the image contains the new geometry.
        if self._gorsel_bekliyor:
            if sonuc.basarili:
                # If there is output it rides on the SAME turn — spending a
                # separate turn is unnecessary and the model should see the
                # two messages together, not one after the other.
                self._gorseli_gonder(sonuc.cikti)
                return
            # The code blew up, the transaction was rolled back - nothing new
            # to show.
            self._gorsel_bekliyor = False

        if not sonuc.basarili:
            self._otomatik_onar(sonuc)
        elif sonuc.cikti:
            self._ciktiyi_yolla(sonuc)

    def _ciktiyi_yolla(self, sonuc) -> None:
        """The code SUCCEEDED and printed something: send it back to the model.

        WHY. The log review (2026-08-21, item 1) measured this: 8 blocks
        containing print() ran, and the output of all 8 NEVER reached the
        model. The executor captured the output, wrote it to the log and
        showed it in the panel — it just did not send it to the model. The
        card's "Send result to AI" button was also only visible when there
        was a WARNING, so there was NO way at all to pass on a result that
        consisted only of output.

        The model's reaction to this is in the log, and this was its cost:

          * creating objects in the document to measure (adding a Draft
            circle to learn a number and reading its radius on the NEXT
            turn),
          * burying the result in a deliberate exception to get it back — in
            its own words: "I'll bury the result in a deliberate error so it
            comes back to you automatically". It worked, because the ERROR
            path was fed automatically and the SUCCESS path was not. The
            model had found the one hole the host left open.

        Now the success path is fed too; both of those patterns are
        unnecessary. There is no loop risk: every turn starts with the user
        pressing Run, it does not chain by itself.
        """
        if self.mesgul_mu():
            return
        self.gunluk.sistem("OUTPUT sent automatically "
                           f"({len(sonuc.cikti)} chars)")
        self.sonucu_gonder(sonuc, kullanici_mi=False)

    # -- automatic repair --------------------------------------------------

    @staticmethod
    def _hata_imzasi(sonuc) -> str:
        """The last line of the traceback — the identity of the error.

        Line numbers and paths can change; if what changes is not the TYPE
        and message of the error, the model is still hitting the same wall.
        """
        satirlar = (sonuc.hata_izi or "").strip().splitlines()
        return satirlar[-1].strip() if satirlar else ""

    def _otomatik_onar(self, sonuc) -> None:
        """When the code blows up, sends the error to the model BY ITSELF.

        WHY. This used to require the user to PRESS the "Send error to AI"
        button; if they didn't, the model never learned its code had blown
        up. That is exactly the same pattern as the undo problem (MANTIK
        19): a job the host could do on its own was being made a human's
        job. In the log the user pressed that button three times — the flow
        was the same every time, the only difference a click and the chance
        that the user was looking elsewhere at that moment.

        TWO LIMITS. PLAN M4 said "a budget of 2 attempts":

        1. At most _ONARIM_SINIRI automatic turns. After that it stops and
           the ball goes to the user — the button stays in place, it can be
           sent by hand.
        2. If the SAME error comes twice, stop IMMEDIATELY. There is no point
           filling up the budget: the model is hitting the same wall and a
           third attempt would crash into the same place. This is the real
           limit that kicks in earlier than the budget limit.
        """
        imza = self._hata_imzasi(sonuc)

        if imza and imza == self._son_hata:
            self._son_hata = ""
            self.mesaj.emit("sistem",
                            "The same error repeated; auto-repair "
                            "stopped. Please describe a different "
                            "approach.")
            self.gunluk.sistem("AUTO-REPAIR stopped: same error repeated")
            return

        if self._onarim_tur >= _ONARIM_SINIRI:
            self.mesaj.emit("sistem",
                            f"{_ONARIM_SINIRI} auto-repair attempts "
                            "were not enough; stopped. You can continue "
                            "with “Send error to AI”.")
            self.gunluk.sistem("AUTO-REPAIR budget exhausted")
            return

        if self.mesgul_mu():
            return                     # keep the manual send path open

        self._onarim_tur += 1
        self._son_hata = imza
        self.mesaj.emit("sistem",
                        f"Error sent to AI automatically "
                        f"({self._onarim_tur}/{_ONARIM_SINIRI}).")
        self._hatayi_yolla(sonuc, kullanici_mi=False)

    # -- undo --------------------------------------------------------------

    def geri_al(self, ai_mi: bool = False) -> tuple[bool, str]:
        """Undoes the last AI change. Returns: (done, explanation).

        Both the panel button and the model's GERI-AL marker come in HERE,
        because the dangerous thing is the same in both: WHOSE work is on
        top of the stack.

        The old button called `doc.undo()` unconditionally and its label was
        "Undo last AI change". If the user had done something by hand after
        the AI's code, the button undid THEIR work — the label was lying.
        Now the prefix of the top entry is checked.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "No document is open."
        adlar = list(getattr(doc, "UndoNames", ()) or ())
        if not adlar:
            return False, "Nothing to undo."

        tepe = adlar[0]
        if not tepe.startswith(_AI_ONEK):
            return False, (
                f"The top of the undo stack is not an AI change — it is "
                f"“{tepe}”, your own edit. Stopped so it is not lost. "
                f"Use Ctrl+Z if you want to undo it yourself.")

        doc.undo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"recompute after undo: {e}")
        # Stale binding = HARD CRASH risk (see executor.namespace_temizle).
        self.executor.namespace_temizle()
        kim = "AI" if ai_mi else "User"
        self.gunluk.sistem(f"UNDO ({kim}): {tepe}")
        return True, tepe

    @staticmethod
    def _ileri_sayisi() -> int:
        """Number of steps on the redo stack. 0 if there is no document."""
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return 0
        return len(list(getattr(doc, "RedoNames", ()) or ()))

    def ileri_al(self) -> tuple[bool, str]:
        """RE-APPLIES the last undone change. Returns: (done, explanation).

        MEASURED (LOG/2026-08-24_3ad4cef1.txt, 12:09:33 -> 12:09:58): the
        user accidentally undid exactly the result they had just called
        "yes, that's nice, just what I wanted" — three times in six seconds.
        Then they tried to re-run the old code block, got the same error
        twice ("bunny or Belly_fill missing" — because the undo had deleted
        the fill) and the session ended there. At that moment FreeCAD's redo
        stack still held THREE entries; 25 minutes of work did not come back
        because a button was missing.

        UNLIKE GERI-AL, the user's own entry can be redone too. The
        asymmetry is deliberate: undo DELETES work (if the user's effort is
        on top of the stack it destroys it — that is why there is a check
        there), redo BRINGS work BACK. Refusing would protect nothing, so we
        only say what came back.

        MEASURED — EXACTLY when the redo stack is cleared (FreeCAD 1.1.1):

            empty transaction (commit or abort)       -> KEPT
            read-only code (print only)               -> KEPT
            SyntaxError (transaction never opened)    -> KEPT
            aborted transaction that MADE A CHANGE    -> CLEARED
            new, successful transaction               -> CLEARED (normal behaviour)

        So the two failed runs in the log had NOT touched the stack; had the
        button existed that day, the work would have come back. Still, code
        that "makes a change and blows up" burns the stack — blogu_calistir
        notices this and says so.
        """
        import FreeCAD as App

        doc = App.ActiveDocument
        if doc is None:
            return False, "No document is open."
        adlar = list(getattr(doc, "RedoNames", ()) or ())
        if not adlar:
            return False, ("Nothing to redo. If you made a new change after "
                           "undoing, the redo history was cleared.")

        tepe = adlar[0]
        doc.redo()
        try:
            doc.recompute()
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"recompute after redo: {e}")
        # Stale binding = HARD CRASH risk — the same reason as for undo.
        self.executor.namespace_temizle()
        self.gunluk.sistem(f"REDO: {tepe}")
        return True, tepe

    def _ai_geri_al(self) -> None:
        """Carries out the model's GERI-AL request.

        MEASURED (LOG/2026-08-20_baa70fa4.txt) — the lack of this feature
        caused three separate losses:

          15:32:51  AI: "The first step is not code: go back with Ctrl+Z ..."
          15:46:12  USER: "undone"
                    -> 13 minutes 21 seconds, the session stalled completely.

          16:04:52  The AI said the same thing again.
          16:05:20  AI: "I'm continuing ASSUMING it was undone"
                    -> and generated code on top of that assumption. The user
                       had said "ok"; whether that meant "undone" or "carry
                       on" was unclear. The model wrote code for a state it
                       could not verify.

        The third is the real one: this is not a speed problem, it is a
        CORRECTNESS problem.
        """
        if self._geri_al_tur >= _GERI_AL_SINIR:
            self.mesaj.emit("sistem",
                            f"The AI asked to undo {_GERI_AL_SINIR} times in a "
                            "row; stopped. You can tell it where to go "
                            "back to.")
            return

        oldu, aciklama = self.geri_al(ai_mi=True)
        if oldu:
            self._geri_al_tur += 1
            self.mesaj.emit("sistem", f"AI undid: {aciklama}")
            return

        # FAILED. The model THINKS its request was carried out and will build
        # the next step on that assumption — exactly the measured 3rd loss.
        # So we do not stay silent: one automatic turn is spent telling the
        # model what did not happen. On success NO turn is spent, because
        # there the model's assumption is already correct.
        self.mesaj.emit("sistem", "The AI asked to undo but it was not done: "
                                  + aciklama)
        self.gunluk.sistem("UNDO refused: " + aciklama)
        self.gonder(
            "Your undo request was NOT carried out. Reason: " + aciklama +
            "\nThe document is unchanged. Do NOT assume it was undone. "
            "Either ask the user in one sentence what they want, or give "
            "a step that continues from the current state.",
            kullanici_mi=False)

    def sonucu_gonder(self, sonuc, kullanici_mi: bool = True) -> None:
        """Sends the run result (including output and console warnings) to the model.

        The user's request: "let the AI see the warning and notice codes too,
        I mean the orange parts." FreeCAD's console warnings often do not
        raise an exception; the code looks successful but something has gone
        wrong.

        When there is output, _ciktiyi_yolla comes in here by itself; the
        button is only needed when the user wants to send something extra.
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
        """The "Send error to AI" button in the panel.

        After automatic repair (see _otomatik_onar) kicks in this button is
        still there: once the budget is used up or the same error repeats,
        the user may still want to send it.
        """
        self._hatayi_yolla(sonuc, kullanici_mi=True)

    def _hatayi_yolla(self, sonuc, kullanici_mi: bool) -> None:
        self.gonder(
            "The code you just gave failed when run on the live document. "
            "The transaction was rolled back, the document is unchanged. "
            "Give a corrected COMPLETE block; do not apologise or pad the "
            "explanation. If the error calls for it, choose a DIFFERENT "
            "approach instead of retrying the same one.\n\n"
            f"<execution_error>\n{sonuc.hata_izi.strip()}\n</execution_error>",
            kullanici_mi=kullanici_mi)

    # -- internal ----------------------------------------------------------

    def _metin_parcasi(self, parca: str) -> None:
        # We don't open the live box until the first part arrives; for
        # code-only/empty replies it should not leave an empty bubble.
        if not self._akan_var:
            self._akan_var = True
            self.akis_basladi.emit()
        self.akis_parcasi.emit(parca)

    def _tur_bitti(self, sonuc: TurSonucu) -> None:
        if self._akan_var:
            self.akis_bitti.emit()
            self._akan_var = False

        if sonuc.hata_mi:
            self.mesaj.emit("sistem", sonuc.aciklama or "Unknown error.")
            self.gunluk.sistem("ERROR: " + (sonuc.aciklama or "unknown"))
            self.bilgi_satiri.emit("hata", sonuc.aciklama or "")
            return

        self._tur_sayisi += 1
        self._tk_toplam += sonuc.tk_toplam

        duz, bulunan = blocks.ayikla(sonuc.metin)

        # Is GORSEL-KONTROL requested? We don't show the marker to the user -
        # it is a protocol word, not part of the message.
        gorsel_esleme = _GORSEL_ISARET.search(duz or "")
        gorsel_istendi = gorsel_esleme is not None
        if gorsel_istendi:
            # "GORSEL-KONTROL 3" = the model itself asked for three angles
            # (it made a big change and does not trust a single frame).
            self._gorsel_cok = bool(gorsel_esleme.group(1))
            # "YAKIN Name1,Name2" = zoom the camera in on those objects.
            adlar = (gorsel_esleme.group(2) or "").strip()
            self._gorsel_yakin = [a for a in adlar.split(",")
                                  if a][:_YAKIN_AZAMI]
            duz = _GORSEL_ISARET.sub("", duz).strip()
        elif _GORSEL_ANAHTAR.search(duz or ""):
            # The marker is there but not in its place. We do NOT leave the
            # channel SILENT: it is written to the log and rides on the next
            # automatic prompt as a note (see gonder).
            self._gorsel_uyari = True
            self.gunluk.sistem("GORSEL-KONTROL marker was not at the end "
                               "of the reply — no image sent, the model "
                               "will be told")

        geri_al_istendi = _GERI_AL_ISARET.search(duz or "") is not None
        if geri_al_istendi:
            duz = _GERI_AL_ISARET.sub("", duz).strip()

        if duz:
            self.mesaj.emit("ai", duz)
        elif not bulunan:
            self.mesaj.emit("ai", "(empty reply)")

        # Undo BEFORE the code cards. The same reply can contain both "undo
        # this" and corrected code; when the user presses Run the document
        # must be at the right point.
        if geri_al_istendi:
            self._ai_geri_al()

        for b in bulunan:
            self.oneri.emit(b)

        self.gunluk.oturum_ac(sonuc.oturum or self.transport.oturum, sonuc.model)
        # SPEND and CONTEXT are written to the log separately; folding them
        # into one number had produced the jump that showed context doubled.
        # `api=` is here too: if the jump happens again, the reason shows up
        # in the log.
        olcu = f"{sonuc.tk_toplam} token · context {sonuc.tk_baglam}"
        if sonuc.api_cagrisi > 1:
            olcu += f" · api={sonuc.api_cagrisi}"
        self.gunluk.ai(sonuc.metin, sonuc.model, sonuc.sure_ms / 1000.0, olcu)

        self.bilgi_satiri.emit(*self._bilgi(sonuc, len(bulunan)))

        if gorsel_istendi:
            if bulunan:
                # There is code: capturing now would show the old state. It
                # will be captured after it runs (see blogu_calistir).
                self._gorsel_bekliyor = True
            else:
                self._gorseli_gonder()

    # -- visual check ------------------------------------------------------

    def _cakisma_metni(self, adlar: list[str]) -> str:
        """Overlap measurement of the objects in the close-up — as text.

        Why the host does it instead of asking the model: measured (MANTIK
        39), the model looked at the image, said "no overlap" and was wrong.
        The moment it wants to look closely we HAND IT the right answer; it
        spends no extra turn and there is no chance of forgetting.

        FOCUS MODE (2026-08-27). Objects used to be put in a list here and
        `cakisma_kontrol(*all)` was called, which, contrary to the
        docstring, scanned THE WHOLE DOCUMENT. Measured
        (LOG/2026-08-27_9564dc71.txt): 44 objects, 946 pairs, the 2 s budget
        ran out, **431 pairs were never measured**, and most of the 38 lines
        returned were hidden cut bases — so the answer asked for was not
        coming, noise was.

        Now `odak=` is used: only the pairs that involve the object in the
        close-up. On the same document 16 pairs, 0.38 s, 2 lines.
        """
        try:
            import FreeCAD as App

            from .execution import olcum

            doc = App.ActiveDocument
            if doc is None:
                return ""
            nesneler = [doc.getObject(a) for a in adlar]
            nesneler = [o for o in nesneler if o is not None]
            if not nesneler:
                return ""
            if len(nesneler) == 1:
                # A single object: the pairs that INVOLVE that object.
                # cakisma_kontrol finds the candidates itself and drops the
                # consumed ones (see kesif.tuketilmis_mi).
                sonuc = olcum.cakisma_kontrol(odak=nesneler[0], yaz=False)
                return sonuc.get("satir", "")
            # Several objects were asked for EXPLICITLY: exactly those are
            # measured, no filtering — the model gets what it asked for.
            sonuc = olcum.cakisma_kontrol(*nesneler, yaz=False)
            return sonuc.get("satir", "")
        except Exception as e:                                   # noqa: BLE001
            log.uyari(f"close-up overlap measurement failed: {e}")
            return ""

    def _gorsel_yerine_cikti(self, cikti: str, sebep: str) -> None:
        """The image could not be sent. THE OUTPUT WAS RIDING ON IT — don't swallow that too.

        MEASURED (LOG/2026-08-24_3ad4cef1.txt, 12:03:26): after a successful
        run NOTHING landed in the log — neither output nor image. The cause
        was the image budget, but the bill went to the output: the output
        RIDES on this call (see blogu_calistir), and when the image path
        returned early, `fill area: 3080 mm2 | overlap: 0.00 mm2` went with
        it. The model got zero feedback about a successful run.

        The suppression is now also written to the LOG. It used to be only
        `mesaj.emit`-ed to the panel; every other suppression path (e.g.
        "AUTO-REPAIR budget exhausted") writes to the log. So anyone
        reviewing the log later could not find a reason for that gap.
        """
        self.gunluk.sistem("IMAGE NOT SENT: " + sebep)
        if not cikti:
            return
        self.gunluk.sistem(f"OUTPUT sent anyway ({len(cikti)} chars)")
        self.gonder(
            "The code you just gave was run; its output is below. The 3D "
            "image you asked for could NOT be sent (" + sebep + "), so do not "
            "talk as if you had looked at it. Continue with the numbers you "
            "have if you can; if you really need to look, ask the user to "
            "describe what you need to see.\n\n"
            f"<execution_result>\n{cikti}\n</execution_result>",
            kullanici_mi=False)

    def _kac_kare(self) -> tuple[bool, str]:
        """Three frames or one — THE HOST DECIDES, not the model.

        WHY IT CHANGED (measured, LOG/2026-08-27_9564dc71.txt). The old rule
        was "three frames if the model says 'GORSEL-KONTROL 3'", i.e. the
        decision was the model's. Result: **27 of 30** image sends were
        three frames (90%), and even AFTER "three frames is not the default"
        was written into the contract the rate stayed at 90%. One system
        prompt line does not beat 40 examples in the model's own context.
        If a rule does not hold, it moves to where it can be enforced.

        The cost was measured: 30 sends, 916 KB, 30 KB per turn on average,
        and it grows as the model gets more complex (22 KB in the first
        half, 47 KB in the second) — roughly a third of the context window.

        The gain was not measured, because there is NONE: in 7 of the 30
        turns with an image, the model found a problem, and in **all seven**
        the evidence was a printed number (bbox, volume, cakisma_kontrol) —
        items like "0.2 mm overhang" are invisible at 4 pixels/mm anyway.
        There is not a single finding the image caught on its own.

        The three-frame allowance is granted in two cases:
          * the last block added a NEW OBJECT — there is something whose
            place in space was never proven, one angle does not settle
            "is it floating"; or
          * this is the second look in a row — the first frame did not
            settle the question.
        If neither holds, one frame is sent and the model is told WHY it
        was one frame; otherwise it repeats the same request.
        """
        istedi = self._gorsel_cok
        yeni_nesne = bool(self._son_eklenen)
        ikinci_bakis = self._gorsel_tur >= 1
        if yeni_nesne or ikinci_bakis:
            return True, ""
        if istedi:
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

    def _gorseli_gonder(self, cikti: str = "") -> None:
        """Captures the 3D view and sends it to the model. Does not stay silent on failure.

        If `cikti` is given it rides on the same message: if the code both
        printed something and an image was requested, there is no point
        spending two turns.
        """
        self._gorsel_bekliyor = False

        # IMAGES OFF (see GORSEL_ACIK). This sits at the very top so it does
        # not pollute any of the counters below; when turned on, the old
        # behaviour comes back as it was.
        #
        # The model may still ask (even without the clause in the contract
        # it can write it out of old habit). So we DO NOT STAY SILENT: the
        # output is sent and it is told "don't talk as if you looked at an
        # image".
        if not GORSEL_ACIK:
            self._gorsel_cok = False
            self._son_eklenen = []
            self._gorsel_yakin = []
            self._gorsel_yerine_cikti(
                cikti, "the image system is off — proceed by measuring")
            return

        # LOOP SAFETY: the model can look at the image and ask for an image
        # again. Two turns are enough; on the third we stop and hand the
        # ball to the user.
        #
        # WHAT THE COUNTER COUNTS. Only looks that come IN A ROW, with no
        # work done in between. It is reset when code runs (see
        # blogu_calistir), because the guard was aimed at "look, then look
        # again", not "look - change - look again". Measured
        # (LOG/2026-08-24_3ad4cef1.txt): Opus looked at 11:46 / 11:53 /
        # 11:58, gave GERI-AL between each look and wrote new code — exactly
        # the loop we want — and was penalised on the fourth because the
        # budget was full.
        if self._gorsel_tur >= _GORSEL_SINIR:
            self.mesaj.emit("sistem",
                            f"The AI asked for a visual check {_GORSEL_SINIR} "
                            "times in a row; stopped. You can describe "
                            "what it should look at.")
            self._gorsel_yerine_cikti(
                cikti, f"requested {_GORSEL_SINIR} times in a row, stopped")
            return

        if not gorunum.yakalanabilir_mi():
            self.mesaj.emit("sistem",
                            "The AI wanted to see the 3D view but there "
                            "is no active 3D window. Open a document and retry.")
            self._gorsel_yerine_cikti(cikti, "no open 3D window")
            return

        cok_aci, kare_notu = self._kac_kare()
        self._gorsel_cok = False
        # The allowance is used ONCE. If we did not clear it, an object added
        # in an earlier turn would keep granting three frames to later looks.
        self._son_eklenen = []
        yakin = list(self._gorsel_yakin)
        self._gorsel_yakin = []

        if yakin:
            # CLOSE-UP. The general frame does not show fine work: on a
            # 201 mm model a 900x640 frame is ~4 pixels/mm, so a 0.6 mm part
            # is 2 pixels (measured, MANTIK 39). The camera moves in on the
            # object.
            kareler = gorunum.yakala_yakin(yakin, cok_aci=cok_aci)
            if not kareler:
                # If we could not zoom in we DO NOT stay silent: we fall back
                # to the normal frame and tell the model (in the prompt text
                # below).
                tek = gorunum.yakala()
                kareler = [tek] if tek else []
                yakin_dustu = True
            else:
                yakin_dustu = False
        elif cok_aci:
            kareler = gorunum.yakala_cok()
            yakin_dustu = False
        else:
            tek = gorunum.yakala()
            kareler = [tek] if tek else []
            yakin_dustu = False

        if not kareler:
            self.mesaj.emit("sistem",
                            "The AI asked for the 3D view but the capture "
                            "failed (details in the Report view).")
            self._gorsel_yerine_cikti(cikti, "the image could not be captured")
            return

        veri = kareler if len(kareler) > 1 else kareler[0]
        bayt = sum(len(k) for k in kareler)
        etiket = (f"{len(kareler)}-angle view" if len(kareler) > 1
                  else "3D view")

        self._gorsel_tur += 1
        yakin_eki = f", CLOSE-UP: {', '.join(yakin)}" if yakin else ""
        self.mesaj.emit("sistem",
                        f"{etiket} sent to AI ({bayt // 1024} KB"
                        f"{yakin_eki}).")
        self.gunluk.sistem(f"GORSEL-KONTROL: {len(kareler)} frame(s) sent "
                           f"({bayt} bytes){yakin_eki}")
        if len(kareler) > 1:
            istem = (f"The 3D images you asked for are attached, from "
                     f"{len(kareler)} angles: 1) the angle the user sees on "
                     f"screen, 2) FRONT view (from -Y), 3) TOP view (from "
                     f"+Z). Look at all three — what one angle hides (whether "
                     f"something floats, whether an alignment is off) shows "
                     f"in the others. Then: if it looks right, confirm in one "
                     f"sentence; if something is wrong, say what and give "
                     f"ONLY the first step of the fix.")
        else:
            istem = ("The 3D image you asked for is attached. Then: if it "
                     "looks right, confirm in one sentence; if something is "
                     "wrong, say what and give ONLY the first step of the "
                     "fix. If one angle is not enough to be sure, do not "
                     "guess: end your reply with GORSEL-KONTROL 3 to look "
                     "from three angles.")
        # If the host reduced three frames to one, we say WHY. Reducing it
        # silently pushes the model to repeat the same request.
        istem += kare_notu

        # IN A CLOSE-UP THE MEASUREMENT GOES TOO. The user's decision: "let
        # it look closely and inspect in detail" + numbers along with the
        # image. The overlap question is not settled by the image anyway
        # (MANTIK 39), so we give the deterministic answer in the same
        # message too — without spending an extra turn.
        if yakin:
            istem = (f"CLOSE-UP: the camera zoomed in on — "
                     f"{', '.join(yakin)}. " + istem)
            if yakin_dustu:
                istem += ("\n\nNOTE: the camera could not zoom in, this frame "
                          "is the GENERAL view (details in the Report view).")
            olcum_metni = self._cakisma_metni(yakin)
            if olcum_metni:
                istem += ("\n\nDETERMINISTIC overlap measurement of the same "
                          "objects (the image cannot settle this, this does):\n"
                          f"<execution_result>\n{olcum_metni}\n"
                          "</execution_result>")
        if cikti:
            istem += (f"\n\nprint() output of the same code:\n"
                      f"<execution_result>\n{cikti[:2000]}\n"
                      f"</execution_result>")
        self.gonder(istem, gorsel=veri, kullanici_mi=False)

    def _bilgi(self, s: TurSonucu, blok_sayisi: int) -> tuple[str, str]:
        """Footer bar text + hint.

        Tokens are shown INSTEAD OF dollars: on a subscription no dollars
        are charged, that figure was only the "if it were done at API
        prices" equivalent and was misread as "I'm spending money". Tokens
        are the resource actually used.
        """
        satir = [f"{s.sure_ms / 1000:.1f} s"]
        if s.model:
            satir.append(s.model)
        satir.append(f"{_kisa_sayi(s.tk_toplam)} token")
        # CONTEXT FILL. The CLI does not report the limit (every field of
        # init and result was scanned), so the model's catalog value is
        # hard-coded - see config.BAGLAM_SINIRI. The used side is a real
        # measurement.
        satir.append(f"{_kisa_sayi(s.tk_baglam)}/{config.baglam_siniri_kisa()} context")
        # We don't write "0 code blocks": noise that carries no information,
        # the user rightly said "what is that, delete it if it's useless".
        # Above zero it is meaningful.
        if blok_sayisi:
            satir.append(f"{blok_sayisi} code block" + ("s" if blok_sayisi > 1 else ""))

        ipucu = [
            "Runs through your Claude Code subscription "
            "(drawn from its monthly Agent SDK credit).",
            "",
            f"Context: {s.tk_baglam:,} / {config.BAGLAM_SINIRI:,} tokens",
            "  (input + cache; output does not count)",
            "  Limit is the model's catalog value - the CLI does not report it.",
            "",
            "This turn:",
            f"  input            {s.tk_girdi:>9,}",
            f"  cache read       {s.tk_onbellek_okuma:>9,}   (cheap)",
            f"  cache write      {s.tk_onbellek_yazma:>9,}",
            f"  output           {s.tk_cikti:>9,}",
            f"  TOTAL            {s.tk_toplam:>9,}",
            "",
            f"This chat so far: {self._tk_toplam:,} tokens / {self._tur_sayisi} turns",
        ]
        if s.maliyet_usd:
            ipucu += ["",
                      f"At API prices this would cost ~${s.maliyet_usd:.3f} -",
                      "covered by your plan's credit until it runs out."]
        if self.gunluk.dosya:
            ipucu += ["", f"Chat log: {self.gunluk.dosya}"]

        log.ayik(" · ".join(satir))
        return " · ".join(satir), "\n".join(ipucu)
