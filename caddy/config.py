"""Ayarlar — FreeCAD'in kendi parametre deposunda saklanir.

FreeCAD ayarlari `App.ParamGet(...)` ile okunur/yazilir ve user.cfg'de kalicidir;
ayri bir ayar dosyasi uydurmuyoruz. Anahtarlar:

    Model            "opus" | "sonnet"              panelden secilir, bkz. MODELLER
    Efor             "" | "low"                     dusunme miktari, bkz. EFORLAR
    Timeout          saniye — TOPLAM sure degil, SESSIZLIK suresi (bkz. asagi)
    Debug            ayrintili gunluk
    ClaudeExe        elle verilen claude.exe yolu (bos = otomatik bul)
    MaxBudgetUsd     0 = sinirsiz; >0 ise --max-budget-usd olarak gecer
    PanelYuzde       panel ilk acilista ana pencerenin yuzde kaci (bkz. asagi)

CIKARILDI — `AutoRun`. Aciklamasi "guard temizse onay beklemeden calistir"
idi ve DAYANDIGI GUARD HIC YAZILMADI (MANTIK 6, ucuncu katman). Yani ayar
acilsaydi hicbir sey denetlemeden kod calisirdi. Okuyanda var olmayan bir
emniyet duygusu birakiyordu; guard yazilirsa ayar da geri gelir.
"""

from __future__ import annotations

import os
from pathlib import Path

YOL = "User parameter:BaseApp/Preferences/Mod/CADdy"

VARSAYILAN = {
    "Model": "opus",
    # Dusunme miktari. Bos = CLI varsayilani (olculen en yavas seviye).
    # Varsayilani DEGISTIRMIYORUZ: hiz kazanci olculdu, KALITE kaybi
    # olculmedi. Kullanici panelden secer; olcum gelince varsayilan
    # yeniden tartisilir. Bkz. EFORLAR.
    "Efor": "",
    # SESSIZLIK siniri, toplam sure DEGIL. Olculdu: zor bir istekte model
    # 131 sn dusunup 166 sn'de bitirdi — toplam sureye bakan 180 sn'lik bir
    # saat bunu kil payi kacirmis, biraz daha zorunda calisan bir yaniti
    # kesip "iptal edildi" diye raporlayacakti. CLI ise dusunurken ~1.5 sn'de
    # bir nabiz atiyor (system/thinking_tokens), en uzun gozlenen bosluk
    # 4.3 sn. Yani 90 sn sessizlik = surec gercekten olmus demektir.
    "Timeout": 90,
    "Debug": False,
    "ClaudeExe": "",
    "MaxBudgetUsd": 0.0,
    # Panel ilk acilista ne kadar yer kaplar. Kullanicinin sikayeti:
    # "caddy ekranin yuzde 60'ini kapsiyor, %40 olsun, %60 model gozuksun".
    # Olculdu: panel Qt'nin verdigi kadar genisti cunku ASGARI genisligi
    # 888 px idi (ust satirdaki uzun dugme etiketleri) ve daha dar
    # olamiyordu. Once o taban dusuruldu, sonra bu oran uygulanabildi.
    "PanelYuzde": 40,
}


def _p():
    import FreeCAD as App

    return App.ParamGet(YOL)


def metin(anahtar: str) -> str:
    try:
        return _p().GetString(anahtar, VARSAYILAN[anahtar])
    except Exception:
        return VARSAYILAN[anahtar]


def sayi(anahtar: str) -> int:
    try:
        return _p().GetInt(anahtar, VARSAYILAN[anahtar])
    except Exception:
        return VARSAYILAN[anahtar]


def ondalik(anahtar: str) -> float:
    try:
        return _p().GetFloat(anahtar, VARSAYILAN[anahtar])
    except Exception:
        return VARSAYILAN[anahtar]


def bayrak(anahtar: str) -> bool:
    try:
        return _p().GetBool(anahtar, VARSAYILAN[anahtar])
    except Exception:
        return VARSAYILAN[anahtar]


def yaz(anahtar: str, deger) -> None:
    p = _p()
    if isinstance(deger, bool):
        p.SetBool(anahtar, deger)
    elif isinstance(deger, int):
        p.SetInt(anahtar, deger)
    elif isinstance(deger, float):
        p.SetFloat(anahtar, deger)
    else:
        p.SetString(anahtar, str(deger))


# --- kisayollar -----------------------------------------------------------

