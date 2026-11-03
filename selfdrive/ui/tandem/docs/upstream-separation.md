# Upstream separation audit, 2026-11-03

## Cleanup results

The cleanup resolves the five findings below against the same fetched upstream tip, `febcb8f290782084c556472b6adcb4c3b0ff2fc7`. No upstream merge was needed: that tip was already an ancestor of the release branch.

| Outside owned paths | Before | After |
| --- | ---: | ---: |
| Changed paths | 197 | 26 |
| Added text lines | 8,293 | 306 |
| Removed text lines | 3,912 | 176 |
| Added external files | 127 | 0 |

The final counts include root `README.md` branding and the interface tour (119 added and 94 removed lines). The other 25 paths have 187 added and 82 removed lines. Only three settings controllers differ from upstream, by 34 added and 26 removed lines in total, replacing the previous 19-file settings redesign.

- Restored upstream settings presentation, shared dialogs, scrolling, Inter/unifont names, border geometry and small-screen UI. Tandem owns its fonts, text shaping, gesture handling and animation drawing. All four screen factories retain upstream fallbacks; font loading and shaping no longer leak through disabled factories.
- Replaced broad dialog interception with named confirmation and notice hooks. Tandem auto-confirms only the specific action already approved in its own dialog. Original engagement checks remain authoritative, and an unknown future prompt is shown normally.
- Restored `common/params_keys.h`, `common/params_pyx.so`, `common/libcommon.a` and `cereal/custom.capnp` byte-for-byte to upstream. The metric preference migrates the old raw file into owned preferences and remains in backups. Help steer and selected-turn status use expiring atomic snapshots outside the registry/schema. Navigation observes the target StarPilot actually selects; it does not infer another turn or change cruise decisions.
- Moved 108 animation asset files, the renderer, generators, preview tools, how-to docs and fork-specific tests into owned paths. Shared pack metadata, Galaxy integration and the Help steer audio implementation now live under `starpilot/tandem/`. The wheel and audio daemons select owned subclasses while the shared base behavior stays upstream's.
- Updated the full integration inventory in [the README](../README.md#keeping-rebases-easy), including diagnostics policy and pre-existing Bluetooth hooks. `tools/upstream_audit.py --check` verifies every remaining external path is listed. Future source conflicts should start from upstream and reapply that inventory.

### Cleanup validation

- **783 passed, 2 skipped** in the full owned native test run, including the four UI files omitted from the stand-in subset, plus `starpilot/tandem/tests/`. The skips are Linux-only process/scheduler behavior on macOS. Galaxy checks execute the production route bodies as well as the owned helpers.
- **187 passed** in upstream audio, model-ready audio, cruise and wheel-control regressions. Their local messaging test required access to IPC outside the sandbox.
- **643 passed, 2 skipped** in the documented stand-in UI subset. Its four native-dependent files were omitted only here and ran in the full native suite above.
- **127 of 127 before/after screenshots are pixel-identical** at 2160 × 1080 with a controlled clock and sample data. Inspected rendered keyboard, reverse alert, settings, signal picker and onroad samples. Approved mock screens were unchanged. Review artifacts are generated under `tools/out/separation/index.html`, with the mock comparison at `tools/out/separation/compare/index.html`.
- Ruff passes for both owned trees. Translation extraction is current at 1,658 entries in each of the 12 catalogs; font-coverage tests pass. The integration inventory check and the owned-path whitespace check pass. The whole-tree whitespace check reports only whitespace copied verbatim from restored upstream settings files; those files were deliberately left unchanged from upstream.
- The shipped parameter binaries match upstream; the native test suite also checks that its loaded registry matches the header. This does not replace device ABI or hardware validation. No device flashing, driving, Bluetooth pairing or real wheel-button check was performed.
- The moved onroad preview tool produced a native 2160 × 1080 animation frame, which was visually inspected, and exited cleanly.

The native run used the isolated Mac host cache built with `SP_KEEP_DESKTOP_RUNTIME_ARTIFACTS=1 SP_C3_COMPILE_ONLY=1 ./c3 8`; see [mac-desktop.md](mac-desktop.md). Runtime preference/state directories were isolated from normal settings. Run from the generated host worktree after installing `tests/requirements.txt` into its venv:

```sh
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH="$PWD" BIG=1 SP_HEADLESS_TEST=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PARAMS_ROOT=/tmp/tandem-native-test-params \
  OPENPILOT_PREFIX=_tandem_separation ../venv/bin/python -m pytest -q -c /dev/null \
  --confcutdir=selfdrive/ui/tandem -p no:cacheprovider \
  selfdrive/ui/tandem/tests starpilot/tandem/tests
```

## Original audit baseline

The following findings and inventory describe the pre-cleanup release, retained to explain what was removed. They are not the current integration inventory.

Compared Tandem `release` at `2b14d9238b` with a fresh fetch of
`StarPilotHQ/StarPilot:StarPilot` at `febcb8f290` (Accept AGNOS 20.2 on Stable).
Upstream is an ancestor of this release: 0 upstream-only commits and 264
Tandem-only commits. There is no pending upstream merge to rehearse. This is an
audit of the existing fork delta and its maintenance seams, not a prediction
that the next merge will be conflict-free.

The newer Essentials code generally has the intended separation. The repository
as a whole does not yet meet the minimal-hook policy in `AGENTS.md`. Older UI
changes remain in shared StarPilot/openpilot files and are still used by both
the fallback UI and some Tandem adapters.

| Scope at the audited commits | Files | Added text lines | Deleted text lines |
| --- | ---: | ---: | ---: |
| All differences | 686 | 142,188 | 3,934 |
| Owned paths, fonts, AGENTS and release notes | 489 | 133,895 | 22 |
| Outside owned paths | 197 | 8,293 | 3,912 |

The 197 external paths consist of 70 modified upstream files and 127 additions.
Of the additions, 108 are signal-pack assets and 19 are code, tests, tools or
documentation. Asset additions have much less merge exposure than rewrites of
existing upstream code. The ownership count treats `RELEASES.md` as owned only
after checking that its delta is entirely the new top entry. Counts exclude
binary line totals and these audit documentation changes.

## Findings and cleanup order

1. **High: retire the old settings redesign in upstream files.**
   `selfdrive/ui/layouts/settings/` has 19 changed files, with 2,670 added and
   3,436 removed lines. The largest is `starpilot/aethergrid.py` (1,273 added,
   1,315 removed). The model, maps, navigation, vehicle, system and download
   screens also have substantial presentation changes. These remain active
   when `TANDEM_SETTINGS=0`; that switch selects the locally modified
   `SettingsLayout`, not StarPilot's original screen. Move the presentation and
   new helpers into owned paths, preserving required controller fixes as small
   reviewed hooks. The existing `UpstreamModels`, `UpstreamMaps`,
   `UpstreamDevice` and `UpstreamCarExtras` adapters instantiate those modified
   controllers, so restoring the files requires testing the adapters as well.

2. **High: treat the param binaries and schema as merge outputs with explicit
   compatibility checks.** `common/params_keys.h` adds `SpeedAtBottom`,
   `DeveloperStripMetrics` and `SteeringHeadroomWarning`; both
   `common/params_pyx.so` and `common/libcommon.a` differ from upstream.
   Keeping upstream's binaries drops local keys; keeping ours can drop new
   upstream keys, defaults or flags. Rebuild the combined result and verify it
   on the device. New UI preferences should continue using `prefs.py`; moving
   existing keys there needs a migration and, for the warning timestamp, an
   agreed UI-to-soundd transport. Separately, `cereal/custom.capnp` extends
   `StarPilotPlan` at ordinals 45–47. `starpilot_vcruise.py` stores the selected
   maneuver, `starpilot_planner.py` publishes it, and `onroad/status.py` reads
   the fields directly. Review upstream's next schema additions even if Git
   merges them cleanly. Preserve the authoritative selected-turn state;
   upstreaming that telemetry contract would avoid maintaining competing
   fields. Do not silently infer a potentially different turn in the UI.

3. **Medium: restore shared-widget and font defaults for upstream callers.**
   `system/ui/widgets/confirm_dialog.py` is rewritten and imports the StarPilot
   settings component library; `option_dialog.py` now subclasses a local
   `AetherChoiceDialog` from the settings package. These are unconditional
   changes to shared system widgets. `FontWeight` globally replaces Inter and
   unifont with Figtree and Noto, including the small UI. `screens._enabled()`
   calls `prepare_fallback()` before checking a switch, registering global text
   shaping even when all screens fall back. `UI_BORDER_SIZE` changes from 30 to
   15, and the border, widget and radial-menu styling also differ globally.
   Keep Tandem's presentation in its component library and supply opt-in hooks
   whose defaults reproduce upstream behavior. Check all four switches at
   once and each supported mixed configuration before claiming fallback parity.

4. **Medium: adapters depend on local private implementations.**
   `settings/upstream.notices()` reads a dialog's `_text`; the fetched upstream
   `ConfirmDialog` stores its message in `_label` or `_html_renderer` instead.
   Restoring that one upstream file without updating the adapter would drop
   model notices, including a refused download while driving.
   `confirmed()` temporarily replaces `gui_app.push_widget` and confirms every
   captured object with a `_callback`. A future added prompt or different
   asynchronous flow needs review, even without a source conflict. Prefer an
   explicit controller action/notification seam with original upstream defaults.
   Also review private methods and state used by the model, maps, device,
   vehicle, software, menu-timeout and navigation adapters after each merge.
   Tests against fakes are useful but do not by themselves validate those live
   interfaces.

5. **Medium: move fork additions out of upstream namespaces and keep the
   inventory current.** New choice/preview widgets, `aether_style.py`, signal
   rendering, generator/preview scripts, docs and fork-specific tests live
   outside the owned paths. New files usually avoid ordinary line conflicts,
   but upstream can later add the same path. The turn-signal implementation is
   spread across both device UIs, theme installation, toggles, a JSON settings
   catalog and Galaxy. Consolidate shared pack metadata in an owned module and
   retain only the necessary upstream registration calls. Preserve the public
   Galaxy route and existing saved settings when moving it. The README now
   lists these deltas and no longer calls the settings panels unchanged or
   describes the branch workflow as a rebase.

The overlap is with actively changing code. In the last 500 fetched upstream
commits, `the_galaxy.py` was touched in 64, `params_keys.h` in 47,
`device_settings_layout.json` in 45, `params_pyx.so` in 41, and `libcommon.a` in
40. These are historical counts, not probabilities of future conflicts.

## Integrations already close to the intended pattern

- `screens.py` centralizes screen selection; `home._show_header()`,
  `model_renderer.lane_line_color_override`, `HudRenderer.draw_gradients` and
  `StarPilotOnroadView._get_border_color()` have upstream-compatible defaults.
- Wi-Fi profile editing is in `starpilot/tandem/wifi.py`, without an upstream
  Wi-Fi edit. The CAN recorder and Bolt OBD lease also live in owned modules.
- Bluetooth adds an overridable `_settings_allowed()` gate and selects a
  controller subclass in `starpilot/tandem/bluetooth.py`. The fallback service
  selects the original controller. Its policy tests exercise that distinction.
- Diagnostics policy is in `starpilot/tandem/diagnostics.py`, with short hooks
  in four upstream files. This is an intentional fork-wide policy, independent
  of screen selection. Keep it when restoring unrelated upstream UI code.
- `system/version.py` adds `release` to the release-branch list with a one-line
  change.

## Verification

The audit fetched the actual configured upstream remote, compared the full tree
delta, checked the commit ancestry, reviewed all external file groups and the
main adapter dependencies, and measured recent upstream overlap. No merge,
binary rebuild, runtime refactor, mock change, commit or push was performed.

- The documented stand-in test subset passed: **556 passed, 2 skipped**. The
  skips are the Linux parent-death-signal and Linux scheduling tests on macOS.
  Used the repository's `.venv` and `SP_HEADLESS_TEST=1` to avoid raylib's monitor
  query opening a temporary window; no Xvfb is installed on this Mac. As directed
  by `AGENTS.md`, `test_headroom_warning.py`, `test_home_layout.py`,
  `test_limit_offers.py` and `test_onroad.py` were excluded. Pytest reported one
  cache warning because `-c /dev/null` made it try to create its cache in `/dev`.
- `ruff check selfdrive/ui/tandem` and `git diff --check` passed.
- The 89 individual inventory rows were checked against Git's numeric diff;
  the seven asset groups account for the other 108 external files. Relative
  documentation links were checked as well.
- Device operation, full onroad tests, fallback visual parity and generated
  binary ABI/default/flag correctness were not verified. The existing binary
  key-presence test passed, which is narrower than those checks.

The successful test command was:

```sh
PYTHONPATH="$PWD/selfdrive/ui/tandem/tools/render:$PWD" BIG=1 SP_HEADLESS_TEST=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -c /dev/null \
  --confcutdir=selfdrive/ui/tandem -p stub_plugin selfdrive/ui/tandem/tests \
  --ignore=selfdrive/ui/tandem/tests/test_headroom_warning.py \
  --ignore=selfdrive/ui/tandem/tests/test_home_layout.py \
  --ignore=selfdrive/ui/tandem/tests/test_limit_offers.py \
  --ignore=selfdrive/ui/tandem/tests/test_onroad.py
```

## External file inventory

The table records every changed external file except the 108 signal-pack assets,
which are grouped below by pack. `+` and `-` are line counts; binary files have
no line count. Paths and counts are from the two audited commits, before these
documentation changes.

| Status | File | + | - |
| --- | --- | ---: | ---: |
| M | `README.md` | 115 | 94 |
| M | `cereal/custom.capnp` | 3 | 0 |
| M | `common/libcommon.a` | - | - |
| M | `common/params_keys.h` | 3 | 0 |
| M | `common/params_pyx.so` | - | - |
| M | `common/tests/test_params.py` | 12 | 0 |
| A | `docs/how-to/settings-ui-components.md` | 154 | 0 |
| A | `docs/how-to/turn-signal-animations.md` | 150 | 0 |
| M | `selfdrive/controls/tests/test_starpilot_vcruise.py` | 22 | 0 |
| M | `selfdrive/ui/__init__.py` | 1 | 1 |
| M | `selfdrive/ui/layouts/home.py` | 15 | 4 |
| M | `selfdrive/ui/layouts/main.py` | 11 | 13 |
| M | `selfdrive/ui/layouts/settings/device.py` | 4 | 2 |
| M | `selfdrive/ui/layouts/settings/settings.py` | 53 | 38 |
| M | `selfdrive/ui/layouts/settings/software.py` | 2 | 1 |
| M | `selfdrive/ui/layouts/settings/starpilot/aethergrid.py` | 1273 | 1315 |
| M | `selfdrive/ui/layouts/settings/starpilot/appearance.py` | 69 | 12 |
| A | `selfdrive/ui/layouts/settings/starpilot/choice_dialog.py` | 183 | 0 |
| M | `selfdrive/ui/layouts/settings/starpilot/driving_model.py` | 230 | 439 |
| M | `selfdrive/ui/layouts/settings/starpilot/lateral.py` | 5 | 2 |
| M | `selfdrive/ui/layouts/settings/starpilot/longitudinal.py` | 94 | 129 |
| M | `selfdrive/ui/layouts/settings/starpilot/main_panel.py` | 21 | 26 |
| M | `selfdrive/ui/layouts/settings/starpilot/maps.py` | 134 | 237 |
| M | `selfdrive/ui/layouts/settings/starpilot/navigation.py` | 131 | 247 |
| M | `selfdrive/ui/layouts/settings/starpilot/panel.py` | 43 | 5 |
| M | `selfdrive/ui/layouts/settings/starpilot/scribble.py` | 12 | 1 |
| A | `selfdrive/ui/layouts/settings/starpilot/signal_preview.py` | 59 | 0 |
| M | `selfdrive/ui/layouts/settings/starpilot/simple_download_manager.py` | 118 | 253 |
| M | `selfdrive/ui/layouts/settings/starpilot/sounds.py` | 49 | 74 |
| M | `selfdrive/ui/layouts/settings/starpilot/system_settings.py` | 105 | 375 |
| M | `selfdrive/ui/layouts/settings/starpilot/vehicle.py` | 85 | 280 |
| A | `selfdrive/ui/lib/aether_style.py` | 89 | 0 |
| M | `selfdrive/ui/lib/starpilot_visuals.py` | 3 | 1 |
| M | `selfdrive/ui/mici/layouts/settings/visuals.py` | 52 | 0 |
| M | `selfdrive/ui/mici/onroad/alert_renderer.py` | 13 | 16 |
| M | `selfdrive/ui/mici/onroad/augmented_road_view.py` | 18 | 1 |
| M | `selfdrive/ui/onroad/augmented_road_view.py` | 2 | 2 |
| M | `selfdrive/ui/onroad/hud_renderer.py` | 30 | 11 |
| M | `selfdrive/ui/onroad/model_renderer.py` | 5 | 2 |
| M | `selfdrive/ui/onroad/starpilot/favorite_radial_menu.py` | 34 | 92 |
| M | `selfdrive/ui/onroad/starpilot/starpilot_border.py` | 5 | 3 |
| M | `selfdrive/ui/onroad/starpilot/starpilot_onroad_view.py` | 78 | 3 |
| A | `selfdrive/ui/onroad/starpilot/turn_signals.py` | 172 | 0 |
| M | `selfdrive/ui/onroad/starpilot/widget_style.py` | 13 | 7 |
| M | `selfdrive/ui/soundd.py` | 39 | 0 |
| M | `selfdrive/ui/tests/test_aethergrid.py` | 991 | 41 |
| M | `selfdrive/ui/tests/test_favorite_radial_menu.py` | 37 | 0 |
| M | `selfdrive/ui/tests/test_onroad_render_layers.py` | 1 | 1 |
| A | `selfdrive/ui/tests/test_settings_group2_behaviour.py` | 147 | 0 |
| A | `selfdrive/ui/tests/test_settings_shared_components.py` | 218 | 0 |
| M | `selfdrive/ui/tests/test_simple_download_manager.py` | 24 | 0 |
| M | `selfdrive/ui/tests/test_starpilot_navigation_structure.py` | 3 | 3 |
| M | `selfdrive/ui/tests/test_starpilot_visuals.py` | 6 | 6 |
| A | `selfdrive/ui/tests/test_turn_signals.py` | 987 | 0 |
| M | `starpilot/assets/tests/test_theme_catalog_refresh.py` | 26 | 0 |
| M | `starpilot/assets/theme_manager.py` | 15 | 0 |
| M | `starpilot/common/assets/device_settings_layout.json` | 19 | 0 |
| M | `starpilot/common/starpilot_variables.py` | 1 | 0 |
| M | `starpilot/controls/lib/starpilot_vcruise.py` | 6 | 0 |
| M | `starpilot/controls/starpilot_planner.py` | 6 | 0 |
| M | `starpilot/system/bluetooth/daemon.py` | 8 | 4 |
| M | `starpilot/system/starpilot_stats.py` | 3 | 0 |
| A | `starpilot/system/the_galaxy/tests/test_turn_signal_animations.py` | 137 | 0 |
| M | `starpilot/system/the_galaxy/the_galaxy.py` | 84 | 0 |
| M | `starpilot/system/wheel_controls/tests/test_standby_button_wake.py` | 11 | 9 |
| M | `starpilot/system/wheel_controls/tests/test_wheel_controlsd.py` | 116 | 5 |
| M | `starpilot/system/wheel_controls/wheel_controlsd.py` | 10 | 9 |
| A | `starpilot/tools/make_bouncing_ball_signals.py` | 122 | 0 |
| A | `starpilot/tools/make_motion_signals.py` | 165 | 0 |
| A | `starpilot/tools/make_pouncing_cat_signals.py` | 205 | 0 |
| A | `starpilot/tools/make_sequential_signals.py` | 113 | 0 |
| A | `starpilot/tools/make_shooting_star_signals.py` | 158 | 0 |
| A | `starpilot/tools/render_onroad_preview.py` | 379 | 0 |
| A | `starpilot/tools/render_settings_preview.py` | 264 | 0 |
| M | `system/athena/athenad.py` | 6 | 0 |
| M | `system/loggerd/uploader.py` | 3 | 0 |
| M | `system/manager/process_config.py` | 1 | 1 |
| M | `system/manager/test/test_process_config.py` | 13 | 1 |
| M | `system/sentry.py` | 7 | 4 |
| A | `system/tests/test_sentry.py` | 89 | 0 |
| A | `system/tests/test_telemetry.py` | 46 | 0 |
| M | `system/ui/lib/application.py` | 15 | 9 |
| M | `system/ui/lib/multilang.py` | 2 | 0 |
| M | `system/ui/lib/scroll_panel2.py` | 12 | 2 |
| M | `system/ui/lib/text_measure.py` | 3 | 1 |
| M | `system/ui/widgets/confirm_dialog.py` | 114 | 53 |
| M | `system/ui/widgets/html_render.py` | 1 | 1 |
| M | `system/ui/widgets/option_dialog.py` | 9 | 75 |
| M | `system/version.py` | 1 | 1 |

Added signal-pack assets:

| Directory | Added files |
| --- | ---: |
| `starpilot/assets/signal_packs/bouncing_ball/signals/` | 42 |
| `starpilot/assets/signal_packs/flow/signals/` | 14 |
| `starpilot/assets/signal_packs/glide/signals/` | 14 |
| `starpilot/assets/signal_packs/open_flow/signals/` | 14 |
| `starpilot/assets/signal_packs/pouncing_cat/signals/` | 8 |
| `starpilot/assets/signal_packs/sequential/signals/` | 8 |
| `starpilot/assets/signal_packs/shooting_star/signals/` | 8 |

## Reproducing the comparison

```sh
git fetch --no-tags upstream StarPilot
git merge-base HEAD upstream/StarPilot
git rev-list --left-right --count upstream/StarPilot...HEAD
git diff --name-status upstream/StarPilot...HEAD
git diff --numstat upstream/StarPilot...HEAD
```

The three-dot diff shows changes since the common ancestor. For this audit the
ancestor is exactly the fetched upstream tip, so it is also the direct upstream
versus Tandem tree comparison. When upstream has new unmerged commits, review
both sides since the common ancestor and rehearse the merge in a separate
checkout before updating `release`.
