"""Tek bir claude.exe surecinin sahibi.

Neden QThread degil QProcess: QProcess Qt'nin olay dongusunde calisir, yani
`readyReadStandardOutput` DOGRUDAN GUI thread'inde tetiklenir. Worker thread
yok, moveToThread yok, kuyruklu baglanti disiplini yok, widget'a yanlis
thread'den dokunma riski yok. Iptal `kill()`, olum bir sinyal.

"JSON'u GUI thread'inde ayristirmak donmaya yol acar" itirazi bu eklentide
gecersiz: bir mesaj birkac KB, json.loads mikro saniyeler. Burada GUI'yi
gercekten donduran sey doc.recompute() ve o zaten GUI thread'inde olmak
zorunda (OCC tek thread'li).

Bu sinif SOHBET SEMANTIGI BILMEZ — sadece surec + cerceveleme.
"""

from __future__ import annotations

import os

from PySide import QtCore

from .. import log
from .framing import ArtimliSatirOkuyucu, SatirTasmasi

# Windows: konsol penceresi acilmasin. Qt bunu zaten yapiyor ama surumden
# suruma degisebilecek bir varsayima guvenmiyoruz.
CREATE_NO_WINDOW = 0x08000000

STDERR_HALKA = 8192  # son N bayt stderr saklanir (hata raporuna eklenir)


class ClaudeProcess(QtCore.QObject):
    """Bir claude.exe surecini baslatir ve ciktisini satir satir yayinlar."""

    satir = QtCore.Signal(str)          # tam bir stdout satiri (NDJSON)
    basladi = QtCore.Signal()
    bitti = QtCore.Signal(int, str)     # cikisKodu, stderr kuyrugu

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._proc: QtCore.QProcess | None = None
        self._okuyucu = ArtimliSatirOkuyucu()
        self._stderr = b""
        self._kasitli_oldurme = False

    # -- yasam dongusu -----------------------------------------------------

    def calisiyor_mu(self) -> bool:
        return (self._proc is not None
                and self._proc.state() != QtCore.QProcess.NotRunning)

    def baslat(self, exe: str, argv: list[str], cwd: str) -> None:
        if self.calisiyor_mu():
            raise RuntimeError("surec zaten calisiyor")

        self._okuyucu = ArtimliSatirOkuyucu()
        self._stderr = b""
        self._kasitli_oldurme = False

        p = QtCore.QProcess(self)
        p.setProgram(exe)
        p.setArguments(argv)
        p.setWorkingDirectory(cwd)
        p.setProcessEnvironment(self._ortam())

        # Windows'ta konsol parlamasini kesin olarak engelle
        try:
            p.setCreateProcessArgumentsModifier(
                lambda a: setattr(a, "flags", a.flags | CREATE_NO_WINDOW))
        except Exception:
            pass  # Windows disi ya da API yok — Qt varsayilani zaten yeterli

        p.readyReadStandardOutput.connect(self._stdout_geldi)
        p.readyReadStandardError.connect(self._stderr_geldi)
        p.finished.connect(self._surec_bitti)
        p.errorOccurred.connect(self._surec_hatasi)
        p.started.connect(self.basladi.emit)

        self._proc = p
        log.ayik(f"baslatiliyor: {exe} {' '.join(argv)}")
        p.start()

    def girdi_yaz(self, metin: str) -> None:
        if self._proc is None:
            raise RuntimeError("surec yok")
        self._proc.write(metin.encode("utf-8"))

    # NOT: `girdiyi_kapat()` (closeWriteChannel) CIKARILDI. Tek atislik
    # surumden kalmaydi; kalici surecte stdin ACIK kalmak zorunda, cagrilsa
    # sonraki turu bozardi (MANTIK 8d).

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

    # -- ic olaylar --------------------------------------------------------

    def _ortam(self) -> QtCore.QProcessEnvironment:
        o = QtCore.QProcessEnvironment.systemEnvironment()
        # FreeCAD bunlari kendi ortamina enjekte ediyor ve her cocuk surece
        # siziyor. claude.exe icin bugun zararsiz, ama Python'a yakin bir sey
        # calistirdigimiz an ayaga dolanir.
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
        # Yalnizca halkada birikir; surec bitince _bitti()'de kuyruk olarak
        # gonderiliyor. (Eskiden bir de `stderr_metin` sinyali yayiliyordu
        # ama hicbir yere bagli degildi — cikarildi.)
        veri = bytes(self._proc.readAllStandardError())
        self._stderr = (self._stderr + veri)[-STDERR_HALKA:]

    def _surec_hatasi(self, hata) -> None:
        # FailedToStart en sik hata: yol yanlis ya da exe yok
        if hata == QtCore.QProcess.FailedToStart:
            log.hata("claude.exe baslatilamadi (yol yanlis olabilir)")

    def _surec_bitti(self, kod: int, _durum) -> None:
        # Kalan tampon: --output-format json cikisinin sonunda satir sonu
        # olmayabilir, bosalt() olmazsa cevabi tamamen kaybederiz.
        try:
            for s in self._okuyucu.bosalt():
                self.satir.emit(s)
        except Exception as e:
            log.hata(f"tampon bosaltilamadi: {e}")

        kuyruk = self._stderr.decode("utf-8", errors="replace")
        self.bitti.emit(int(kod), kuyruk)