# Panelde secilebilen modeller: (deger, etiket, ipucu)
#
# Olculdu (ayni istem, CADdy'nin gercek argv'si ile):
#
#   model   istek   toplam sure          dusunce   kod blogu
#   opus    basit    8.1 sn                    0   var
#   sonnet  basit   11.8 sn                    0   var
#   opus    zor     77 / 167 / 183 sn   3.6k-12k   var
#   sonnet  zor     21.9 sn                  750   YOK
#   sonnet  zor    108 sn                    7.4k   var
#
# Iki sonuc, ikisi de arayuze dogrudan yansiyor:
#  1) Basit iste sonnet DAHA HIZLI DEGIL - opus zaten dusunmuyor. Yani
#     "hizli mod" her zaman kazandiran bir dugme degil, oyle etiketlenmemeli.
#  2) Sonnet zor iste hizli bittiginde kodu hic vermedi. Hiz, guvenilirlik
#     karsiligi aliniyor. Bu ipucu balonunda ACIKCA yaziyor.
#
# Sureyi belirleyen asil sey model degil, modelin ne kadar dusunmeye karar
# verdigi; o da ISTEGIN BUYUKLUGUNE bagli. Ayni belge, ayni model (opus):
#
#   "kulbun karsisina kedi kafasi logosu ekle"      77 / 95 / 157 / 167 / 183 sn
#   "kulbun karsisina 20 mm capinda 3 mm disk ekle"      54.4 / 55.7 sn
#
# Yani istegi bolmek hem ~3 kat hizlandiriyor hem de sureyi ONGORULEBILIR
# kiliyor (belirsiz istekte 77-183 arasi zipliyor). Panel bu yuzden bekleyis
# uzayinca kullaniciya istegi bolmeyi oneriyor (dock._OGUT) - bu, "hizli mod"
# dugmesinden daha buyuk bir kazanc.
# Dizilim: (deger, KISA etiket, TAM etiket, ipucu).
#
# Kisa etiket neden var: bu kutu panelin ust satirindaydi ve tek basina
# 270 px asgari genislik dayatiyordu (olculdu). Ust satir da panelin
# asgari genisligini belirledigi icin "paneli daralt" istegi bu yuzden
# imkansizdi. Tam etiket kaybolmuyor — ipucunun ilk satiri.
MODELLER = [
    ("opus", "Opus", "Opus (iyi kalite)",
     "Zor istekleri dogru cozer. Olculdu (2026-08-24, ayni tavsan): tur "
     "basina ortalama 87.5 sn ve Sonnet'ten %35 DAHA UCUZ — daha az turda "
     "bitirdigi icin. Isi tamamlayan oturum bu oldu."),
    ("sonnet", "Sonnet", "Sonnet (orta kalite)",
     "Tur basina ortalama 49.1 sn. Olculdu: cikti hizi Opus'unkiyle ayni "
     "(78 vs 72 token/sn) — fark hizda degil, Opus'un iki kat uzun "
     "dusunmesinde. Ayni iste kullanicidan onay alamadi."),
]

# DUSUNME MIKTARI — gecikmenin asil kaynagi. Olculdu (2026-08-24, iki gercek
# oturumun 22 turu):
#
#   * Cikti hizi SABIT: Sonnet ortanca 78.5, Opus 72.5 token/sn.
#   * Baglam gecikmeyi BELIRLEMIYOR: 93k baglam + 92 cikti = 3.9 sn;
#     15k baglam + 2486 cikti = 36.8 sn. Prompt cache calisiyor.
#   * Cikti token'inin %91-94'u DUSUNME (gorunur metin gunlukten sayildi):
#     Sonnet 482 sn dusunme / 32 sn yazma, Opus 756 / 74.
#
# Yani gecikme ~= cikti / 75, ve o ciktinin onda dokuzu dusunme. CLI'in
# `--effort` bayragi tam bunu ayarliyor. Ayni istem, 3 tekrar (sonnet):
#
#   (varsayilan)  109 · 126 · 116 sn   ortanca 116.1   9820 cikti token
#   low            37 ·  43 ·  37 sn   ortanca  37.0   2774 cikti token
#
# CIKARILDI — "high". Ilk tek ornekte 48 sn cikmis ve "dengeli orta secenek"
# diye yazilmisti; tekrarli olcum bunu CURUTTU:
#
#   low            37 ·  43 ·  37 sn   ortanca  37.0    2774 cikti
#   (varsayilan)  109 · 126 · 116 sn   ortanca 116.1    9820 cikti
#   high          123 · 130 · 149 sn   ortanca 129.6   11408 cikti
#
# high varsayilandan DAHA YAVAS (0.9x). Ortada bir secenek yok; tablo iki
# uclu. Tek ornekle secenek yazmanin bedeli buydu.
#
# Opus'ta da gecerli: varsayilan 87.0 sn -> low 44.4 sn (2.0x).
#
# DIKKAT — KALITE OLCULMEDI. Bu testte sistem sozlesmesi ve CLAUDE.md yoktu;
# gercek oturumda model cok daha fazla kurali tartiyor. "low daha iyi"
# denmiyor, "dusunme miktari ayarlanabilir" deniyor. Secim kullanicinin.
EFORLAR = [
    ("low", "Hızlı", "Hızlı (az düşünür)",
     "Olculdu, 3 tekrar: 116.1 sn -> 37.0 sn, yani 3.1 kat (opus'ta 2.0 "
     "kat). Olcum, kesif, tek satirlik degisiklik gibi kararsiz islerde "
     "yeter. KALITE FARKI OLCULMEDI — neyi kaybettigini bilmiyoruz."),
    ("", "Derin", "Derin (CLI varsayilani)",
     "Bayrak hic gecilmez. Olculen ortanca 116.1 sn. 'Tavsanin sirti hic "
     "cizilmemis' gibi teshisleri satin aldigin yer burasi. NOT: --effort "
     "high denendi ve bundan da YAVAS cikti (129.6 sn), o yuzden listede "
     "yok."),
]

