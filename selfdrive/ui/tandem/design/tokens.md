# Essentials design tokens

The mocks use Figtree, JetBrains Mono for numbers, and the colors and sizes below. This page explains how they map onto the app. The values themselves live in [`tokens.py`](../tokens.py). The components that use them are described in the [library README](../README.md).

## Converting mock values

- **Scale.** Mocks are drawn at 1125×563. The comma 3/3X panel is 2160×1080, so 1 mock px = 1.92 device px. `px(mock_px)` does the conversion, and every layout constant in the module is already converted.
- **Font sizes.** The app multiplies every font size by `FONT_SCALE` (1.242 on the large UI) when it draws text. `font_px(mock_px)` divides that back out, so the `SIZE_*` constants are the values to pass to draw calls. For example, a 28 px mock title is `SIZE_TITLE` = 43 and draws at 53 px.
- **Touch targets.** Some mock buttons are 42–44 px tall, which is 81–84 device px. That is under the existing 112 px minimum (`MIN_TOUCH`, about 8 mm). Draw them at their mock size, but make the touch area at least `MIN_TOUCH`.

## Fonts

The app UI draws in Figtree: the `FontWeight` members in `system/ui/lib/application.py` now name Figtree files instead of Inter. That is the only upstream change. Inter stays in the repo for the installer and tools that load it directly. ExtraBold and JetBrains Mono come from `selfdrive/ui/tandem/fonts.py` (`ExtraFont`), which loads them the first time a component draws with them.

| Weight | Token | Used for |
| --- | --- | --- |
| 400 Regular | `FONT` | Subtitles, footnotes, body text |
| 500 Medium | `FONT_MEDIUM` | Values next to labels |
| 600 SemiBold | `FONT_SEMIBOLD` | Row titles, buttons, sidebar and nav items |
| 700 Bold | `FONT_BOLD` | Panel titles, selected segments, chips |
| 800 ExtraBold | `FONT_EXTRABOLD` | Screen titles, the speed, big values |
| JetBrains Mono Medium | `FONT_MONO` | Numbers in Developer View and Tuner Mode |

- The `.ttf` files are in `selfdrive/assets/fonts`. The Figtree bitmap fonts (`.fnt`/`.png`) are built by `selfdrive/ui/tandem/tools/build_figtree_fonts.py`. It runs the unchanged upstream `process.py` with `·`, `…`, `−` and `›` added to its character set, which already covers ASCII, `EXTRA_CHARS` and every non-CJK translation. Chinese, Japanese, Korean, Arabic and Thai still fall back to unifont. If you rerun `process.py` directly, it rebuilds Figtree without those four characters, so run the StarPilot script afterwards.
- The mocks show JetBrains Mono at 700 in a few places, but only Medium ships. Medium is used for all mono text.
- **Startup.** Every distinct `FontWeight` file loads one 2048×2048 atlas at startup. That is still six: four Figtree weights, unifont and the brand font, exactly where Inter's four used to be. Inter no longer loads. ExtraBold and mono each add one atlas, the first time they are drawn.
- The mono atlas is upstream's, without the four extra characters. That's fine for numbers.

## Type scale

| Token | Mock px | Draw size | Weight | Where |
| --- | --- | --- | --- | --- |
| `SIZE_VALUE` | 72 | 111 | 800 | Value editors |
| `SIZE_SPEED` | 62 | 96 | 800 | Onroad speed |
| `SIZE_TITLE` | 28 | 43 | 800 | Screen titles |
| `SIZE_PANEL_TITLE` | 24 | 37 | 700 | Panel headings |
| `SIZE_CARD_TITLE` | 22 | 34 | 700 | Hub tiles, card headings |
| `SIZE_ROW_TITLE` | 19 | 29 | 600 | Setting rows |
| `SIZE_BODY` | 18 | 28 | 600 | Sidebar, nav, primary buttons |
| `SIZE_BUTTON` | 16 | 25 | 600 / 700 selected | Segments, secondary buttons |
| `SIZE_LABEL` | 15 | 23 | 400–600 | Chips, small buttons |
| `SIZE_SUBTITLE` | 14 | 22 | 400 | Row subtitles, footnotes |
| `SIZE_CAPTION` | 13 | 20 | 700, capitals, `CAPTION_TRACKING` | Section labels |
| `SIZE_BADGE` | 12 | 19 | 700 | ACTIVE, OVERRIDE, DEFAULT badges |

## Colors

The mocks used about 60 hex values. These are merged into the named set below. Where two shades differed by less than a visible amount, the more common one was kept. For example, `#9FAABA` data labels merge into `TEXT_TERTIARY`.

