# AGENTS.md

Tandem is a fork of StarPilot (which sits on openpilot). Its UI design language is **Essentials**. These rules hold for any change in this repo.

This is `development`: Tandem being ported onto StarPilot 7 (upstream's `testing` branch, which replaced `Dom`), where the code lives under `openpilot/`. `openpilot/selfdrive/ui/tandem/PORTING.md` has the stages and what's ported so far. Until the port is done, `release` stays on StarPilot 6.

## Keep unowned code untouched

Everything outside Tandem's own files belongs to StarPilot or openpilot and changes with every upstream merge. The less of it we edit, the easier merges are.

- **Ours:** `openpilot/selfdrive/ui/tandem/` (code, `design/`, `tools/`, `tests/`, `PORTING.md`), `openpilot/starpilot/tandem/`, the Figtree, JetBrains Mono and NotoSans-Fallback font files (and `NotoSans-OFL.txt`) in `openpilot/selfdrive/assets/fonts/`, `RELEASES.md`'s top entry, and this file.
- **Everything else is unowned.** Put new behavior in our files: subclass, wrap or call upstream code instead of editing it. Read upstream's state rather than adding fields to it.
- **When an upstream edit can't be avoided,** make it the smallest hook that works: a flag that defaults to upstream's behavior, an overridable method, or one line. Don't reformat or reorganize around it.
- **List every upstream edit** in `openpilot/selfdrive/ui/tandem/README.md` under "Keeping merges easy" › Upstream integration, so a merge knows what to reapply.
- **Never change upstream's behavior for its own UI.** `STARPILOT_UI=upstream` and Tandem's own switches must still give upstream's screens, working as upstream intended.
- **Tandem sits on openpilot's original screens** (`MainLayout`), as on `release`, not on StarPilot 7's own UI. Tandem is opinionated about options, so it isn't offered as another choice next to StarPilot's.

## Merging upstream

- Upstream for `development` is the `testing` branch of `StarPilotHQ/StarPilot` (it replaced `Dom`). Tandem merges it; it doesn't rebase, so pushes never need force.
- In a conflict on an unowned file, keep upstream's version and make our edit again.
- After a merge, check what Tandem reads from StarPilot that can change without a conflict. `PORTING.md` lists it while the port is in progress.

## Design

- **Mock first.** A new or changed screen gets its HTML mock in `openpilot/selfdrive/ui/tandem/design/` (with a screenshot in `design/screenshots/`) before the code, and the code then matches the mock. See Screenshots and comparisons.
- **Don't change an approved mock without asking the owner.** If the code has to differ, say where and why in the README's "Where the code differs from the mocks".
- **Build screens from the component library** (`tokens.py`, `layout.py`, `draw.py`, `controls.py`, `rows.py`, `blocks.py`, `chrome.py`, `overlays.py`), not with raw raylib calls. Sizes come from the mocks through `T.px()` and `T.font_px()`. Raylib is StarPilot 7's binding, `from openpilot.starpilot.ui.raylib import rl`; never import `pyray` in UI code.
- **Keep StarPilot's logic.** Essentials redraws StarPilot's settings, alerts and onroad state; StarPilot still decides what's true, what's allowed and when. Settings write StarPilot's own params and settings stores.
- **Wording:** plain words about what the car does, sentence case, and no em dashes (Figtree has none in the atlases).

## Translations

Tandem's screens are written in English, with the text a driver reads marked for translation (`openpilot/selfdrive/ui/tandem/i18n.py`): `N_("…")` for labels and constants (translated where drawn), `t_("… {} …", value)` for text built at runtime, `tn_(singular, plural, n)` for counts, and `context=` for English with two meanings. Mark new text the same way; never put an English plural "s" in a hole.

- **Don't run `tools/translations.py update` yet.** The catalog still holds the strings of screens that aren't ported, and an update would drop them with their translations. `PORTING.md` says when it can run again.
- If translations add characters, rebuild the fallback font: `tools/fallback_font.py subset <dir of Noto TTFs>`, then `build`. The build tools need StarPilot 6's raylib (pyray 5.5), so run them with a `release` checkout's Python, not this branch's.

## Tests

- Set up once with `uv sync --frozen --extra dev --extra testing`, then `uv pip install mypy fonttools uharfbuzz`. On a Mac, also build StarPilot 7's raylib extension for macOS (the committed `openpilot/starpilot/ui/native/_raylib_extra.so` is for the device) as `openpilot/starpilot/ui/native/_raylib_extra.cpython-312-darwin.so`, which Python loads first; leave it uncommitted.
- Run the tests before pushing, and add tests for new behavior. `ruff check openpilot/selfdrive/ui/tandem` must pass.

  ```
  BIG=1 .venv/bin/python -m pytest -q -c /dev/null --confcutdir=openpilot/selfdrive/ui/tandem openpilot/selfdrive/ui/tandem/tests
  ```
- Annotate every function and write Google-format docstrings (README › Conventions). `.venv/bin/python openpilot/selfdrive/ui/tandem/tools/typecheck.py` must pass; it type-checks `openpilot/selfdrive/ui/tandem` and `openpilot/starpilot/tandem` with mypy.
- Don't skip or weaken a test to get green. A `release` test whose code isn't ported yet waits in `PORTING.md`'s list until it is.

## Screenshots and comparisons

Check every visual change by looking at it, not just by tests. All paths below are from the repo root; outputs go to `openpilot/selfdrive/ui/tandem/tools/out/`, which git ignores.

1. **Mock screenshots.** After changing a mock, re-shoot it (needs Playwright's Chromium) and commit the PNG with the mock. It also lists any box whose content overflows, so cramped mocks show up.

   ```
   node openpilot/selfdrive/ui/tandem/tools/shoot_mocks.js [mock names...]   # none: every mock
   ```
2. **Built screens.** Render headlessly at 2160×1080 with sample data, one PNG per mock name (on Linux, under `xvfb-run -a`):

   ```
   mkdir -p openpilot/selfdrive/ui/tandem/tools/out/renders
   PYTHONPATH=$PWD BIG=1 .venv/bin/python openpilot/selfdrive/ui/tandem/tools/render/snap.py \
     openpilot/selfdrive/ui/tandem/tools/render/scene_components.py openpilot/selfdrive/ui/tandem/tools/out/renders
   ```
   Each ported screen gets a `scene_*.py` saved under its mock's name.
3. **The comparison page.** Put each mock beside its render, with a note:

   ```
   python3 openpilot/selfdrive/ui/tandem/tools/compare.py openpilot/selfdrive/ui/tandem/tools/out/renders openpilot/selfdrive/ui/tandem/tools/out/compare
   ```
   `design/compare.json` lists the screens in order: the mock, its title, the note (what matches, or what differs and why) and whether it matches; `built` names the render when it isn't the mock's name, or a list to stack several. Add an entry for a new screen and update the note when a screen changes.
4. **On the device.** `openpilot/selfdrive/ui/tandem/tools/device_screenshot.sh <device address> out.png` saves what the comma's screen shows (a sleeping screen wakes first). Use it to check a change on the device, not only in host renders.
5. **Look at the results** (open the PNGs or `tools/out/compare/index.html`), fix what doesn't match the mock, and share the page with the owner when screens change.

## Release notes

A device's "What's new" is the top entry of `RELEASES.md`, up to its first blank line; GitHub releases aren't read. Before a release, add a new top entry: a `Tandem <date>` heading, its `===` line, then `* ` bullets with no blank lines inside.
