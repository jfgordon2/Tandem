# Tandem

Tandem is this fork of StarPilot. Its design language is **Essentials**: fewer choices and better defaults, with the car explaining what it's doing. This package holds the Essentials component library. The mocks, screenshots and tokens are in [`design/`](design/). It's built on raylib and the existing `Widget` base class. Screens are put together from these pieces instead of drawing with raylib directly.

To run the real UI on a Mac, follow the [desktop setup guide](docs/mac-desktop.md). `./c3` opens the large UI with Essentials; `./c4` opens upstream's small UI.

| Module | Contents |
| --- | --- |
| `fonts.py` | `font(face)`: the shared `FontWeight` faces from `gui_app`, plus `ExtraFont.EXTRA_BOLD` and `ExtraFont.MONO`, which load on first use. |
| `tokens.py` | Colors, type sizes, radii, layout sizes and timings in device pixels. `px()` converts mock pixels and `font_px()` converts mock font sizes. |
| `layout.py` | Rectangle math: `row`, `column`, `grid` (fixed sizes plus `FILL`), `inset`, `place`, `grow`. It doesn't draw. |
| `draw.py` | Rounded fills, single-line text (aligned and elided), captions, wrapped paragraphs, and `icon()`, which draws the mocks' line icons tinted (chevron, cross, plus and check use them too). |
| `icons/` | The mocks' icons: `svg/` holds each one copied from the mocks, and the PNGs beside it are rasterized from them by `tools/build_icons.js` (`node tools/build_icons.js`, needs Playwright's Chromium). Add an icon by adding its SVG and rerunning the tool. |
| `base.py` | `Component`: a `Widget` with `preferred_size()`, plus a touch area grown to `MIN_TOUCH`. `resolve()` for values that may be getters. |
| `controls.py` | `Button` (primary, secondary, ghost, danger for a confirm, danger soft for every other destructive button, nav), `ButtonRow`, `ValueButton`, `ToggleButton`, `Switch`, `Segmented`, `ChoiceCards`, `Stepper`, `Slider`, `Badge`, `Chip`, `ProgressBar` |
| `rows.py` | `SettingRow`, `SectionHeader`, `Text`, `Banner`, `OptionList` (pick one from a list), `Padded`, and `ListPanel`, which stacks rows with dividers, scrolls when they overflow, and can pin a footer |
| `chrome.py` | `BottomNav`, `Sidebar`, `PageHeader`, `HubTile`, `HubGrid`, and `SettingsPage`, which assembles a full screen |
| `assets/` | `boot_logo.jpg`, Tandem's boot logo (2160×1080, from `boot_logo.html`), with a true-black OLED background. Choosing it refreshes the copy in StarPilot's boot logos folder; the Essentials defaults choose it. StarPilot installs the selected splash at startup, so after a logo update, choose it again, reboot once to install it, then reboot again to view it. `design/bootlogo.html` links to the same source for screenshots and comparisons. |
| `blocks.py` | Layout blocks for the mocks' card layouts: `Stack` (with `SPACER`s or a growing item), `Card`, `Columns`, `Grid`, `Label`, `ValueLine`, `IconTitle`, `InfoCard`, `Field`, `Icon`, `Inline`, `Sized`, `Surface` |
| `overlays.py` | `Sheet` (slides up), `Dialog` (confirm; `Tone.DANGER` gives a destructive button), `Toast` |
| Settings › Device › Developer (`settings/developer.py`) | openpilot's Developer panel in our rows: ADB, SSH, GitHub SSH keys (upstream's fetcher), joystick debug, alpha longitudinal (with our warning, only where offered) and UI debug. |
| CAN test recorder (`settings/can_recorder.py`) | A passive logger under Device › Developer, built from the shared panels, value lines, badges and buttons. `starpilot/tandem/can_recorder.py` writes CAN frames and timestamped manual lock/unlock markers in a worker. See [log format and investigation notes](docs/can-recorder.md). |
| More for your car (`settings/vehicle.py`) | StarPilot's car-specific options for the detected car, on its params and handlers; restarts and panda flashing ask first in our dialogs. |
| `overlays.py` dialogs over upstream actions | Restart, Power Off, Recalibrate and the driver monitoring reset ask in our `Dialog`, then run upstream's action (the confirm-only prompts are run with their dialog caught and answered, so upstream's checks still apply). Software's Release Channel and Uninstall (upstream's three steps), What's new and the Bluetooth sound test use our sheets and dialogs too. How It Works stays upstream's training guide: its steps are pre-drawn images. |
| `keyboard.py` | `EssentialsKeyboard`: upstream's `Keyboard` (typing, shift and caps, the 123 and #+= layers, backspace repeat, password masking, minimum length) drawn as `design/keyboard.html`, with a named action key. Used by every text entry our screens open: Wi-Fi and hotspot passwords, the hotspot name, APN, Report a Problem, the startup message and the Galaxy password. Destination search holds it in the page as a `KeyPad`. |
| `tools/` | `build_icons.js` (icons), `shoot_mocks.js` (mock screenshots), `render/` (headless renders of every built screen with sample data, and the test stand-ins), and `compare.py` (the mock-beside-build page from `design/compare.json`). How to run them is in the repo's `AGENTS.md`. |

## Building a screen

The param names below are made up to keep the example short; `settings/` has the real screens.

