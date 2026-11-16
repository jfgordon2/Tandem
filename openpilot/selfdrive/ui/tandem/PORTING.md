# Porting Tandem to StarPilot 7.0

`development` starts as upstream's `Dom` branch (StarPilot 7.0) at 1abbbc6d19. Tandem is ported onto it in stages. Until
stage 2 is done, `development` boots as stock StarPilot 7.0.

| Stage | State |
|---|---|
| 1. Foundation | Done; see below |
| 2. Entry point | Done; see below |
| 3 to 6 | Not started |

## Why a port and not a merge

`Dom` has no history in common with `release`. It is rebuilt on openpilot's full history, so `git merge` refuses it
("unrelated histories"). It is also a different codebase, not a newer copy of the one Tandem hooks into:

- All code moved under `openpilot/`. Import paths stay the same (`openpilot.selfdrive...`), file paths don't.
- Params went from 802 keys to 397. Tandem uses 236 params; 119 of them are gone, including `IsOnroad`. Many settings
  now live in StarPilot's own documents and owners (`starpilot/*/profile_document.py`, `offset_document.py`,
  `saved_document.py`) instead of params.
- StarPilot's UI was rewritten as `openpilot/starpilot/ui/` (`StarMainLayout`), picked in `ui.py` by
  `starpilot/ui/startup.py:select_ui`. The old `selfdrive/ui/layouts/settings/starpilot/` and
  `selfdrive/ui/onroad/starpilot/` are gone.
- Fonts are TTF files rendered into atlases at startup (`load_font_ex` at size 200), not prebuilt `.fnt` atlases.
- 21 of the 36 upstream files Tandem edits on `release` no longer exist, and 15 of the 37 StarPilot modules Tandem
  imports are gone. The files that remain changed a lot (`application.py` -644/+259 lines, `ui_state.py` -349/+454,
  `soundd.py` -443/+190, `model_renderer.py` -789/+248).
- Of the 22 message services Tandem reads, `starpilotPlan`, `liveDelay` and `liveParameters` are gone. Likely
  replacements, to confirm field by field: `starpilotLongitudinalPlan` and the `slc*` services, `lateralDelay`,
  `vehicleParameters`.

`Dom` was moving fast when this was written (439 commits in a week, against 5 on `StarPilot`), and its README calls it a
development branch with migration still in progress.

## How `development` follows upstream

- `development` merges `upstream/Dom` the usual way; its history is Dom's from the start, so those merges are ordinary.
- `release` keeps following `upstream/StarPilot` until 7.0 replaces it. Tandem fixes made on `release` meanwhile are
  ported to `development` by hand where the code differs.
- The rules in `AGENTS.md` apply, with owned paths under `openpilot/`.

## Stages

Each stage ends with its tests, ruff and the typecheck passing, and with a check on a device where it touches drawing
or memory. Tandem stays off until stage 2 picks it.

1. **Foundation.** Bring over the owned tree at its new paths: `openpilot/selfdrive/ui/tandem/` (component library,
   i18n, fonts module, design mocks, tools, tests) and `openpilot/starpilot/tandem/`, Figtree, JetBrains Mono and
   NotoSans-Fallback, `AGENTS.md` with the new paths, and the README's upstream table started fresh. Rework the font
   loading for Dom's runtime atlases, and redo the four text hooks (`KEEP_FONT`, `TEXT_SHAPERS`, the `text_measure.py`
   shapers, the `inputbox.py` font getter) on Dom's `application.py`. The lazy loading and atlas cropping from
   `idle-memory` don't carry over as written; measure Dom's font memory on a device first.
2. **Entry point.** Tandem sits on openpilot's original screens (`MainLayout`), as on `release`, and isn't offered as a
   choice next to StarPilot 7's UI: Tandem's point is fewer choices. The owner decided this on 2026-11-16. It needs one
   small hook where `ui.py` builds the layout, with `STARPILOT_UI=upstream` and Tandem's own switch still giving
   upstream's screens back.
3. **State.** Map what Tandem reads to Dom: `ui_state`, the services above, and each of the 119 missing params to its
   Dom key, document or owner, or to "dropped". Settings must write Dom's stores, not old keys. Keep the map in this
   file or a test, so a Dom merge that moves something fails a test.