# Baglam penceresi. CLI BUNU BILDIRMIYOR - init ve result satirlarinin
# butun alanlari tarandi, limit hicbirinde yok. O yuzden modelin katalog
# degeri buraya sabit yaziliyor ve panelde "sinir katalog degeri" diye
# isaretleniyor; uydurma bir kesinlik vermeyelim.
# Opus 5 ve Sonnet 5: 1M token.
BAGLAM_SINIRI = 1_000_000


def baglam_siniri_kisa() -> str:
    n = BAGLAM_SINIRI
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    return f"{n // 1_000}k"


def model() -> str:
    d = metin("Model") or VARSAYILAN["Model"]
    return d if d in [m[0] for m in MODELLER] else VARSAYILAN["Model"]


def modeli_ayarla(ad: str) -> None:
    yaz("Model", ad)


def efor() -> str:
    """Dusunme miktari. Bos dize = bayrak hic gecilmez (CLI varsayilani).

    Bos dize GECERLI bir deger — o yuzden `metin()` yerine dogrudan
    okunuyor ve gecerlilik listeye bakarak denetleniyor.
    """
    try:
        d = _p().GetString("Efor", VARSAYILAN["Efor"])
    except Exception:
        d = VARSAYILAN["Efor"]
    return d if d in [e[0] for e in EFORLAR] else VARSAYILAN["Efor"]


def eforu_ayarla(ad: str) -> None:
    yaz("Efor", ad)


def zaman_asimi() -> int:
    """Kac saniye SESSIZLIKTEN sonra surec olu sayilir.

    Toplam sure siniri bilerek YOK: modelin ne kadar dusunecegini onceden
    bilemeyiz ve uzun dusunmek hata degil.
    """
    d = sayi("Timeout")
    return d if d > 0 else VARSAYILAN["Timeout"]


def ayikla_acik() -> bool:
    return bayrak("Debug")


def panel_yuzde() -> int:
    """Panelin ana penceredeki payi. Sacma degerler varsayilana duser."""
    d = sayi("PanelYuzde")
    return d if 10 <= d <= 90 else VARSAYILAN["PanelYuzde"]


def butce_usd() -> float:
    return ondalik("MaxBudgetUsd")


# --- yollar ---------------------------------------------------------------

def eklenti_dizini() -> Path:
    """Bu paketin bir ustu, yani eklenti kok dizini."""
    return Path(__file__).resolve().parent.parent


def calisma_dizini() -> Path:
    """claude.exe'nin cwd'si.

    Neden ayri bir klasor: CLI, calistigi dizindeki CLAUDE.md'yi otomatik
    yukler. Oraya FreeCAD API kilavuzunu koyuyoruz ki her turda tekrar
    gondermek zorunda kalmayalim (ustelik onbellege giriyor).
    """
    d = eklenti_dizini() / "workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d


def yedek_dizini() -> Path:
    """Ilk AI degisikliginden onceki belge kopyalari (bkz. executor._yedek_al).

    MANTIK 6'nin ikinci katmani. Uzun bir seansta hasar birikebiliyor ve
    Ctrl+Z yigini o kadar geriye yetmeyebiliyor; bu klasordeki kopya son
    caredir.
    """
    d = eklenti_dizini() / ".caddy-backups"
    d.mkdir(parents=True, exist_ok=True)
    return d