| Group | Tokens |
| --- | --- |
| Surfaces, dark to light | `BG #000000` · `SURFACE_1 #13161A` · `SURFACE_2 #16191D` · `SURFACE_3 #1A1D22` · `SURFACE_4 #1E2227` · `CONTROL #23272E` · `TRACK #2A2F36` |
| Chrome | `NAV_BAR #0E1013` · `NAV_BAR_EDGE #1F242B` · `CONTROL_NAV #1F2328` · `SCRIM #050608` · `KEY #262A31` · `KEY_MOD #353A43` |
| Text | `TEXT #F2F5F9` · `TEXT_SECONDARY #C9D0DA` · `TEXT_TERTIARY #AEB6C2` · `TEXT_MUTED #8FA0B5` (6.0:1 on `SURFACE_4`, the lowest-contrast pair; all text tokens pass 4.5:1) |
| Accent | `ACCENT #5AAAF8` · `ACCENT_INK #0B1A2B` · `ACCENT_TEXT #7DBBF9` · `ACCENT_SURFACE #1F2E45` · `ACCENT_SELECTED #182434` · `ACCENT_CHIP_TEXT #DCEBFF` |
| Success | `SUCCESS #1F9A55` · `SUCCESS_BRIGHT #3FD08A` · `SUCCESS_TEXT #6FD8A0` · `SUCCESS_SURFACE #13301F` · `SUCCESS_CHIP_TEXT #D2F5E1` |
| Warning | `WARNING #F0B35A` · `WARNING_BORDER #E0A23A` · `WARNING_SURFACE #3A2E1B` · `WARNING_BANNER #221D14` · `WARNING_TITLE #FFD08A` · `WARNING_CHIP_TEXT #FFE3B8` |
| Danger | `DANGER #D9434F` · `DANGER_BUTTON #C8404D` · `DANGER_TEXT #F2A7B1` · `DANGER_TEXT_OUTLINE #E58C98` · `DANGER_SURFACE #3A2026` · `DANGER_BORDER #5A3A40` · `CRITICAL_FILL #2A0E12` |
| Switch | Track on `ACCENT`, knob on `#0E1520`; track off `#343A44`, knob off `TEXT` |
| Onroad | Bar scrim: a vertical gradient from `#0B0D10` at 0% to 55% · `ONROAD_CONTROL` `#1F2328` at 80% · `ONROAD_CARD` `#0B0D10` at 90% · `LEAD_MARKER #E9B44C` · steering arc track white 18%, comfortable white 90%, working `WARNING`, at limit `#FF6A3D` |

This palette replaces Aether's purple accent (`aether_style.ACCENT*`) with blue. Screens move over one at a time to the Essentials components. Once no screen uses `aether_style.py` and `aethergrid.py`, both are deleted.

## Shape and layout

| Token | Mock px | Device px |
| --- | --- | --- |
| `RADIUS_SHEET` / `RADIUS_PANEL` / `RADIUS_CARD` / `RADIUS_ITEM` | 26 / 22 / 18 / 14 | 50 / 42 / 35 / 27 |
| `RADIUS_CONTROL` / `RADIUS_SEGMENT` / `RADIUS_BADGE` | 12 / 10 / 8 | 23 / 19 / 15 |
| `NAV_HEIGHT` / `NAV_BUTTON` | 102 / 74 | 196 / 142 |
| `SIDEBAR_WIDTH` / `SIDEBAR_ITEM_HEIGHT` | 300 / 56 | 576 / 108 |
| `ROW_HEIGHT` / `SUB_ROW_HEIGHT` | 60 / 48 | 115 / 92 |
| `SEGMENT_HEIGHT` / `BUTTON_HEIGHT` / `PRIMARY_BUTTON_HEIGHT` | 42 / 44 / 60 | 81 / 84 / 115 |
| `SWITCH_WIDTH` × `SWITCH_HEIGHT` | 72 × 42 | 138 × 81 |
| `ONROAD_BAR_HEIGHT` / `ONROAD_CONTROL_SIZE` / `STATUS_CHIP_HEIGHT` | 92 / 74 / 44 | 177 / 142 / 84 |

A selected card has an `ACCENT_SELECTED` fill and a 2 mock px `ACCENT` edge.

## States

- **Pressed:** draw `PRESSED_OVERLAY` (white at 8%) over the control while it's touched.
- **Selected:** segments fill with `ACCENT` and use `ACCENT_INK` bold text. Cards get `ACCENT_SELECTED` with the accent edge. Sidebar items use `ACCENT_SURFACE`; Tuner Mode uses `WARNING_SURFACE` instead.
- **Disabled:** the whole row or control is drawn at 50% opacity (`DISABLED_ALPHA`), and the subtitle says why (e.g. "Available with Towing", "Pairing waits until you're parked").
- **Override / Default / Learned / From style:** use the badge colors from the Tuner Mode mocks: `WARNING_SURFACE`/`WARNING`, `CONTROL`/`TEXT_SECONDARY`, `ACCENT_SURFACE`/`ACCENT_TEXT`.

## Motion

| Token | ms | Use |
| --- | --- | --- |
| `SHEET_MS` | 240 | Sheets slide up. Dialogs fade in and scale up from 96%. |
| `SWITCH_MS` | 150 | Switch knob and track color |
| `PRESSED_ROW_MS` | 600 | Wheel-button "PRESSED" highlight |
| `STATUS_CHIP_HOLD_MS` / `STATUS_CHIP_FADE_MS` | 2000 / 200 | Status chips |
| `TOAST_MS` | 4000 | Toasts (never shown while driving) |
| `STEER_LIMIT_HOLD_MS` | 500 | Time over 85% before "Help steer" |
| `SPEED_LIMIT_PROMPT_MS` | 8000 | Higher-limit prompt times out to Ignore |

## Icons

The mocks draw icons as 24×24 line icons with a 2 px stroke and round caps, and they need exporting as PNG or SVG into `selfdrive/assets/icons`.

- **Existing icons to reuse:** `backspace`, `shift`, `checkmark`, `close`, `lock_closed`, `menu`, `warning`, `wifi_strength_*`, and the settings hub icons the current hub already uses.
- **New icons needed:**
  - Status chips: curve, traffic light, stop octagon, car rear, turn arrow, gauge, rain cloud, steering wheel with pause bars, signal chevrons, blocked lane, lane-shift arrow, play, car with up arrow.
  - Everything else: star, bookmark, home, briefcase, trash, monitor, speaker, map, sun, cloud variants for Weather, and the remote / game controller.

## Not covered yet

- The small 536×240 UI (`mici`).
- Light mode. The design is dark only.
- Right-to-left layouts.