```python
from openpilot.selfdrive.ui.tandem import (BottomNav, ListPanel, Segmented, SettingRow, SettingsPage, Sidebar, SidebarItem, Stepper,
                                               Switch)

params = Params()

page = SettingsPage(
  sidebar=Sidebar("Driving", [SidebarItem("Everyday"), SidebarItem("Weather", open_weather, value="Auto")], selected=0),
  content=ListPanel([
    SettingRow("Driving Style", "Sets following gap, acceleration and braking together",
               Segmented(["Relaxed", "Standard", "Sport"], lambda: params.get_int("DrivingStyle"),
                         lambda i: params.put_int("DrivingStyle", i))),
    SettingRow("Offset", "Added to every matched limit",
               Stepper(lambda: params.get_int("SpeedLimitOffset"), lambda v: params.put_int("SpeedLimitOffset", int(v)), -10, 15,
                       fmt=lambda v: f"{v:+g} mph"), indent=True),
    SettingRow("Smart Slowdowns", "Slows for curves and stop lights", Switch(lambda: params.get_bool("SmartSlowdowns"),
                                                                             lambda on: params.put_bool("SmartSlowdowns", on))),
  ], title="Everyday"),
  nav=BottomNav(["Driving", "Device", "Network", "Bluetooth", "Software"], selected=0, on_select=open_tab),
)
```

## Conventions

- **Values may be getters.** Any `Bindable` argument takes either a plain value or a zero-argument callable that is read every frame. That lets a row stay in sync with Params without extra glue. Changes go out through `on_change` / `on_click` callbacks.
- **Containers lay out their children.** A container asks each child for `preferred_size(max_width)` and decides where it goes, so pages never hard-code positions.
- **Touch.** A control smaller than `MIN_TOUCH` (112 px) still responds across a 112 px area. Containers turn that off with `grow_touch_target = False`. Rows inside a `ListPanel` ignore taps that are really scrolls.
- **Color and size only come from `tokens`.** If a screen needs a value that isn't there, add a token rather than a hex code.
- **Text.** Use `draw.text`, `draw.caption` and `draw.paragraph`. They apply `FONT_SCALE` and elide with "…". The font atlases are pre-baked, so a character that isn't baked in draws as "?". Add it to `DESIGN_CHARS` in `tools/build_figtree_fonts.py` and run that script.

## Keeping rebases easy

Automatic crash and performance reporting is disabled by the fork-owned `starpilot/tandem/diagnostics.py`. Exceptions, stall dumps and native crash artifacts remain on the device; unattended Sentry events, remote diagnostic log/stat forwarding and StarPilot statistics uploads are blocked. Sentry only sends explicitly submitted issue reports and tunes, with automatic integrations, sessions and tracing disabled. The drive-log/video Uploads setting is separate and keeps its existing behavior. Base-code integrations are small policy hooks so rebases can keep upstream's capture and upload logic.

This fork is rebased onto StarPilot, and everything outside this package belongs to StarPilot or to openpilot underneath it. Our work therefore lives in new files and edits upstream files only when there is no other way.

