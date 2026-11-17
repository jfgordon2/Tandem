# Tandem

Tandem is this fork of StarPilot. Its design language is **Essentials**: fewer choices and better defaults, with the car explaining what it's doing. This package holds the Essentials component library. The mocks, screenshots and tokens are in [`design/`](design/). It's built on raylib and the existing `Widget` base class. Screens are put together from these pieces instead of drawing with raylib directly.

This branch ports Tandem onto StarPilot 7. [`PORTING.md`](PORTING.md) tracks the stages. The component library, sidebar, parked Home and core driving overlays are ported.

Tandem sits on openpilot's original layout (`MainLayout`), not on StarPilot 7's own UI. On the big UI, `ui.py` takes `MainLayout`'s path while any Essentials screen is on (`screens.py`), and `MainLayout` gets each screen from `screens.py`. A screen not ported yet is openpilot's. `TANDEM_HOME`, `TANDEM_SETTINGS`, `TANDEM_ONROAD` and `TANDEM_SIDEBAR` set to `0` give openpilot's screen back; with all four `0`, or `STARPILOT_UI=upstream`, Tandem stays out and StarPilot 7 chooses its UI as it would without Tandem.

| Module | Contents |
| --- | --- |
| `fonts.py` | `font(face)`: maps upstream weight identifiers to our Figtree and Noto files, plus ExtraBold and JetBrains Mono. All load on first use without replacing upstream fonts. |
| `tokens.py` | Colors, type sizes, radii, layout sizes and timings in device pixels. `px()` converts mock pixels and `font_px()` converts mock font sizes. |
| `layout.py` | Rectangle math: `row`, `column`, `grid` (fixed sizes plus `FILL`), `inset`, `place`, `grow`. It doesn't draw. |
| `draw.py` | Rounded fills, single-line text (aligned and elided), captions, wrapped paragraphs, and `icon()`, which draws the mocks' line icons tinted. |
| `icons/` | The mocks' icons: `svg/` holds each one copied from the mocks, and the PNGs beside it are rasterized from them by `tools/build_icons.js` (needs Playwright's Chromium). |
| `base.py` | `Component`: a `Widget` with `preferred_size()`, plus a touch area grown to `MIN_TOUCH`. `resolve()` for values that may be getters. |
| `controls.py` | `Button`, `ButtonRow`, `ValueButton`, `ToggleButton`, `Switch`, `Segmented`, `ChoiceCards`, `Stepper`, `Slider`, `Badge`, `Chip`, `ProgressBar` |
| `rows.py` | `SettingRow`, `SectionHeader`, `Text`, `Banner`, `OptionList`, `Padded`, and `ListPanel`, which stacks rows with dividers, scrolls when they overflow, and can pin a footer |
| `chrome.py` | `BottomNav`, `Sidebar`, `PageHeader`, `HubTile`, `HubGrid`, and `SettingsPage`, which assembles a full screen |
| `blocks.py` | Layout blocks for the mocks' card layouts: `Stack`, `Card`, `Columns`, `Grid`, `Label`, `ValueLine`, `IconTitle`, `InfoCard`, `Field`, `Icon`, `Inline`, `Sized`, `Surface` |
| `overlays.py` | `Sheet` (slides up), `Dialog` (confirm; `Tone.DANGER` gives a destructive button), `Toast` |
| `scroll.py` | Gesture rejection for Tandem's lists; upstream's scroll panel keeps its behavior. |
| `i18n.py`, `arabic.py`, `thai.py` | Translation (see Translations), Arabic joining and right-to-left order, and Thai clusters. |
| `prefs.py` | Tandem's own on/off preferences, kept as marker files beside the params folder. |
| `screenshot.py` | On the device, `touch /tmp/tandem-screenshot` saves the screen as `/tmp/tandem-screenshot.png` (waking it first if it sleeps). From a computer, `tools/device_screenshot.sh <address> [out.png]`. Nothing is stored or uploaded. |
| `screens.py` | Where Tandem joins StarPilot 7's UI: `ui_selection()` for `ui.py`, and the screens `MainLayout` shows. |
| `home.py`, `home_layout.py` | Parked Home, weather, release notes and offroad alerts. StarPilot’s software and alert owners supply state and actions. |
| `sidebar.py` | The sidebar beside home and the onroad view (`design/home.html`, `onroadmenu.html`): upstream's `Sidebar`, redrawn, with a Maps row from StarPilot's map manager. |
| `onroad/view.py`, `onroad/overlay.py` | Standard and Larger onroad HUD and the existing camera and model. StarPilot owns speed-limit decisions, cruise actions and alerts. |
| `onroad/size.py` | Text Size (Larger) and Reduce Motion for the driving screen and the menu sidebar. |
| `tools/` | `shoot_mocks.js` (mock screenshots), `render/` (headless renders: `snap.py` and `scene_*.py`), `compare.py` (the mock-beside-build page), `build_icons.js`, the font builders (`bmfont.py`, `build_figtree_fonts.py`, `fallback_font.py`, `crop_font_atlases.py`, `thai_font.py`), `translations.py` and `typecheck.py`. |

