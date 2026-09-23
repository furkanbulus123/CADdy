"""Settings — stored in FreeCAD's own parameter store.

FreeCAD settings are read/written with `App.ParamGet(...)` and persist in
user.cfg; we do not invent a separate settings file. Keys:

    Model            "opus" | "sonnet"              chosen in the panel, see MODELLER
    Efor             "" | "low"                     amount of thinking, see EFORLAR
    Timeout          seconds — NOT total time, SILENCE time (see below)
    Debug            verbose logging
    ClaudeExe        claude.exe path set by hand (empty = find automatically)
    MaxBudgetUsd     0 = unlimited; >0 is passed as --max-budget-usd
    PanelYuzde       panel width on first open, as % of the main window (see below)

REMOVED — `AutoRun`. Its description was "run without confirmation if the
guard is clean", and the GUARD IT RELIED ON WAS NEVER WRITTEN. So turning
it on would have run code with no check at all. It left the reader with a
sense of safety that did not exist; if the guard is ever written, the
setting comes back.
"""

from __future__ import annotations

import os
from pathlib import Path

YOL = "User parameter:BaseApp/Preferences/Mod/CADdy"

VARSAYILAN = {
    "Model": "opus",
    # Amount of thinking. Empty = CLI default (the slowest level measured).
    # We do NOT change the default: the speed gain was measured, the
    # QUALITY loss was not. The user picks it in the panel; once quality is
    # measured the default can be revisited. See EFORLAR.
    "Efor": "",
    # A SILENCE limit, NOT total time. Measured: on a hard request the model
    # thought for 131 s and finished at 166 s — a 180 s clock on total time
    # barely missed it and would have cut a slightly harder reply and
    # reported it as "cancelled". The CLI sends a heartbeat roughly every
    # 1.5 s while thinking (system/thinking_tokens); the longest gap seen
    # was 4.3 s. So 90 s of silence means the process really is dead.
    "Timeout": 90,
    "Debug": False,
    "ClaudeExe": "",
    "MaxBudgetUsd": 0.0,
    # How much room the panel takes on first open. User feedback: "caddy
    # covers 60% of the screen, make it 40% so 60% shows the model".
    # Measured: the panel was as wide as Qt gave it because its MINIMUM
    # width was 888 px (long button labels in the top row) and it could not
    # get narrower. That floor was lowered first, then this ratio could apply.
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


# --- shortcuts ------------------------------------------------------------

# Models selectable in the panel: (value, label, tooltip)
#
# Measured (same prompt, with CADdy's real argv):
#
#   model   request  total time          thinking  code block
#   opus    simple    8.1 s                     0   yes
#   sonnet  simple   11.8 s                     0   yes
#   opus    hard     77 / 167 / 183 s    3.6k-12k   yes
#   sonnet  hard     21.9 s                   750   NO
#   sonnet  hard    108 s                    7.4k   yes
#
# Two results, both reflected directly in the UI:
#  1) On a simple task sonnet is NOT FASTER - opus does not think there
#     anyway. So a "fast mode" is not a button that always wins, and must
#     not be labelled as one.
#  2) When sonnet finished a hard task quickly, it gave no code at all.
#     Speed is paid for with reliability. The tooltip says this PLAINLY.
#
# What really sets the time is not the model but how much the model decides
# to think, and that depends on the SIZE OF THE REQUEST. Same document, same
# model (opus):
#
#   "add a cat-head logo opposite the handle"             77 / 95 / 157 / 167 / 183 s
#   "add a 20 mm diameter, 3 mm disk opposite the handle"      54.4 / 55.7 s
#
# So splitting the request makes it ~3x faster AND makes the time
# PREDICTABLE (a vague request jumps between 77 and 183). That is why the
# panel suggests splitting the request once the wait gets long (dock._OGUT)
# - a bigger win than a "fast mode" button.
# Layout: (value, SHORT label, FULL label, tooltip).
#
# Why a short label: this box sat in the panel's top row and alone forced
# a 270 px minimum width (measured). The top row set the panel's minimum
# width, so the "make the panel narrower" request was impossible because of
# it. The full label is not lost — it is the tooltip's first line.
MODELLER = [
    ("opus", "Opus", "Opus (higher quality)",
     "Solves hard requests correctly. Measured: 87.5 s per turn on "
     "average and 35% CHEAPER than Sonnet on the same task — it needs "
     "fewer turns. This was the session that finished the job."),
    ("sonnet", "Sonnet", "Sonnet (medium quality)",
     "49.1 s per turn on average. Measured: same output speed as Opus "
     "(78 vs 72 tokens/s) — the difference is Opus thinking twice as "
     "long. On the same task it did not get the user's approval."),
]

# AMOUNT OF THINKING — the real source of latency. Measured (22 turns of two
# real sessions):
#
#   * Output speed is CONSTANT: Sonnet median 78.5, Opus 72.5 tokens/s.
#   * Context does NOT set the latency: 93k context + 92 output = 3.9 s;
#     15k context + 2486 output = 36.8 s. The prompt cache works.
#   * 91-94% of output tokens are THINKING (visible text counted from logs):
#     Sonnet 482 s thinking / 32 s writing, Opus 756 / 74.
#
# So latency ~= output / 75, and nine tenths of that output is thinking. The
# CLI's `--effort` flag controls exactly this. Same prompt, 3 runs (sonnet):
#
#   (default)     109 · 126 · 116 s    median 116.1   9820 output tokens
#   low            37 ·  43 ·  37 s    median  37.0   2774 output tokens
#
# REMOVED — "high". A first single sample came out at 48 s and it was
# written up as "a balanced middle option"; repeated measurement DISPROVED it:
#
#   low            37 ·  43 ·  37 s    median  37.0    2774 output
#   (default)     109 · 126 · 116 s    median 116.1    9820 output
#   high          123 · 130 · 149 s    median 129.6   11408 output
#
# high is SLOWER than the default (0.9x). There is no middle option; the
# table has two ends. That was the price of writing an option from one sample.
#
# Same on Opus: default 87.0 s -> low 44.4 s (2.0x).
#
# CAREFUL — QUALITY WAS NOT MEASURED. This test had no system contract and
# no CLAUDE.md; in a real session the model weighs many more rules. We are
# not saying "low is better", we are saying "thinking is adjustable". The
# choice is the user's.
EFORLAR = [
    ("low", "Fast", "Fast (thinks less)",
     "Measured, 3 runs: 116.1 s -> 37.0 s, i.e. 3.1x (2.0x on Opus). "
     "Good enough for measuring, inspecting, one-line changes. QUALITY "
     "DIFFERENCE NOT MEASURED — what you lose is unknown."),
    ("", "Deep", "Deep (CLI default)",
     "No flag passed. Measured median 116.1 s. This is where you pay for "
     "subtle diagnoses. NOTE: --effort high was tried and was even SLOWER "
     "(129.6 s), so it is not listed."),
]

# Context window. The CLI DOES NOT REPORT IT - every field of the init and
# result lines was checked, the limit is in none of them. So the model's
# catalog value is hard-coded here and marked in the panel as "limit is the
# catalog value"; let us not fake precision.
# Opus 5 and Sonnet 5: 1M tokens.
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
    """Amount of thinking. Empty string = no flag passed (CLI default).

    The empty string is a VALID value — so it is read directly instead of
    through `metin()`, and validity is checked against the list.
    """
    try:
        d = _p().GetString("Efor", VARSAYILAN["Efor"])
    except Exception:
        d = VARSAYILAN["Efor"]
    return d if d in [e[0] for e in EFORLAR] else VARSAYILAN["Efor"]


def eforu_ayarla(ad: str) -> None:
    yaz("Efor", ad)


def zaman_asimi() -> int:
    """After how many seconds of SILENCE the process counts as dead.

    There is deliberately NO total-time limit: we cannot know in advance how
    long the model will think, and thinking long is not an error.
    """
    d = sayi("Timeout")
    return d if d > 0 else VARSAYILAN["Timeout"]


def ayikla_acik() -> bool:
    return bayrak("Debug")


def panel_yuzde() -> int:
    """The panel's share of the main window. Nonsense values fall back to the default."""
    d = sayi("PanelYuzde")
    return d if 10 <= d <= 90 else VARSAYILAN["PanelYuzde"]


def butce_usd() -> float:
    return ondalik("MaxBudgetUsd")


# --- paths ----------------------------------------------------------------

def eklenti_dizini() -> Path:
    """One level above this package, i.e. the addon root directory."""
    return Path(__file__).resolve().parent.parent


def calisma_dizini() -> Path:
    """claude.exe's cwd.

    Why a separate folder: the CLI automatically loads CLAUDE.md from its
    working directory. We put the FreeCAD API guide there so we do not have
    to send it every turn (and it gets cached).
    """
    d = eklenti_dizini() / "workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d


def yedek_dizini() -> Path:
    """Copies of the document from before the first AI change (see executor._yedek_al).

    The second safety layer. Damage can pile up over a long session and the
    Ctrl+Z stack may not reach back far enough; the copy in this folder is
    the last resort.
    """
    d = eklenti_dizini() / ".caddy-backups"
    d.mkdir(parents=True, exist_ok=True)
    return d