- **Ours:** everything in `selfdrive/ui/tandem/`, meaning the code, `design/` (mocks and docs), `tools/` and `tests/`. Also the new font files `selfdrive/assets/fonts/Figtree-*` and `Figtree-OFL.txt`, which have to sit where the app loads fonts from.
- **Upstream integration:**
  - Root `README.md`: Tandem's project introduction, release and development links (including the Mac desktop setup guide), and screenshots from `assets/screenshots/`. Reapply this overview after an upstream merge, preserving the upstream credits and third-party notices.
  - The file names in `FontWeight` (`system/ui/lib/application.py`), which switch the whole UI to Figtree.
  - `KEEP_FONT` in `system/ui/lib/application.py` (off by default, so upstream's behavior): `font_fallback` skips unifont while it's on. `draw.py` turns it on only while it measures and draws Tandem's own text, which isn't translated, so a language that needs the fallback font leaves Tandem in Figtree; upstream's screens and widgets still fall back.
  - The fallback font for scripts Figtree lacks is Noto, not unifont: `FontWeight.UNIFONT` names `NotoSans-Fallback.fnt` (`system/ui/lib/application.py`), and `UNIFONT_LANGUAGES` (`system/ui/lib/multilang.py`) adds `ar` and `uk`, which Figtree can't draw (Inter could draw Cyrillic). `tools/fallback_font.py` builds the atlas from the Noto subsets in `tools/fonts/` (rerun `subset`, then `build`, when translations gain characters; `tests/test_fallback_font.py` fails until then). Upstream loads that font unfiltered, as it did pixel unifont; `fonts.prepare_fallback()` (from `screens.py`) gives it mipmaps.
  - `TEXT_SHAPERS` in `system/ui/lib/application.py` (empty by default), applied in its `draw_text_ex` wrapper and in `measure_text_cached` (`system/ui/lib/text_measure.py`): Tandem adds `arabic.shape`, which joins Arabic letters and orders right-to-left lines for raylib, which draws one glyph per character left to right. Text without Arabic is unchanged.
  - In `selfdrive/ui/layouts/main.py`: the imports, the calls that create the sidebar, home, settings and onroad screens (`screens.py`), and the left sidebar's width. StarPilot's developer sidebar on the right keeps upstream's width.
  - In the wheel controls daemon and its manager predicate: temporary button testing runs while the Bluetooth screen is open, including onroad, without changing the saved enable setting. Tests cover the service and screen lifecycle.
  - `starpilot/system/bluetooth/daemon.py`: `_settings_allowed()` is an overridable gate for settings commands, delayed sound tests and scan maintenance; its default is the original offroad check. `main()` selects Tandem's controller subclass from `starpilot/tandem/bluetooth.py`. That subclass also allows a stationary Park with fresh valid car/control messages and inactive controls. The raw offroad state, reconnect policy and incoming-pairing acceptance remain upstream's; `TANDEM_SETTINGS=0` selects the original controller.
  - Small hooks: `_show_header()` in `selfdrive/ui/layouts/home.py`, a lane line color override in `selfdrive/ui/onroad/model_renderer.py`, `_get_border_color()` in `selfdrive/ui/onroad/starpilot/starpilot_onroad_view.py`, `draw_gradients` in `selfdrive/ui/onroad/hud_renderer.py` (off in Essentials, so no dark fade from the screen's edges), and the Help steer sound in `selfdrive/ui/soundd.py`.
  - `common/params_keys.h`: `SteeringHeadroomWarning` and `DeveloperStripMetrics`. The device runs the committed `common/params_pyx.so` and `libcommon.a` (`prebuilt`), so a new key only exists there once those are rebuilt; until then reading or writing it crashes the UI. Tandem's own on/off settings use marker files instead (`prefs.py`). Device › Backups saves those files too, in a `.tandem_prefs` folder inside each backup that restore copies back beside the params folder rather than into it (the stored forecast isn't saved; it's a cache). A backup made before this leaves Tandem's current settings alone. StarPilot's own automatic backups still hold only params.
  - `system/version.py`: `release` is in `RELEASE_BRANCHES`, so Tandem's release branch boots as a release build (development-only params cleared, friendly update errors).

  If a rebase conflicts in these files, keep upstream's version and reapply the integration.
- **Unchanged:** `Widget`, `process.py`, the installer, the Inter and mono files, `THIRD_PARTY_NOTICES.md`, and the upstream settings panels.
- **New needs go in this package**, not in shared modules. For example, extra font faces live in `fonts.py` rather than in `FontWeight`.

## Branches and merging upstream

Tandem has one branch, `release`, on `jfgordon2/Tandem`. Upstream is StarPilot's `StarPilot` branch on `StarPilotHQ/StarPilot` (firestar5683's repo), which sits on openpilot. Tandem merges upstream rather than rebasing, so `release` keeps its history and pushes never need force.

Set up once in a clone:

```
git remote add upstream https://github.com/StarPilotHQ/StarPilot.git
```

To take upstream's changes:

```
git checkout release
git fetch upstream StarPilot
git merge upstream/StarPilot
```

Conflicts can only come from the upstream files listed under Upstream integration, and from the owner's own changes to StarPilot code (the turn signal animations in `selfdrive/ui/onroad/starpilot/turn_signals.py` and `starpilot/assets/signal_packs/`, the settings it adds, and the diagnostics hooks). Keep upstream's version, then make our edit again. Files in this package never conflict.

**Release notes:** a device's "What's new" is the top entry of `RELEASES.md` at the repo root, up to its first blank line; GitHub tags and releases aren't read. Before pushing a release, add a new top entry: a `Tandem <date>` heading, its `===` underline, then `* ` bullets (two spaces before a nested `* `), with no blank line inside. `tests/test_tandem.py` checks the top entry is Tandem's and whole.

After a merge, check what Tandem reads from StarPilot, which can change without a conflict:
- run the tests in `tests/` (see the top of this README);
- the turn signal renderer's `render()` arguments and `BUNDLED_SIGNAL_PATHS` (`onroad/view.py`, `settings/display.py`);
- the messages and fields the status chips read (`onroad/status.py`) and the alert names in `onroad/alerts.py`;
- `RELEASE_BRANCHES` still lists `release`.
- `device.add_interactive_timeout_callback` and gui_app's `_nav_stack` and `pop_widgets_to`, which `menu_idle.py` uses to close what's open on top of settings when the menu times out while driving.

## The settings window

`settings/` is the Essentials settings window. `selfdrive/ui/layouts/main.py` creates it through `settings_window()` instead of upstream's `SettingsLayout`. Set `TANDEM_SETTINGS=0` to get the upstream window back.

### How it's built

- **Window:** `window.py` has four tabs (Driving, Device, Connections, Software), each with its own page stack, and the close/back button. It also takes upstream `PanelType`s, so the home screen and sidebar open the right tab. Sheets and dialogs are drawn over the page by the window itself (`present`/`dismiss`), because the app draws only the top widget of its own stack.
- **Models and panels:** each screen is a small model class that reads and writes params through `SettingsStore`, plus a function that builds its panel. One control usually writes several params, and the model owns that mapping. Tests drive the models with a fake param cache.
- **Upstream logic:** anything with real logic behind it goes through an adapter class named `Upstream…` that calls upstream code. That covers downloads, Wi-Fi, Bluetooth, wheel remotes, the updater, the car list, and calibration and power. Upstream keeps its checks, threads and confirmations, and we only draw. The window takes each adapter as a constructor argument, so tests and headless renders pass fakes (`tests/fakes.py`).
- **Signalling:** `SettingsStore.write` signals the driving processes once per call. `SettingsStore.batch()` groups many writes into one signal; Reset Settings uses it.

| Tab | Screens | Files | Upstream code it drives |
| --- | --- | --- | --- |
| Driving | Hub with the power-user switches | `driving_tab.py`, `bundles.py` | |
| | Speed & Steering: Everyday, Vehicle Profile, Weather, Navigation, Assistance | `speed_steering.py` | |
| | Display: Driving Screen, Theme & Startup, Map | `display.py` | |
| | Alerts, with the volume sheet | `alerts.py` | Sounds screen's sample player |
| | Driving Model and its catalog | `model.py` | Driving model screen controller |
| | Vehicle and the car picker | `vehicle.py` | Fingerprint catalog, button actions |
| | Offline Maps and the region picker | `maps.py` | Maps screen controller; removal is StarPilot's (parked, not mid-download), confirmed in our dialog |
| | Tuner Mode: Steering, Gas & Brake, Following & Stops, Bundle Overrides | `tuner.py`, `editors.py` | |
| Device | This Device, the pairing page, Remote Access, Regulatory and the driver camera (`drivercamera.py`) | `device.py` | `DeviceLayout` handlers; the pairing code is upstream's `PairingDialog`'s (token and 5-minute refresh). Remote Access uses upstream's Galaxy keyboard, files, link and `GalaxyQRDialog` code, and its unpair; the password setup writes the same three files upstream's handler does, without its QR dialog |
| | General, Backups, Storage & Data, Report a Problem | `device_sections.py` | Same folders and report as StarPilot's System screen; one storage measurement shared with Offline Maps and the model catalog; offline maps and unused models can also be removed here |
| Search | Every setting by name, meaning and place; opens its page and section | `search.py` | The index is checked against every screen by `tests/test_settings.py` |
| Connections | Sections: Wi-Fi; Cellular (with Roaming, APN and IP address); Bluetooth Remote; Car Audio & Devices | `connections.py`, `network_tab.py`, `bluetooth_tab.py` | `WifiManager`, wheel controls service, `BluetoothManager` |

The Cellular section shows the current hotspot name and edits it through the shared keyboard. `starpilot/tandem/wifi.py` subclasses upstream’s Wi-Fi manager only for profile discovery and renaming; no upstream Wi-Fi files are changed. NetworkManager saves the name in the same profile, with its UUID, password, security and routing preserved. A stable profile ID restores a renamed hotspot at startup before upstream creates its default. The 32-byte UTF-8 SSID limit is checked before saving; names colliding with saved networks are rejected. An active hotspot reconnects with its new name; an inactive hotspot stays off. Upstream’s UI still uses the original Wi-Fi manager.

Bluetooth discovery runs through the shared `WhileShown` lifecycle on both Bluetooth sections. Tandem waits for the manager's asynchronous status, enables the radio through StarPilot's existing manager, and starts scanning only after the adapter reports powered. Settings are allowed offroad or with fresh valid messages confirming Park, standstill, speed below 0.1 m/s, and no enabled lateral/longitudinal control. Both the UI and authoritative service use `starpilot/tandem/bluetooth.py`; publication and receive times must both be within one second. This lets a car stereo be paired with accessory/ignition power available. Scans renew when the daemon's 20-second window ends, pause while pairing, and stop when the section hides (including a start still awaiting its first status update). Original device filtering, pairing protocol, reconnect/offroad controller policy and the upstream UI fallback remain intact.
| Software | Updates, release channel, Reset Settings, Uninstall | `software_tab.py`, `defaults.py` | `SoftwareLayout` actions |

### Upstream screens still shown, one tap away

These are reached from a row or button, never as a tab:

- **Destination search**, from Navigation's Set or Change. In the mocks it belongs on the parked home screen, which isn't built yet.
- **"More for your car"** under Vehicle. It holds car-specific toggles (Toyota, Subaru, Bolt, Jeep) and panda flashing.
- **openpilot's Developer panel**, under Device, only while Tuner Mode is on.

`upstream.py` hosts them. `StarPilotPage` opens one StarPilot panel directly, without going through StarPilot's own hub.

### Where the code differs from the mocks

- **Hotspot Edit buttons:** use the shared `ValueButton`, including its chevron, as the other settings editors do.
- **Lead marker:** the newly approved `design/gaptag.html` supersedes the primary ground bar in `leadmarker.html` and the triangle in the older `onroaddev.html`. The anchor estimates the roof from StarPilot's projected ground point and marker size. A tag too near the top edge keeps only its anchor until there is room for readable text.
- **Voice setup:** the download panel keeps the mock's layout, but its explanation now includes the one-time native engine setup instead of calling it only a 75 MB model download.
- **Alerts:** the volume preset adds **Auto**, upstream's default, where the level follows cabin noise.
- **Row heights:** settings rows keep the standard height (`T.ROW_HEIGHT`, sub-rows `T.SUB_ROW_HEIGHT`) everywhere for consistency, even where a mock draws them shorter or taller to fit. So a few cards scroll a little instead of fitting as in their mocks: Assistance's Driver Monitoring (While parked), Alerts' Chimes (Weather heads-up) and Vehicle's Steering Wheel Buttons. Two exceptions keep their own height: the Speed Limit Sign row, which holds the two sign pictures, and the Where to? list, whose rows are search results.
- **Uploads:** offers Off, **Parked** and Always. Upstream can hold uploads while driving, but it has no Wi-Fi-only switch.
- **Things upstream has no support for:**
  - Automatic weekly backups.
  - "Attach last drive" in Report a Problem.
  - Automatic matching of the speed limit sign style to your region, so the choice is US or Vienna.
- **Wheel remotes** don't come with four preset buttons. A button has to be pressed before it can be mapped.
- **Wheel-button testing** captures remote presses while Connections › Bluetooth Remote is shown, including onroad and with no mappings yet. Leaving the tab or closing settings ends testing and cancels pending learning. Testing does not change the saved enable setting for normal remote actions.
- **Button favorites** run the existing settings/action favorites. Car and remote pickers show each saved action's name; these are separate from saved destinations. Removing or moving a remote mapping frees its controller action slot once no other button uses it.
- **openpilot's core switches** live in Speed & Steering › Assistance. Upstream's "Experimental mode" switch is gone; Smart Slowdowns switches modes automatically.

## Onroad, home and first-run setup

`screens.py` creates the screens MainLayout shows. Setting `TANDEM_SIDEBAR=0`, `TANDEM_HOME=0`, `TANDEM_SETTINGS=0` or `TANDEM_ONROAD=0` brings back upstream's version of that screen.

- **Onroad** (`onroad/`): `EssentialsOnroadView` subclasses StarPilot's onroad view and keeps its camera, path and lane lines, and StarPilot still chooses every alert. It replaces the following:
  - **Lead gap tag** (`onroad/lead.py`, `design/gaptag.html`): the primary car ahead uses the existing developer tag's JetBrains Mono, fill, border and padding, with an anchor and connector above its estimated roof. Normal view shows only the centered actual time gap; below 1 m/s it shows meters or feet, returning to seconds above 1.5 m/s. Developer View or Lead Insights preserves distance, gap and relative speed in the same tag. The display value has a 0.3 s smoothing time constant; driving data is unchanged. The existing `LeadSettle` rule starts the 250 ms anchor/connector/tag entrance for a new lead or a distance jump over 8 m, with full-size text throughout. Low-confidence values become `--` at 45% opacity. Invalid, stale or previous-drive messages hide the tag and reset its state. Secondary and adjacent cars retain their faint bars. Tests in `tests/test_lead_tag.py` cover data validity, smoothing, units, acquisition, centering and view integration.
  - **Bottom bar:** no panel or scrim behind it, so the road shows to the bottom edge. It holds menu (the sidebar), MAX − / + (StarPilot's `SLCForceCruiseSpeed`, only while engaged), the street name, and engage. The street name comes from mapd, with directions and street types shortened as signs write them (`onroad/streets.py`: "North Main Street" reads "N Main St"); the turn card shortens each street in its instruction the same way.
    - Engage and disengage go through the wheel controls' action counters.
    - While a route is active, the street name gives way to arrival time, what's left and End route. That reads `navInstruction` through the view's own subscriber, since `ui_state` doesn't subscribe to it.
  - **Status chips** (bottom left, stacked up from the bar): up to four at once, newest nearest the bar (the highest priority when there are more); each held 2 s after its reason ends, renewed when it fires again, then faded, with the rest sliding down; all hidden during alerts (`ChipStack`). The rules are in `onroad/status.py`, pure and tested.
    - Turn progress uses the planner's active turn-speed target and measured deceleration for "Slowing for turn", then its turn events for "Turning left/right". Slowing stays first during the approach, even if the model has already requested the turn. Steering, stopping and curve statuses keep their existing priority.
    - "Turning left/right" also appears directly when there was no automatic slowdown, including Always On Steering with the driver operating gas/brake, with or without a route.
    - The slowdown chip and navigation card share maneuver icons. The chip uses the turn that actually set the speed target (including a next turn), with a neutral map icon if the direction is unknown. Paused-steering chevrons follow the signal side, with a hazard symbol for both signals. Weather chips use rain, snow or fog icons to match the condition.
    - Lane-change and turn progress always use chips. Display's Driving Style Banner switch only controls the personality message when the style changes (off by default), using the existing saved preference. There is no Clean Screen bundle in Tuner Mode.
  - **Steering headroom arc:** replaces the torque bar and uses its estimate. It has three stages (under 60%, 60–85%, over 85% held for 0.5 s) and a faint preview of what the path needs 2.5 s ahead.
    - At limit, the lane lines turn orange, the border turns amber, and Help steer plays one soft warning chime through soundd. Help steer is drawn as a Warning alert card in the bar's place (the bar and chips hide, as for other alerts), with the arc above it. It uses the warning volume and steering-limit mute-speed settings. The warning clears below 80%, or when steering becomes inactive; existing alerts take priority. The small release margin prevents repeated chimes around 85%.
  - **MAX follows limits** (`prefs.MAX_FOLLOWS_LIMIT`, a marker file, on by default, under Speed Limits › Match): when StarPilot adopts a new limit, MAX becomes it plus the offset, through the same `SLCForceCruiseSpeed` request the bar's − / + use (`onroad/limits.py` `LimitFollower`). A lower limit only lowers MAX and a higher one only raises it, so a higher MAX the driver set stays; a MAX set within a zone stays until the next limit. Without it StarPilot coasts down to a lower limit under an unchanged MAX (its SLC coast curve), which on Eco braking takes a minute or more; with MAX at the limit it slows as it does for a lower MAX. StarPilot still decides which limit applies and when.
  - **New-limit card:** asks before matching a new limit when Speed Limits says to ask for that direction (Higher limits and Lower limits, StarPilot's `SLCConfirmationHigher` and `SLCConfirmationLower`; lower limits apply on their own by default). A higher one asks "Speed up to", a lower one "Slow down to". Each new card chimes once with openpilot's pre-alert (`pre_alert.wav`, the first "Pay Attention" chime, at the Driver attention volume), requested through soundd's existing `TestAlert` as StarPilot's onroad sound previews do; it's skipped when StarPilot's Speed limit changed chime is on, since that already sounds. Match sends StarPilot's `SpeedLimitAccepted`. Ignore suppresses consecutive offers for that same limit, including after an offer expires or its source briefly disappears. An intervening higher or lower posted limit, or a new drive, allows it again.
  - **Speed, sign and turn card:** StarPilot still decides when each shows (its HUD's speed with the hide-speed rule, its speed card's posted limit, its turn card's route data); they're drawn as in the mocks. The sign stays top left, with the turn card popping up below it while navigating; while the new-limit card asks it takes the sign's place, and the turn card stays below it. The compass above the speed isn't drawn.
  - **Turn signal:** two green chevrons in the speed pill on the signalling side, the brighter one stepping outward. It replaces StarPilot's signal animations, so Display has no animation picker.
  - **Removed:** the driving personality button, the experimental-mode wheel, the favorites menu (the lower-left gesture), the picture-in-picture side camera (a Galaxy developer feature), the stopped timer, and the paused and weather badges, which the chips replace.
  - **Alerts** (`onroad/alerts.py`): StarPilot's alert renderer keeps its choice of alert, timing, sound and fades; the drawing follows the three levels in `design/alertstyles.html`. Info (normal and StarPilot alerts) is a dark pill at the bottom and the border keeps its color. Warning (prompts) is an amber two-line card with an amber border. Critical (full-screen or critical alerts) is a dark red takeover with a steering wheel icon and a red border, and the sign hides under it. Reverse gear keeps StarPilot's text-only drawing over the rear view. Light Turned Green, Lead Departed, lane changes and turn progress show as status chips instead of banners; their chime still plays and the bar stays usable. The bar, chip, new-limit card and driver monitor tile hide during any other alert.
  - **Driver monitor** (top right corner): upstream's driver state drawn as a dark tile with the driver icon, ringed green while attentive and amber as attention drops, dimmed when the camera isn't monitoring, hidden during alerts as upstream does.
- **Where to?** (`destinations.py`, mocks `destinations.html`, `navsearch.html`, `routepreview.html`): one full-screen widget with three views, opened from Home and from Settings › Navigation. StarPilot's navigation controller still does the work (Mapbox search and resolving, favorites with Home and Work, recents, starting and ending a route); `UpstreamPlaces` reaches into it. The route preview (`routemap.py`) asks Mapbox for the route the way navigationd does (`MapboxRouteEngine`, `MapboxSecretKey` and the last GPS fix), in the background, and draws it on the mock's stylized map with Arrive, Time and Distance. There are no map tiles; the route is fitted to the panel, north up. This is one extra directions request per previewed place, before navigationd makes its own on Start.
  - The list: Home and Work tiles (a tile with nothing saved searches for one and sets it), Add favorite, other favorites, recents with a star, and the active route with End route. Offline maps ready shows when maps are downloaded.
  - Search: the keyboard sits in the page; results update 0.6 s after you stop typing (from 3 letters), and Search lists them all without the keyboard.
  - Voice typing (`voice.py`, `speech.py`, `speech_native.py`, mocks `voicelistening.html`, `voicetranscribing.html`, `voicedownload.html`): a mic beside 123 on every keyboard except passwords, parked or driving. Driving, the worker reads micd's audio (`rawAudioData`, which micd publishes while it holds the microphone) instead of opening it, and runs whisper.cpp with 2 threads on cores 0-3, away from controlsd and card (4), plannerd, radard and selfdrived (5) and modeld (7), which are real-time anyway (`speech.driving_limits`); if no audio arrives within 2 s it says so. `worker.log` records each transcription's time and mode. The tinygrad fallback uses the GPU, so it stays parked-only. Listening ends on a tap, after a 1.5 s pause, after 6 s with nothing said, or at 15 s. The words land in the field for editing; nothing is searched or saved until the action key. Address fields prime Whisper with an example address and use `address_text` to join digit-by-digit house numbers and write street ordinals.
  - The comma uses the CPU runner from [whisper.cpp v1.9.5](https://github.com/ggml-org/whisper.cpp/tree/d1be6fde11ac6e0407606b4e42fe72d34add8037) (MIT), with tiny.en Q8 weights. First use verifies and downloads the model (44 MB) and source (10 MB), then builds a static runner with the AGNOS CMake/C++ toolchain. They stay in `/data/tandem/speech`; no AGNOS package, StarPilot file, power policy or telemetry setting changes. `python3 selfdrive/ui/tandem/speech.py --prepare` performs this one-time setup before a mic attempt. Later taps use the cached executable and model, without GPU compilation or a resident service. The 768-frame audio context covers the full 15 s recording limit, rather than processing 30 s of mostly silence. Longer `--file` diagnostics grow the context up to the full 30 s. Greedy decoding uses one candidate with temperature retries off. Shorter 512-frame contexts were faster but misheard a test phrase, so they are not used.
  - The worker remains separate from the UI and records with sounddevice. It drops inherited real-time priority and CPU affinity (`relax_priority`); the native runner inherits its background priority. Audio travels in memory through a WAV pipe, and text returns through stdout; no recording is saved. Cancel or leaving the panel kills the worker; a Linux parent-death signal also ends its native child. The native helper execs before importing numpy, and avoids Python `preexec_fn` in a threaded worker. Errors and transcription duration stay in the local `worker.log`. The setup panel describes the one-time engine preparation as well as the model download.
  - `TANDEM_SPEECH_BACKEND=tinygrad` selects the old GPU implementation for diagnostics; PC previews default to it. Its model is tinygrad’s `examples/whisper.py`, kept in `speech.py` because releases omit examples, with numpy spectrograms and the GPT-2 word list. Decoder activations stay float32 to avoid the QCOM half-precision reduction failure. To test either backend on 16 kHz mono float32 audio: `python3 selfdrive/ui/tandem/speech.py --file clip.npy` (append `address` for an address). Tests cover PCM handoff, context coverage, address handling, setup retries and native child cancellation, plus repeated tinygrad decoding with a small synthetic model.
  - The preview: the place, what Essentials does on the way, and Favorite / Home / Work toggles, then Start. There is no map or arrival estimate before starting: StarPilot only routes once a destination is set. Renaming a favorite isn't offered.
- **Home's alerts and update** (`home_alerts.py`, `design/homealerts.html`, `homeupdate.html`): upstream's OffroadAlert and UpdateAlert still read the params and own Snooze update, Acknowledge excessive actuation and Reboot and update; we draw alert cards by severity (with short titles for the alerts we know) and the release notes, and Home no longer shows upstream's header.
- **Home** (`home.py`): upstream's HomeLayout with new home content: readiness and the current setup, Where to? (`destinations.py`), and the Software card: it opens the release notes when an update is ready, and otherwise Settings › Software (MainLayout opens settings as usual, then `screens.show_settings_tab` moves the window to Software). The home cards use the full content height without the legacy header or its tap targets. Offroad alerts and update details retain upstream's header and navigation.
- **Menu timeout while driving** (`menu_idle.py`): upstream's MainLayout goes back to the driving view when the screen's interaction timeout runs out (`ScreenTimeoutOnroad`, 30 s by default), closing the sidebar and settings. A second callback on that same timeout also closes anything opened on top of them (a keyboard, Where to?, the driver camera preview, a dialog). Parked, nothing extra closes. No upstream edit.
- **Mapbox keys** (`mapbox_help.py`, mocks `drivingnav.html`, `mapboxkey.html`): StarPilot takes two. The public key (`MapboxPublicKey`, pk., the account's default token) is for place search (Search Box API); the secret key (`MapboxSecretKey`, sk.) is for routes, turn guidance and the Mapbox speed-limit filler (Directions API), which the Essentials defaults turn on (`SLCMapboxFiller`). Tandem has no field to type them: Navigation's Mapbox Keys row says which are saved and opens a sheet with the steps (a Mapbox account; a token with the default public scopes plus DOWNLOADS:READ, which makes it sk.; Remote Access; Galaxy › Navigation & Maps › App Keys, where the owner found it; Galaxy's classic layout also lists App Keys under Tools). Without the public key Where to? says search needs it; without the secret one the route preview says routes do. Where the mock bolds sk. and pk. in the steps, the code's wrapped text can't.
- **Weather heads-up** (`forecast.py`, mocks `statuschips.html`, `drivingweather.html`, `alerts.html`): the next 24 hours of Open-Meteo's forecast in 15-minute steps (free, no key, the source StarPilot's weather presets use), kept in `.tandem_forecast.json` beside the params folder. It's fetched in the background at most once an hour, or sooner when the car is more than 20 miles from where it was fetched; a failed fetch retries after 5 minutes. The location is StarPilot's `LastGPSPosition`. Rain (from light rain), drizzle, freezing rain, snow, thunderstorms and fog count, each by name. A status chip shows "Snow in 12 min" from 15 minutes before it starts, then "Snow until 8:15 PM" (the place's local time) while it lasts, in place of the presets' longer-gap chip. When an event is first seen within the hour (60 minutes out, or less when the car was just turned on), the chip shows briefly and the pre-alert chimes once. Switches: Weather › Weather heads-up and Alerts › Chimes › Weather heads-up, both marker files (`prefs.py`), on by default. Times are to the nearest 15 minutes, and it's a forecast, not radar.
- **Where to? in the bar** (`OnroadBar`, mock `onroadwhereto.html`): without a route, a tinted square beside MAX with the parked card's navigation arrow opens Where to? over the driving view, so a destination can be set while driving (with voice typing). While navigating it isn't there; End route is.
- **Weather in the bar** (`layers.weather_now`, `forecast.now_conditions`, mock `onroadextras.html`): without a route, the drive screen's bar ends with the current hour's weather icon and temperature (°F/°C from General › Temperature) at the street name's size, opposite the compass tag; the street centers between them. From the same forecast, so only with Weather heads-up on and a forecast that covers the hour.
- **Parked forecast** (`home.py` Hero, `forecast.outlook`, mocks `homeweather.html`, `homeweatherdry.html`): the next 12 hours along the bottom of the Ready card, one tile an hour (time, icon, temperature in °F or °C from General › Temperature, `prefs.TEMPERATURE`, which follows Units until the driver picks one), with one line above: the next hazard ("Light snow from 5:45 to 8:30 PM", or "until" while it's falling) or, when dry, the sky over the most hours in Open-Meteo's terms (Sunny, Mostly sunny, Partly cloudy, Cloudy; Clear and Mostly clear at night). It shares the drive screen's forecast (`shared_service`), which the parked screen also refreshes; the location is StarPilot's live GPS position, or after a restart the one it saved (`where_now`, as Galaxy finds the car). Failed fetches are logged ("weather forecast fetch failed"). Hidden with fewer than 3 hours of forecast left, or with Weather heads-up off.
- **Sidebar** (`sidebar.py`): subclasses upstream's Sidebar, which still tracks device state and owns the callbacks. It has a Settings button and a status card with Network, comma connect, Temperature, Vehicle and Maps, each with a colored dot. Onroad it adds Save a clip (upstream's flag button), and it shows a recording indicator while cabin audio is recorded.
- **First-run setup** (`setup.py`): three questions, or Use defaults. Either way it applies the Essentials defaults first. Home shows it once, as soon as onboarding has closed; a marker file beside the params folder records that it's done, so no new param key is needed.

What these don't do yet:
- **Onroad extras** (`onroad/extras.py`, `design/onroadextras.html`): StarPilot's optional visuals, each still under its own switch, drawn in Essentials: pedal tiles (PedalsOnUI) and the external-GPU model chip under the driver monitor tile (StarPilot's widget still decides the state and fade), the compass as a tag at the start of the bar, in the same place with or without a route, a stopping-point line with a distance tag, adjacent-lane and blind-spot washes, light-blue path edges, white radar dots, the curve glow in our blue, and signal (blue, blinking) and blind-spot (red) halves of the border. StarPilot's steering-torque border fill is left out; the steering arc shows the same. The rainbow path stays StarPilot's.
- **Developer View** (`onroad/developer.py`, `design/onroaddev.html`), in JetBrains Mono as the mock sets it: a panel on the right with LEAD (distance, gap, relative speed, radar or vision), DEVICE (CPU and temperature, GPU, RAM, FPS) and CONTROLS (curve speed, limit source, lane widths); a strip above the bar; Lead Insights' tag above the lead car; and the limit's source and offset under the sign. Values come from openpilot's and StarPilot's messages (`read()`). StarPilot's settings decide what shows: its developer sidebar switch for the panel, Developer UI for the rest, and each row's own switch (ShowCPU, NumericalTemp, ShowGPU, ShowMemoryUsage, FPSCounter, AdjacentPathMetrics, SpeedLimitSources; the last also covers the note under the sign), all in Tuner › Bundle Overrides. The strip shows up to five metrics picked there under Bar metrics (`STRIP_METRICS`, kept in the new `DeveloperStripMetrics` param, default the mock's accel, want, jerk, lat and delay), each given an equal share of the width; picking none hides it. `main.py` takes the panel and its width from `screens.py`.

## Translations

Tandem's screens are written in English, and the text a driver reads is marked where it's written (`i18n.py`):

| Mark | For | Translated |
| --- | --- | --- |
| `N_("Driving Style")` | Text in tables, labels and constants | Where it's drawn, so a language change applies at once |
| `N_("Set up", context="action")` | English that means two things | The same, with its own entry |
| `t_("Sets {} options", count)` | Text built at runtime | Now, with the values in its `{}` holes |
| `tn_("{} alert", "{} alerts", n)` | Counts | Now, in each language's plural forms |

- **Drawing:** `draw.text`, `fit`, `text_width`, `paragraph` and `caption` look up whatever they draw, so `N_` text comes out translated, and so do the pieces of text the code joins (" · " and " › " summaries, comma lists, a name with its value such as "Drives 21.0 GB", case changes). StarPilot's `trn()` text, which arrives formatted ("2 regions"), is matched against its plural entry. Anything not in the catalog (street names, Wi-Fi names, numbers) is drawn as is.
- **Catalog:** `tools/translations.py update` collects every `N_`, `t_` and `tn_` (with context and plural) into `translations/tandem.pot`, plus the `tr()`/`trn()` strings of the StarPilot screens Tandem's adapters show text from (`UPSTREAM`) and the home screen's offroad alert sentences (`alerts_offroad.json`), and merges it into each `tandem_<code>.po`. A mark needs a string literal; long ones are split with `+`. Translations may number their holes (`{1} {0}`) to reorder the values.
- **Pseudo-language check:** `scene_pseudo.py` renders every screen with each marked string as "[Text ~~~]" (`TANDEM_PSEUDO=1`) into `tools/out/pseudo/`, and lists in `missed.txt` the drawn text without brackets: text that wasn't marked. The extra 30% shows where a longer language won't fit. What's left on the list is meant to stay English: sample names and addresses, StarPilot's onroad alert text, dates, brand names, Developer View's labels and param keys, and the words on the US speed limit sign.
- **Fonts:** each string is drawn in Figtree when Figtree has all its letters, otherwise in the Noto fallback (Japanese, Arabic, Cyrillic...).
- **Languages so far:** a pilot in Spanish, German and Japanese, machine-drafted and needing a native speaker's review. The other languages have no Tandem catalog yet, so Tandem shows English for them. StarPilot's novelty styles (Caveman, Pirate...) aren't in Tandem's language list.
- **Not yet translated:** settings search matches English words only; dates use English month names.

## Third-party

Figtree is © 2022 The Figtree Project Authors (<https://github.com/erikdkennedy/figtree>), used under the SIL Open Font License 1.1. The license text is in `selfdrive/assets/fonts/Figtree-OFL.txt`. The `.ttf` files are unmodified; the `.fnt`/`.png` atlases are generated from them by `tools/build_figtree_fonts.py`.

Tests: `tests/test_tandem.py` (components) and `tests/test_settings.py` (window navigation and param mapping).