## Conventions

- **Values may be getters.** Any `Bindable` argument takes either a plain value or a zero-argument callable that is read every frame. That lets a row stay in sync with Params without extra glue. Changes go out through `on_change` / `on_click` callbacks.
- **Containers lay out their children.** A container asks each child for `preferred_size(max_width)` and decides where it goes, so pages never hard-code positions.
- **Touch.** A control smaller than `MIN_TOUCH` (112 px) still responds across a 112 px area. Containers turn that off with `grow_touch_target = False`. Rows inside a `ListPanel` ignore taps that are really scrolls.
- **Color and size only come from `tokens`.** If a screen needs a value that isn't there, add a token rather than a hex code.
- **Raylib.** UI code uses StarPilot 7's binding, `from openpilot.starpilot.ui.raylib import rl` (raylib 6). Its structs are plain values: they aren't callable and have no `ffi`.
- **Types and docstrings.** Every function in Tandem's code is annotated, and `tools/typecheck.py` (mypy over `openpilot/selfdrive/ui/tandem` and `openpilot/starpilot/tandem`) must pass. Docstrings use the Google format: every public class gets one, and so does any function whose name and types don't say enough, with `Args:`, `Returns:` and `Raises:` sections for what needs explaining. A one-line summary is enough when that says it all.
- **Text.** Use `draw.text`, `draw.caption` and `draw.paragraph`. They apply `FONT_SCALE` and elide with "…". The font atlases are pre-baked, so a character that isn't baked in draws as "?". Add it to `DESIGN_CHARS` in `tools/build_figtree_fonts.py` and run that script.

## Keeping merges easy

Tandem merges StarPilot 7 (`Dom`). New behavior, presentation, assets, tools and tests live in owned paths: `openpilot/selfdrive/ui/tandem/`, `openpilot/starpilot/tandem/`, the Figtree, JetBrains Mono and Noto font files and licenses, `AGENTS.md`, and the top entry of `RELEASES.md`.

**Upstream integration:** every external edit is listed here. Each defaults to upstream's behavior.

| File | Integration |
| --- | --- |
| `openpilot/system/ui/lib/application.py` | `KEEP_FONT = False` and an empty `TEXT_SHAPERS` list. `font_fallback` skips the language-wide Noto fallback while `KEEP_FONT` is set, and the `rl.draw_text_ex` wrapper runs `TEXT_SHAPERS` over the text. Tandem sets both only while drawing its own text (`draw._own_font`) and restores them afterward. Inter Medium and SemiBold load on demand with Tandem enabled. Inter Regular, Bold, Unifont and the current fallback are ready at startup. |
| `openpilot/system/ui/lib/text_measure.py` | `measure_text_cached` runs `TEXT_SHAPERS` too, so measuring matches drawing. |
| `openpilot/system/ui/widgets/inputbox.py` | The font getter defaults to the native face for draw, measure, and cursor placement. The release keyboard overrides it with the Tandem face. |
| `openpilot/selfdrive/ui/ui.py` | `select_ui(...)` is wrapped in `screens.ui_selection(..., BIG_UI)`, which returns StarPilot's choice unchanged unless Tandem's screens are on, and then openpilot's layout with the reason logged. |
| `openpilot/selfdrive/ui/layouts/main.py` | `Sidebar`, `SIDEBAR_WIDTH`, `HomeLayout`, `SettingsLayout` and `AugmentedRoadView` are imported from `screens.py` under those names, so every call stays upstream's; each gives openpilot's widget when its switch is off. Before drawing, a view whose class has `requires_full_view` (Tandem's onroad view, for a critical alert) can close the sidebar through its existing visibility setter. |
| `openpilot/starpilot/ui/native/raylib_extra.cc`, `_raylib_extra.so` | Exposes a native method to release the CPU copy of a font's glyph images, keeping its atlas and text metrics. Tandem calls it for Inter only. The Linux/ARM64 build is bundled. |
| `prebuilt.json` | Records the matching inventory after validating the rebuilt device artifact. |
| `openpilot/selfdrive/ui/onroad/augmented_road_view.py` | The stock HUD is prepared by default. Tandem's camera view passes `stock_hud=False` to keep unused Inter faces and assets out of the driving HUD. |
| `openpilot/selfdrive/ui/layouts/sidebar.py` | Tandem's sidebar passes `stock_text=False` to use its own fonts. The native sidebar initializes its normal fonts as before. |
| `openpilot/system/manager/process_config.py` | The automatic uploader uses Tandem’s release Off, Parked and Always predicate. Missing preferences and the recovery switches leave the process on its native schedule. Network policy remains in the uploader. |
| `openpilot/starpilot/maps/operation_owner.py` | Dispatches Tandem’s local snapshot removal request to code that shares the native admission lock and parked authority. |
| `openpilot/starpilot/navigation/navtilesd.py` | Handles the local map removal request between tile writes and acknowledges cleanup to the parked map owner. |

**After a merge:** if StarPilot changed `raylib_extra.cc` or its `_raylib_extra.so`, keep upstream's versions, add Tandem's
`release_font_glyph_images` method to the source again, rebuild the extension on a comma (AGNOS, ARM64), and refresh
`prebuilt.json` with StarPilot's receipt tool; until then Tandem skips the glyph release (`application.py` checks for
the method). Map removal uses names StarPilot's map owner and tile writer don't publish; `tests/test_map_removal_contract.py`
fails when a merge renames one.

