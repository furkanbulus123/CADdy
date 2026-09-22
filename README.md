# CADdy

**An AI assistant that lives inside FreeCAD — and measures its work instead of guessing.**

<!-- DEMO VIDEO: drag the .mp4 into this line on GitHub's editor -->
![CADdy demo](docs/demo.gif)

You draw. You ask. CADdy continues on the same live document. You keep going.
Nothing is exported, nothing is lost, and every AI step is one `Ctrl+Z` away.

---

## Why CADdy

- **Verified, not eyeballed.** After every change CADdy checks the geometry:
  overlapping parts, open shells, invalid solids, volumes. An AI looking at a
  screenshot says "looks fine" — CADdy measures.
- **One live document.** Hand-made and AI-made features sit in the same model
  tree and stay parametric. Edit either one, any time.
- **One step, one undo.** However many objects an AI turn creates, a single
  `Ctrl+Z` rolls it back.
- **No API key.** Runs on your existing Claude subscription through the Claude
  Code CLI.

![Screenshot](docs/screenshot.png)

## Requirements

- Windows 10 / 11
- [FreeCAD 1.1](https://www.freecad.org/downloads.php) (1.0 and older will not work)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code), signed in with a Claude Pro or Max plan

> Do **not** set `ANTHROPIC_API_KEY`. If it is set, the CLI bills API credits
> instead of using your subscription.

## Install

```powershell
git clone https://github.com/furkanbulus123/CADdy.git
cd CADdy
.\kurulum.ps1
```

The script finds FreeCAD, checks the `claude` command and links the folder into
FreeCAD's `Mod` directory. No admin rights needed. Restart FreeCAD and pick
**CADdy** from the workbench list.

## Usage

Open the CADdy panel and describe what you want:

> *"Add four M3 mounting holes, 5 mm from each corner."*

![Example](docs/example.png)

| Button | What it does |
|---|---|
| **Yeni** (New) | Start a fresh conversation |
| **Geri al / İleri al** (Undo / Redo) | Step through AI changes |
| **Model** | Opus or Sonnet |
| **Hızlı / Derin** (Effort) | Fast or deep thinking |

## Tests

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" tests\test_yukleme_fc.py
```

## License

[MIT](LICENSE)