4. **Screens**, each against its mock: home, onroad, alerts, then the settings tabs. StarPilot features that 7.0
   dropped lose their rows; new 7.0 features get mocks first.
5. **Services.** Routing (`starpilot/tandem/routing`, about 5,700 lines) against Dom's own offline routing
   (`starpilot/navigation/offline_owner.py`, `route_engine.py`) first, since 7.0 may make part of it unnecessary. Then
   Bluetooth (`starpilot/bluetooth/`), wheel controls (`starpilot/controllers/`), speed-limit vision memory
   (`starpilot/speed_limits/vision/`), the CAN recorder, radios and the network test.
6. **Fork-wide policies and workflows.** Statistics (`starpilot/analytics/`), `athenad.py`, `uploader.py`, `sentry.py`,
   the inert inherited workflows, and `release` in `RELEASE_BRANCHES` (now `openpilot/common/version.py`).

## Where each `release` hook goes

| `release` file | On `Dom` |
|---|---|
| `selfdrive/ui/ui.py` | Kept; picks the UI through `starpilot/ui/startup.py:select_ui` (stage 2) |
| `selfdrive/ui/layouts/main.py`, `home.py`, `settings/device.py` | Kept, much changed; only needed if Tandem sits on `MainLayout` |
| `selfdrive/ui/layouts/settings/starpilot/driving_model.py`, `vehicle.py` | Gone; settings are `starpilot/ui/*` |
| `selfdrive/ui/onroad/hud_renderer.py`, `model_renderer.py` | Kept, much changed |
| `selfdrive/ui/onroad/starpilot/starpilot_border.py`, `starpilot_onroad_view.py` | Gone; see `starpilot/ui/onroad*.py` |
| `selfdrive/ui/soundd.py` | Kept, much changed |
| `system/ui/lib/application.py`, `text_measure.py`, `system/ui/widgets/inputbox.py` | Kept; redo the hooks (stage 1) |
| `starpilot/assets/theme_manager.py`, `starpilot/system/the_galaxy/*` | Gone; see `starpilot/galaxy/` and `starpilot/ui/` |
| `starpilot/controls/starpilot_planner.py`, `lib/starpilot_vcruise.py` | Gone; see `starpilot/longitudinal/` |
| `starpilot/navigation/navigationd.py`, `starpilot/common/starpilot_functions.py` (maps) | Gone; see `starpilot/navigation/`, `starpilot/maps/` |
| `starpilot/system/bluetooth/daemon.py` | Gone; see `starpilot/bluetooth/` |
| `starpilot/system/wheel_controls/wheel_controlsd.py` | Gone; see `starpilot/controllers/` |
| `starpilot/system/speed_limit_vision.py` | Gone; see `starpilot/speed_limits/vision/` |
| `starpilot/system/starpilot_stats.py` | Gone; see `starpilot/analytics/` |
| `system/manager/process_config.py`, `system/athena/athenad.py`, `system/loggerd/uploader.py`, `system/sentry.py` | Kept |
| `system/version.py` | Gone; `openpilot/common/version.py` |
| `.github/workflows/*` | Dom has its own set; review in stage 6 |

## Stage 1: what was done

- The component library and what it needs (`tokens`, `layout`, `draw`, `controls`, `rows`, `blocks`, `chrome`, `overlays`,
  `base`, `scroll`, `fonts`, `i18n`, `arabic`, `thai`, `prefs`), the mocks, icons, translation catalog, font files and
  the tools that don't depend on unported screens. Raylib is StarPilot 7's binding (`openpilot.starpilot.ui.raylib`).
- Two upstream hooks again, in `application.py` and `text_measure.py` (README › Upstream integration). Upstream's UI
  tests give the same results with and without them. The `inputbox.py` font getter comes back with the keyboard.
- Figtree Regular is keyed on `FontWeight.NORMAL` (Inter Regular on the big UI); StarPilot 6's `ROMAN` is gone.
- `NotoSans-Fallback` rebuilt for StarPilot 7's languages (Vietnamese added) with `tools/bmfont.py`, StarPilot 6's
  `.fnt` generator, kept in Tandem's tools since StarPilot 7 no longer ships it.
