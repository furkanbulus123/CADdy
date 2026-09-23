# Architecture

CADdy is a pure-Python FreeCAD 1.1 addon. The panel talks to the Claude Code
CLI; code the model writes runs inside the live FreeCAD document.

```
InitGui.py  ->  caddy/ui/dock.py  ->  caddy/conversation.py
                                         |-> caddy/transport/   (claude.exe, stream-json)
                                         |-> caddy/execution/   (run, verify, measure)
                                         '-> caddy/context/     (document -> text)
```

**Layer rule:** only `caddy/ui/` imports QtWidgets. `execution/` and
`context/` use only the FreeCAD API, so they are tested headless with
`freecadcmd`.

## Key decisions

- **One AI turn = one undo step.** `executor.py` wraps each code block in a
  persistent FreeCAD transaction; an exception aborts it, so the document is
  never half-modified.
- **Verify by measurement, not by looking.** After every run `dogrulama.py`
  checks the touched objects: valid topology, per-solid volume sign (catches
  inside-out solids that `isValid()` accepts), closed shells, mesh
  printability, and overlaps between parts. Screenshots are only used where
  measurement cannot answer.
- **Measurement helpers in the model's namespace** (`olcum.py`, `islem.py`,
  `kesif.py`): `cakisma_kontrol`, `olc`, `mesafe`, `saglik`, `simetri`,
  `kesif`, `mesh_onar`, `birlestir`... They wrap FreeCAD/OCC calls the model
  used to write by hand.
- **Honest reports.** A check that did not run is listed as NOT RUN, never
  counted as passed.
- **Your own edits are safe.** The panel's Undo refuses to undo a change that
  is not the AI's.
- **Backups.** Before the first AI change in a document a copy is saved to
  `.caddy-backups/`.

## Tests

`tests/test_*_fc.py` run headless:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" tests\test_dogrulama_fc.py
```

Each suite writes `tests/_son_<name>.txt` with a pass/fail summary.
