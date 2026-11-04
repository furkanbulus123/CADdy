# Contributing to CADdy

Thanks for your interest! Bug reports, ideas and pull requests are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on
  the approach.
- Issues labelled [`good first issue`](https://github.com/furkanbulus123/CADdy/labels/good%20first%20issue)
  are a good place to begin.
- [ARCHITECTURE.md](ARCHITECTURE.md) explains how the pieces fit together.

## Running the tests

The tests run headless with FreeCAD's own Python (`freecadcmd`). Each suite
writes its report to `tests/_son_*.txt`, because `print` output is lost inside
`freecadcmd`.

```powershell
$fc = "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe"   # or %LOCALAPPDATA%\Programs\FreeCAD 1.1
Get-ChildItem tests\test_*_fc.py | ForEach-Object { & $fc $_.FullName }
Get-Content tests\_son_*.txt | Select-String "BASARISIZ|basarisiz"
```

Please make sure every suite reports 0 failures before opening a pull request.

## A few rules

- **Only `caddy/ui/` imports `QtWidgets`.** Everything else must run headless,
  so it can be tested with `freecadcmd`.
- **Keep the model honest.** A check that did not run is reported as
  `NOT RUN`, never silently skipped; a value that could not be measured is
  never guessed.
- **Keep behaviour unchanged** in refactors and translations, and add a test
  for any bug you fix.
- `install.ps1` must stay pure ASCII (Windows PowerShell 5.1 reads it in the
  ANSI code page).

## Pull requests

Keep them small and focused, describe what changed and why, and mention how
you tested it (which suites, and anything you checked by hand in FreeCAD).
