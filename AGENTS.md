# AGENTS.md

Tandem is a fork of StarPilot (which sits on openpilot). Its UI design language is **Essentials**. These rules hold for any change in this repo.

## Keep unowned code untouched

Everything outside Tandem's own files belongs to StarPilot or openpilot and changes with every upstream merge. The less of it we edit, the easier merges are.

- **Ours:** `selfdrive/ui/tandem/` (code, `design/`, `tools/`, `tests/`), `starpilot/tandem/`, the Figtree, JetBrains Mono and NotoSans-Fallback font files (and `NotoSans-OFL.txt`) in `selfdrive/assets/fonts/`, `RELEASES.md`'s top entry, and this file.
- **Everything else is unowned.** Put new behavior in our files: subclass, wrap or call upstream code instead of editing it. Read upstream's state rather than adding fields to it.
- **When an upstream edit can't be avoided,** make it the smallest hook that works: a flag that defaults to upstream's behavior, an overridable method, or one line. Don't reformat or reorganize around it.
- **List every upstream edit** in `selfdrive/ui/tandem/README.md` under "Keeping rebases easy" › Upstream integration, so a merge knows what to reapply.
- **Never change upstream's behavior for its own UI.** The `TANDEM_*=0` environment switches bring back upstream's screens, and they must still work as upstream intended.

## Merging upstream

- Upstream is the `StarPilot` branch of `StarPilotHQ/StarPilot`. Tandem merges it; it doesn't rebase, so pushes never need force.
- In a conflict on an unowned file, keep upstream's version and make our edit again.
- After a merge, check what Tandem reads from StarPilot that can change without a conflict. The README's "Branches and merging upstream" section lists it.

## Design

- **Mock first.** A new or changed screen gets its HTML mock in `selfdrive/ui/tandem/design/` (with a screenshot in `design/screenshots/`) before the code, and the code then matches the mock. See Screenshots and comparisons.
- **Don't change an approved mock without asking the owner.** If the code has to differ, say where and why in the README's "Where the code differs from the mocks".
- **Build screens from the component library** (`tokens.py`, `layout.py`, `draw.py`, `controls.py`, `rows.py`, `blocks.py`, `chrome.py`, `overlays.py`), not with raw raylib calls. Sizes come from the mocks through `T.px()` and `T.font_px()`.
- **Keep StarPilot's logic.** Essentials redraws StarPilot's settings, alerts and onroad state; StarPilot still decides what's true, what's allowed and when. Settings write StarPilot's own params.
- **Wording:** plain words about what the car does, sentence case, and no em dashes (Figtree has none in the atlases).

## Translations

Tandem's screens are written in English, with the text a driver reads marked for translation (`selfdrive/ui/tandem/i18n.py`): `N_("…")` for labels and constants (translated where drawn), `t_("… {} …", value)` for text built at runtime, `tn_(singular, plural, n)` for counts, and `context=` for English with two meanings. Mark new text the same way; never put an English plural "s" in a hole. After changing wording, run `python3 selfdrive/ui/tandem/tools/translations.py update`; `tests/test_translations.py` checks the template is current. To find unmarked text and layouts that won't fit longer languages, render `tools/render/scene_pseudo.py` and read its `missed.txt`. New strings show in English until translated. If translations add characters, rebuild the fallback font (`tools/fallback_font.py subset`, then `build`).

## Settings search

Every settings row is indexed in `selfdrive/ui/tandem/settings/search.py`. When you add, rename or move a setting, update its entry; `tests/test_settings.py` checks the index against every screen.

## Tests

- Run `pytest selfdrive/ui/tandem/tests` before pushing, and add tests for new behavior. `ruff check selfdrive/ui/tandem` must pass.
- Without a full openpilot build (no `cereal`, `zmq` or device hardware), run them with the stand-ins in `tools/render/` and leave out the four files that import `cereal`; say that those didn't run:

  ```
  PYTHONPATH=$PWD/selfdrive/ui/tandem/tools/render:$PWD BIG=1 xvfb-run -a python3 -m pytest -q -c /dev/null \
    --confcutdir=selfdrive/ui/tandem -p stub_plugin selfdrive/ui/tandem/tests \
    --ignore=selfdrive/ui/tandem/tests/test_headroom_warning.py --ignore=selfdrive/ui/tandem/tests/test_home_layout.py \
    --ignore=selfdrive/ui/tandem/tests/test_limit_offers.py --ignore=selfdrive/ui/tandem/tests/test_onroad.py
  ```
- Don't skip or weaken a test to get green.

## Screenshots and comparisons

Check every visual change by looking at it, not just by tests. All paths below are from the repo root; outputs go to `selfdrive/ui/tandem/tools/out/`, which git ignores.

1. **Mock screenshots.** After changing a mock, re-shoot it (needs Playwright's Chromium) and commit the PNG with the mock. It also lists any box whose content overflows, so cramped mocks show up.

   ```
   node selfdrive/ui/tandem/tools/shoot_mocks.js [mock names...]   # none: every mock
   ```
2. **Built screens.** Render every built screen headlessly at 2160×1080 with sample data, one PNG per mock name:

   ```
   mkdir -p selfdrive/ui/tandem/tools/out/renders
   PYTHONPATH=$PWD BIG=1 xvfb-run -a python3 selfdrive/ui/tandem/tools/render/snap.py \
     selfdrive/ui/tandem/tools/render/scene_compare.py selfdrive/ui/tandem/tools/out/renders
   ```
   `scene_compare.py` opens the settings window over the test fakes and saves each screen; onroad, home, setup, alerts and the other screens have their own `scene_*.py`, which it runs too. A new screen needs a step there (or a scene of its own), saved under its mock's name.
3. **The comparison page.** Put each mock beside its render, with a note:

   ```
   python3 selfdrive/ui/tandem/tools/compare.py selfdrive/ui/tandem/tools/out/renders selfdrive/ui/tandem/tools/out/compare
   ```
   `design/compare.json` lists the screens in order: the mock, its title, the note (what matches, or what differs and why) and whether it matches; `built` names the render when it isn't the mock's name, or a list to stack several. Add an entry for a new screen and update the note when a screen changes.
4. **Look at the results** (open the PNGs or `tools/out/compare/index.html`), fix what doesn't match the mock, and share the page with the owner when screens change.

## Release notes

A device's "What's new" is the top entry of `RELEASES.md`, up to its first blank line; GitHub releases aren't read. Before a release, add a new top entry: a `Tandem <date>` heading, its `===` line, then `* ` bullets with no blank lines inside.
