"""Bayt parcalarindan tam satirlar cikarir.

Iki gercek hatayi onluyor:

1. **Coklu bayt karakterin parca sinirinda bolunmesi.** QProcess'in verdigi
   chunk'lar rastgele yerlerde biter. `bytes.decode("utf-8")` tam ortasindan
   bolunmus bir "ş" gorunce patlar. Turkce yazan bir kullanicida bu bir
   ihtimal degil, kesinlik. Cozum: `codecs` artimli cozucu — yarim karakteri
   kendi icinde tutar, tamamlaninca verir.

2. **Sinirsiz tampon buyumesi.** Satir sonu hic gelmezse bellek dolar.
   Tavan konuldu.

Kodlama her zaman UTF-8'dir; `locale.getpreferredencoding()` KULLANILMAZ.
CLI bir boruya (pipe) yazdigi icin konsol kod sayfasi (bu makinede cp1254)
devreye girmez.
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
        """Bayt ekler, tamamlanmis satirlari dondurur (bos satirlar atilir)."""
        if veri:
            self._tampon += self._cozucu.decode(veri)
        if len(self._tampon) > self._tavan:
            self._tampon = ""
            raise SatirTasmasi(
                f"satir {self._tavan} baytu asti — bozuk akis olabilir")
        if "\n" not in self._tampon:
            return []
        *satirlar, self._tampon = self._tampon.split("\n")
        return [s for s in (x.strip() for x in satirlar) if s]

    def bosalt(self) -> list[str]:
        """Akis bitti: tamponda kalani (satir sonu gelmemis olsa da) ver.

        `--output-format json` cikisi tek bir JSON nesnesidir ve sonunda satir
        sonu OLMAYABILIR; bu yuzden bitiste mutlaka cagrilmali.
        """
        kalan = self._cozucu.decode(b"", final=True)
        metin = (self._tampon + kalan).strip()
        self._tampon = ""
        return [metin] if metin else []
