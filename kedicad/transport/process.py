"""Owner of a single claude.exe process.

Why QProcess and not QThread: QProcess runs on Qt's event loop, so
`readyReadStandardOutput` fires DIRECTLY on the GUI thread. No worker thread,
no moveToThread, no queued-connection discipline, no risk of touching a
widget from the wrong thread. Cancel is `kill()`, death is a signal.

The objection "parsing JSON on the GUI thread causes freezes" does not apply
here: a message is a few KB, json.loads takes microseconds. What really
freezes the GUI is doc.recompute(), and that has to run on the GUI thread
anyway (OCC is single-threaded).

This class knows NOTHING about chat semantics — only process + framing.
"""

from __future__ import annotations

import os

from PySide import QtCore

from .. import log
from .framing import ArtimliSatirOkuyucu, SatirTasmasi

# Windows: no console window. Qt already does this, but we do not rely on a
# default that could change between versions.
CREATE_NO_WINDOW = 0x08000000

STDERR_HALKA = 8192  # keep the last N bytes of stderr (added to error reports)


class ClaudeProcess(QtCore.QObject):
    """Starts a claude.exe process and emits its output line by line."""

    satir = QtCore.Signal(str)          # one complete stdout line (NDJSON)
    basladi = QtCore.Signal()
    bitti = QtCore.Signal(int, str)     # exit code, stderr tail

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._proc: QtCore.QProcess | None = None
        self._okuyucu = ArtimliSatirOkuyucu()
        self._stderr = b""
        self._kasitli_oldurme = False

    # -- lifecycle ---------------------------------------------------------

    def calisiyor_mu(self) -> bool:
        return (self._proc is not None
                and self._proc.state() != QtCore.QProcess.NotRunning)

    def baslat(self, exe: str, argv: list[str], cwd: str) -> None:
        if self.calisiyor_mu():
            raise RuntimeError("process already running")

        self._okuyucu = ArtimliSatirOkuyucu()
        self._stderr = b""
        self._kasitli_oldurme = False

        p = QtCore.QProcess(self)
        p.setProgram(exe)
        p.setArguments(argv)
        p.setWorkingDirectory(cwd)
        p.setProcessEnvironment(self._ortam())

        # Make sure no console window flashes on Windows
        try:
            p.setCreateProcessArgumentsModifier(
                lambda a: setattr(a, "flags", a.flags | CREATE_NO_WINDOW))
        except Exception:
            pass  # not Windows or no API — the Qt default is enough

        p.readyReadStandardOutput.connect(self._stdout_geldi)
        p.readyReadStandardError.connect(self._stderr_geldi)
        p.finished.connect(self._surec_bitti)
        p.errorOccurred.connect(self._surec_hatasi)
        p.started.connect(self.basladi.emit)

        self._proc = p
        log.ayik(f"starting: {exe} {' '.join(argv)}")
        p.start()

    def girdi_yaz(self, metin: str) -> None:
        if self._proc is None:
            raise RuntimeError("no process")
        self._proc.write(metin.encode("utf-8"))

    # NOTE: `girdiyi_kapat()` (closeWriteChannel) was REMOVED. It was left
    # over from the one-shot version; with a persistent process stdin has to
    # stay OPEN, and calling it would break the next turn.

    def oldur(self) -> None:
        if not self.calisiyor_mu():
            return
        self._kasitli_oldurme = True
        self._proc.terminate()
        if not self._proc.waitForFinished(2000):
            self._proc.kill()
            self._proc.waitForFinished(2000)

    def kasitli_olduruldu_mu(self) -> bool:
        return self._kasitli_oldurme

    # -- internal events ---------------------------------------------------

    def _ortam(self) -> QtCore.QProcessEnvironment:
        o = QtCore.QProcessEnvironment.systemEnvironment()
        # FreeCAD injects these into its own environment and they leak into
        # every child process. Harmless for claude.exe today, but they get in
        # the way the moment we run anything Python-related.
        for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
            o.remove(k)
        o.insert("PYTHONIOENCODING", "utf-8")
        return o

    def _stdout_geldi(self) -> None:
        if self._proc is None:
            return
        veri = bytes(self._proc.readAllStandardOutput())
        try:
            for s in self._okuyucu.besle(veri):
                self.satir.emit(s)
        except SatirTasmasi as e:
            log.hata(str(e))
            self.oldur()

    def _stderr_geldi(self) -> None:
        if self._proc is None:
            return
        # Only accumulates in the ring; sent as the tail in _bitti() once the
        # process ends. (There used to be a `stderr_metin` signal too, but
        # nothing was connected to it — removed.)
        veri = bytes(self._proc.readAllStandardError())
        self._stderr = (self._stderr + veri)[-STDERR_HALKA:]

    def _surec_hatasi(self, hata) -> None:
        # FailedToStart is the most common error: wrong path or no exe
        if hata == QtCore.QProcess.FailedToStart:
            log.hata("claude.exe failed to start (the path may be wrong)")

    def _surec_bitti(self, kod: int, _durum) -> None:
        # Remaining buffer: --output-format json output may lack a trailing
        # newline; without bosalt() we would lose the whole reply.
        try:
            for s in self._okuyucu.bosalt():
                self.satir.emit(s)
        except Exception as e:
            log.hata(f"could not flush buffer: {e}")

        kuyruk = self._stderr.decode("utf-8", errors="replace")
        self.bitti.emit(int(kod), kuyruk)