**Font atlases:** `openpilot/selfdrive/assets/.gitignore` ignores `fonts/*.fnt` and `fonts/*.png`, left from StarPilot 6's generator. Tandem's own atlases are committed with `git add -f` rather than by editing that file; once tracked, git keeps them. After rebuilding an atlas, `git add -f` it again.

StarPilot 7’s raylib binding retains glyph images for TTF fonts. Tandem defers Medium and SemiBold and releases the Inter glyph bitmaps after loading the atlas. Boot measurements with both changes are pending.

## Where the code differs from the mocks

- **Stage 4 Settings:** the four-tab frame is from release. Unported pages currently show their openpilot panels. Device › RAM uses the release panel. The footer and report attachment match release. The release list scrolls to show the last process row.
- **Device › General:** the approved release capture is authoritative. The older General HTML still shows an Automatic Backups row. The built preview uses release’s five rows and Device rail with StarPilot 7’s language names.
- **Device › Backups:** the approved release capture is authoritative. The running release shows the saved snapshots and Back up now. The older HTML has a schedule row. The preview reuses the running release panel and confirmations.
- **Device › Storage & Data:** the preview reuses the release layout and rows. Offline Maps Delete uses the approved confirmation for all downloaded map formats.
  The native release dialog keeps its text spacing. The description wraps earlier than in the HTML mock.

- **Stage 4 driving screen:** the stand-in road in the mock represents StarPilot’s live camera and model. Speed-limit confirmation waits for a wide enough road view when the sidebar is open.

- **Stage 4 Home:** the existing sidebar centers its Settings button label, and release notes use a scrollable list
  of plain paragraphs. Home shows the installed version while the updater has no confirmed result for the current branch.

- **Sidebar, Maps row:** the mocks say "Up to date" for downloaded maps. StarPilot 7 selects a map snapshot and doesn't track updates, so the row says "Ready" when a map is selected. It says "Downloading" while the map manager downloads, installs or switches maps, and keeps its last answer while driving, when the map manager doesn't answer.

## Translations

Tandem's screens are written in English, and the text a driver reads is marked where it's written (`i18n.py`):

| Mark | For | Translated |
| --- | --- | --- |
| `N_("Driving Style")` | Text in tables, labels and constants | Where it's drawn, so a language change applies at once |
| `N_("Set up", context="action")` | English that means two things | The same, with its own entry |
| `t_("Sets {} options", count)` | Text built at runtime | Now, with the values in its `{}` holes |
| `tn_("{} alert", "{} alerts", n)` | Counts | Now, in each language's plural forms |

- **Catalog:** `translations/` is `release`'s, complete for every screen, ported or not. During the port, retain the existing entries when adding newly extracted strings. Rebuild the full catalog once every screen is ported.
- **Fonts:** each string is drawn in Figtree when Figtree has all its letters, otherwise in the Noto fallback. Figtree has no Vietnamese, which StarPilot 7 adds, so Vietnamese draws in the fallback. StarPilot 7 also drops Arabic from its language picker; Tandem's Arabic catalog stays until stage 4 decides the language list.
- **Fallback atlas:** rebuilt for StarPilot 7's translations from Noto Sans 500 Medium (`@expo-google-fonts` packages on npm). It leaves out Braille, which StarPilot 7 uses only for Galaxy's web drag handle ("Drag ⠿ to reorder"), and no Noto font has.

## Third-party

Figtree is © 2022 The Figtree Project Authors (<https://github.com/erikdkennedy/figtree>), used under the SIL Open Font License 1.1. The license text is in `openpilot/selfdrive/assets/fonts/Figtree-OFL.txt`. The `.ttf` files are unmodified; the `.fnt`/`.png` atlases are generated from them by `tools/build_figtree_fonts.py`. Noto Sans and JetBrains Mono are also under the SIL Open Font License 1.1 (`NotoSans-OFL.txt`, `JetBrainsMono-OFL.txt`).

`tools/bmfont.py` is StarPilot 6's `selfdrive/assets/fonts/process.py` (MIT, as openpilot), with its paths and fallback languages changed.