- Not carried over: lazy Inter loading and freeing glyph images (README › Keeping merges easy). Measure on a device first.
- Checked by rendering `tools/render/scene_components.py` on both branches: the same apart from raylib 6's antialiasing,
  and Vietnamese, which `release` draws as "?".

## Stage 2: what was done

- `ui.py` wraps StarPilot's UI choice in `screens.ui_selection()`, and `layouts/main.py` imports `Sidebar` and
  `SIDEBAR_WIDTH` from `screens.py`: one line each (README › Upstream integration). Upstream's UI tests give the same
  results with and without them.
- The sidebar is ported, with its Maps row read from StarPilot 7's map manager (`starpilot/maps/operation_owner.py`)
  on a worker thread. It renders the same as on `release`.
- With Tandem on, home, settings and the onroad view are openpilot's until stage 4 ports them.
- **What StarPilot 7 runs only with its own UI**, and so isn't running with Tandem's screens until Tandem starts it: the
  controller runtime (wheel and controller buttons, favorites), the screen-off wheel poll, Android Auto bookmark and
  speed limit actions, the Galaxy layout preview, SpacePilot's game mode and the projection features. `ui.py` starts
  them only beside `StarMainLayout` (`layout.star`). This is the same as StarPilot's own `STARPILOT_UI=upstream`
  recovery mode. Stage 5 decides which Tandem keeps and how it starts them without StarPilot's layout.
- Not checked on a device: this Mac can't load StarPilot 7's msgq and params builds, so `MainLayout` itself wasn't run.
  The real `Sidebar` subclass was built and checked over a stand-in `ui_state`.

## Tests still on `release` only

Ported so far: `test_fallback_font.py`, the component tests of `test_tandem.py`, the catalog-mechanics tests of
`test_translations.py`, the atlas crop tests of `test_font_loading.py`, and the text hook test of
`test_upstream_integration.py`. Each of the rest comes back with the code it tests. When one comes back, take it from `release` whole.

| `release` test | Waits for |
|---|---|
| `test_tandem.py` from `test_traffic_chip_only_while_braking...` on | Onroad, home and settings screens (stage 4) |
| `test_translations.py`: the template, metadata, coverage and completed-language checks, Developer View labels, picker languages | Every screen ported, then `tools/translations.py update` (end of stage 4) |
| `test_font_loading.py`: lazy fonts, glyph release and alert faces | Lazy fonts and glyph release if they come back; alert faces with onroad alerts (stage 4) |
| `test_upstream_integration.py`: all but the text hooks and the sidebar factory | Their hooks and modules (stages 3 to 6) |
| `test_larger_text.py` (the size tests and the menu sidebar test are ported, in `test_screens.py`), `test_bar.py`, `test_compass.py`, `test_streets.py`, `test_turn_signals.py`, `test_lead_tag.py`, `test_onroad*.py`, `test_alert_levels.py`, `test_chip_events.py`, `test_headroom_warning.py`, `test_limit_follower.py`, `test_limit_offers.py`, `test_developer_view.py` | Onroad (stage 4) |
| `test_home_layout.py`, `test_forecast.py`, `test_menu_idle.py`, `test_ram.py`, `test_keyboard.py`, `test_voice.py`, `test_speech_native.py` | Home, sidebar and keyboard (stage 4) |
| `test_settings.py`, `test_developer.py`, `test_software_dialogs.py`, `test_hotspot_name.py`, `test_network_touches.py`, `test_storage_sizes.py`, `test_prebuilt_params.py` | Settings (stages 3 and 4) |
| `test_destinations.py`, `test_routemap.py`, `test_routing_ui.py`, `test_map_progress.py` | Navigation and routing (stage 5) |
| `test_bluetooth_*.py`, `test_remote_actions.py`, `test_can_recorder.py`, `test_obd.py`, `test_cellular_status.py`, `test_network_test.py`, `test_galaxy_signals.py` | Services (stage 5) |
| `test_workflow_policy.py` | Workflows (stage 6) |
| `starpilot/tandem/tests/` | The services they test (stage 5) |
