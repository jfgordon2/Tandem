# Porting Tandem to StarPilot 7.0

`development` starts as upstream's `Dom` branch (StarPilot 7.0) at 1abbbc6d19, unchanged. Tandem is ported onto it in
stages. Until a stage is done, `development` boots as stock StarPilot 7.0.

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
2. **Entry point.** Decide where Tandem sits: in place of `StarMainLayout` as a third choice in `select_ui`, or over
   upstream's `MainLayout` as on `release`. Either way one small hook, with `STARPILOT_UI=upstream` and Tandem's own
   switch still giving their screens back.
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
