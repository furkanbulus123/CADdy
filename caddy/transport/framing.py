"""Extracts complete lines from byte chunks.

It prevents two real bugs:

1. **A multi-byte character split across a chunk boundary.** QProcess
   chunks end at arbitrary places. `bytes.decode("utf-8")` fails when it
   sees a character like "ş" cut in half. For a user typing in a language
   with non-ASCII letters this is not a possibility, it is a certainty.
   Fix: a `codecs` incremental decoder — it holds the half character and
   emits it once complete.

2. **Unbounded buffer growth.** If a newline never arrives, memory fills up.
   There is a cap.

The encoding is always UTF-8; `locale.getpreferredencoding()` is NOT used.
The CLI writes to a pipe, so the console code page (e.g. cp1254) never
comes into play.
"""

from __future__ import annotations

import codecs

VARSAYILAN_TAVAN = 32 * 1024 * 1024  # 32 MB


class SatirTasmasi(RuntimeError):
    pass


class ArtimliSatirOkuyucu:
    def __init__(self, tavan: int = VARSAYILAN_TAVAN) -> None:
        self._cozucu = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._tampon = ""
        self._tavan = tavan

    def besle(self, veri: bytes) -> list[str]:
        """Adds bytes, returns the completed lines (empty lines dropped)."""
        if veri:
            self._tampon += self._cozucu.decode(veri)
        if len(self._tampon) > self._tavan:
            self._tampon = ""
            raise SatirTasmasi(
                f"line exceeded {self._tavan} bytes — the stream may be corrupt")
        if "\n" not in self._tampon:
            return []
        *satirlar, self._tampon = self._tampon.split("\n")
        return [s for s in (x.strip() for x in satirlar) if s]

    def bosalt(self) -> list[str]:
        """Stream ended: return what is left in the buffer (even without a newline).

        `--output-format json` output is a single JSON object and may have
        NO trailing newline; so this must always be called at the end.
        """
        kalan = self._cozucu.decode(b"", final=True)
        metin = (self._tampon + kalan).strip()
        self._tampon = ""
        return [metin] if metin else []
