# Porting Tandem to StarPilot 7.0

`development` starts as upstream's `Dom` branch (StarPilot 7.0) at 1abbbc6d19. Tandem is ported onto it in stages. Until
stage 2 is done, `development` boots as stock StarPilot 7.0.

| Stage | State |
|---|---|
| 1. Foundation | Done; see below |
| 2. Entry point | Done; see below |
| 3. State | Mapped and covered by contract tests |
| 4. Screens | Done: every release screen, the driving screen and its chips |
| 5. Services | Done: navigation, Valhalla routing and Offline Maps, Bluetooth, the CAN recorder, radios, network test |
| 6. Fork-wide policies | Diagnostics, uploads, statistics, athenad, workflows and translations done; `RELEASE_BRANCHES` is the owner's call |

## Decisions for the rest of the port (owner, 2026-11-16)

- **Offline routing:** port Tandem's Valhalla routing as a provider inside StarPilot 7's navigation, keeping Offline maps
  only and Online / Offline. It goes last.
- **Wheel buttons, favorites, Android Auto actions:** Tandem starts StarPilot 7's controller runtime with its own screens;
  release's Bluetooth Remote screen sets buttons through StarPilot's owners. Release's own wheel service isn't ported.
- **Settings StarPilot 7 dropped:** their rows are left out; rows whose meaning changed use StarPilot 7's owners (the param
  map below). Nothing dropped is rebuilt in Tandem.
- **Driving Style:** Relaxed = Relaxed personality with Comfort acceleration and braking; Standard = Standard with StarPilot
  Default for both; Sport = Aggressive with Sport for both (StarPilot 7's `profile:global_acceleration` and
  `profile:global_braking`).
- **Smart Slowdowns:** on = Driving Mode Automatic and the Curve Speed Controller on; off = Chill and the controller off.
- **MAX follows limits stays:** when it's on and the car is engaged on StarPilot's own cruise, each newly accepted limit
  is adopted once through StarPilot's adopt action (`SlcActionKind.ADOPT`), which moves SET to the adjusted limit. Where the
  car's cruise owns SET, StarPilot can't move it, and the row says so. StarPilot 7 already keeps the car under each
  accepted limit plus offset whatever SET is.
- **Gone with StarPilot 7:** Vehicle Profile's EV and Towing (truck tuning is GM-only and shows with that car's options),
  Weather's driving presets (Weather heads-up stays).
- **Languages:** Tandem's picker is StarPilot 7's list plus Arabic. Every language, Vietnamese included, is translated
  in full (owner, 2026-11-19: "Translate everything").

Order: Connections; the Driving tab; Device's remaining pieces and settings search; the rest of the driving screen; Home's
navigation pieces and first-run setup; StarPilot's controller runtime and the services; Valhalla routing; fork-wide
policies, workflows and the translation catalog.

## Why a port and not a merge

`Dom` has no history in common with `release`. It is rebuilt on openpilot's full history, so `git merge` refuses it
("unrelated histories"). It is also a different codebase, not a newer copy of the one Tandem hooks into:

- All code moved under `openpilot/`. Import paths stay the same (`openpilot.selfdrive...`), file paths don't.
- Params went from 802 keys to 396. Tandem uses 236 params; 119 of them are gone, including `IsOnroad`. Many settings
  now live in StarPilot's own documents and owners (`starpilot/*/profile_document.py`, `offset_document.py`,
  `saved_document.py`) instead of params.
- StarPilot's UI was rewritten as `openpilot/starpilot/ui/` (`StarMainLayout`), picked in `ui.py` by
  `starpilot/ui/startup.py:select_ui`. The old `selfdrive/ui/layouts/settings/starpilot/` and
  `selfdrive/ui/onroad/starpilot/` are gone.
- Fonts are TTF files rendered into atlases at startup (`load_font_ex` at size 200), not prebuilt `.fnt` atlases.
- 21 of the 36 upstream files Tandem edits on `release` no longer exist, and 15 of the 37 StarPilot modules Tandem
  imports are gone. The files that remain changed a lot (`application.py` -644/+259 lines, `ui_state.py` -349/+454,
  `soundd.py` -443/+190, `model_renderer.py` -789/+248).
- Dom replaced three of the 22 message services Tandem reads. The [service map](#cereal-services) covers
  `starpilotPlan`, `liveDelay` and `liveParameters` field by field.

`Dom` was moving fast when this was written (439 commits in a week, against 5 on `StarPilot`), and its README calls it a
development branch with migration still in progress.

## How `development` follows upstream

- `development` merges `upstream/testing` the usual way. Upstream finished `Dom` on 2026-11-17 and moved it to
  `testing`, which continues Dom's history, so those merges are ordinary. `development` merged Dom's last commit first.
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
   shapers, the `inputbox.py` font getter) on Dom's `application.py`. Carry forward the cropped Figtree atlases
   and restore CPU glyph image release for GPU-drawn fonts. See the [device measurements](#font-memory-on-the-comma).
2. **Entry point.** Tandem sits on openpilot's original screens (`MainLayout`), as on `release`, and isn't offered as a
   choice next to StarPilot 7's UI: Tandem's point is fewer choices. The owner decided this on 2026-11-16. It needs one
   small hook where `ui.py` builds the layout, with `STARPILOT_UI=upstream` and Tandem's own switch still giving
   upstream's screens back.
3. **State.** Map UI state, cereal services and missing Params to Dom's fields and owners. The
   [state contracts](#stage-3-state-and-settings-contracts) specify where ported screens read and write settings.
   The contract tests flag changes when Dom moves those dependencies.
4. **Screens**, each against its mock: home, onroad, alerts, then the settings tabs. StarPilot features that 7.0
   dropped lose their rows. New 7.0 features get mocks first. Defer Inter font requests until the ported screens
   need them. Recheck which weights load at boot and verify that alert fonts are ready before driving.
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
- The cropped Figtree atlases carried over from `release`.
- Checked by rendering `tools/render/scene_components.py` on both branches: the same apart from raylib 6's antialiasing,
  and Vietnamese, which `release` draws as "?".

### Font memory on the comma

On the parked comma 3X running `development` at `874f5c6e` with AGNOS 20.5.2, the live Tandem UI reported **133 MiB**
of GPU allocations and a process-lifetime peak of **186 MiB**. In a separate GPU context on the same device,
the production font loader for the English large-screen UI allocated **86 MiB** for the four Inter atlases,
about **21.5 MiB per weight**.

- **Restore CPU glyph image release.** Freeing the CPU glyph images after texture upload reclaimed **26.7 MiB of
  RAM** in the isolated test. GPU allocations stayed steady, and the rendered English text sample matched
  pixel for pixel. Scope the release to fonts used exclusively for GPU drawing so raylib can still draw CPU image
  text where needed. Recheck memory and rendered text on the device after integration.
- **Defer lazy Inter loading to stage 4.** The [HUD renderer](../onroad/hud_renderer.py) and
  [alert renderer](../onroad/alert_renderer.py) request all four weights during startup. Making just the loader
  lazy would leave those allocations in place. Each weight the port can defer saves about **21.5 MiB of GPU
  allocations** while it stays unloaded.

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
- The Mac check built and rendered the real `Sidebar` subclass over a stand-in `ui_state`. `MainLayout` later ran
  on the parked comma during the [font memory check](#font-memory-on-the-comma).

## Stage 3: state and settings contracts

This inventory compares registered keys and service names referenced by string literals in production Python under
Tandem's two owned trees on `release` at `a4dbe5bcc6` with `development` at `874f5c6eee`. It covers 236 Params and 22
cereal services. [The contract test](tests/test_porting_state.py) checks
the current registry, cereal fields and owner entry points against this map. Stage 4 connects the screen callers.
Stage 5 connects the service callers. Keep settings labels and availability tied to the owners' snapshots and use their
validated actions with the revision or expected saved value and the same parked or vehicle checks upstream uses.

### UI state

| Release dependency | StarPilot 7 source |
|---|---|
| `started`, `ignition`, `started_frame`, `engaged`, `is_metric`, `CP`, `is_offroad()`, `add_offroad_transition_callback()`, `prime_state` | Same concepts on [UIState](../ui_state.py). Bind the UI to its state and transitions. Use a qualified parked sample for vehicle-sensitive actions that allow Park while the UI is onroad. |
| `ui_params` | `UIState.params` is typed Params and can be read-only in projection. Read settings via the upstream owners below. Refresh outside per-frame rendering and preserve projection/replay permission checks. |
| `params_memory` | Use the service or owner for each old mailbox in the [param map](#missing-params). Unchanged Param names can still have a different type or lifecycle. |
| `starpilot_toggles` | No aggregate dict. Read display choices via `onroad_appearance()` and `read_customization()`, steering pause through `PauseLateralSpeed` and `PauseLateralOnSignal` via `FeatureSettingsOwner`, and live activity from the messages below. |
| `always_on_lateral_active` | Reuse the [runtime snapshot](../../../starpilot/ui/runtime_snapshot.py) handling of the qualified AOL latch and active lateral output. Use `display_aol_latch()` for the armed display state, and keep armed and active distinct. |
| Vehicle in Park / stationary | [`ParkedVehicleReader`](../../../starpilot/parked_vehicle.py) qualifies current CAN state and dwell. The map owner and the other write owners enforce their own admission. |
| Reads of `sm.valid` and `recv_frame` alone | Reuse the StarPilot 7 display paths' validity, freshness, drive-transition and replay clock checks. `current_message()` is for action freshness, `display_message()` is for high-rate display data, and slow or sparse services use their own qualifications. |

### Cereal services

The first table covers all 22 release services. The current [UIState](../ui_state.py) subscriptions cover most UI
inputs. Subscribe in an owned consumer when the table calls for a feed that UIState does not subscribe to. Attach
any new consumer at its screen or service entry point.

| Release service | StarPilot 7 read or action path |
|---|---|
| `can` | Retained. The CAN recorder owns its subscriber. |
| `carControl`, `carOutput`, `carState`, `controlsState` | Retained on UIState. Read actuation, motion, cruise and steering through current samples. Use `carState.vCruiseCluster` for displayed SET in km/h. |
| `deviceState`, `driverStateV2` | Retained on UIState for device health, connectivity and driver camera. |
| `gpsLocationExternal` | Retained on UIState with `gpsLocation`. Follow [StarPilot GPS selection](../../../starpilot/gps/source.py) for a qualified fix. |
| `liveDelay` | `lateralDelay.lateralDelay` in seconds. `LiveDelay` still exists as a persisted BYTES Param for the estimator. |
| `liveParameters` | `vehicleParameters.steerRatio`. Use the current result with `valid` and `steerRatioValid` for a learned ratio. |
| `mapdExtendedOut` | Retained for mapd reporting. Replace legacy download progress with `MapSnapshotOperationOwner` status. |
| `mapdOut` | Retained, outside UIState. Follow [the onroad map](../../../starpilot/ui/onroad_map.py) for its own subscriber and `roadName` / `wayName` display. |
| `modelV2`, `radarState` | Retained on UIState, including lane-change meta. Use `radarState.leadOne.present` for lead presence. The upstream conditional-lead UI helper still reads the legacy `status` field at this baseline. |
| `navInstruction` | Retained for official nav. Prefer qualified `starpilotNavigation.navigation` through `navigation_display()`. Use `official_navigation_display()` with `navInstruction`, `navRoute` and `NavDestination` for official nav. |
| `pandaStates` | Retained. Use the boot-clock-aware `current_message()` for UI readiness. Preserve the recorder's own subscription. |
| `rawAudioData` | Retained on UIState. Speech can use its own mic subscription as on release. |
| `selfdriveState`, `starpilotSelfdriveState` | Both retained. Use `current_alert()` for alert size, text and type and `onroadEvents` for current event names. |
| `starpilotCarState` | Retained on UIState for pause, coast, pulse-and-glide and vehicle diagnostics. Use qualified AOL state for steering authority and the parked owner for settings admission. |
| `starpilotPlan` | Replaced by the sources below. `customReserved6` and the legacy replay shim are for historical logs. |
| `starpilotRadarState` | Retained outside UIState. Use the current `leadLeft` / `leadRight` for adjacent leads and the upstream qualification for adjacent-stop observations. |

| Release `starpilotPlan` fields | StarPilot 7 source |
|---|---|
| `accelerationJerk`, `dangerFactor`, `laneWidthLeft`, `laneWidthRight` | Omit these legacy diagnostics. `modelV2.laneLines` supports drawing lane geometry, with no equivalent left/right width metric published. |
| `cscControllingSpeed`, `cscSpeed` | Qualified `slcState.curve` via `current_curve_message()` and `curve_observation()`. Use `controlling` and qualified `ceilingMps`. |
| `forcingStop`, `redLight` | `starpilotLongitudinalPlan.forceStopHolding` / `forceStopBraking` describe qualified stop behavior via [the force-stop consumer](../../../starpilot/longitudinal/force_stop_alert.py). Consume the native alert for its meaning. Holding or braking alone does not identify a red light. |
| `forcingStopLength`, `stopSignConfirmed` | No equivalent qualified stop distance. Use the native stop-sign advisory path in the runtime snapshot. |
| `experimentalMode`, `trackingLead` | `selfdriveState.experimentalMode` and `radarState.leadOne.present` for the individual values. A tracked lead alone gives no planner reason to assert that it is slowing the car. |
| `lateralCheck` | Use qualified AOL status and `carControl.latActive` for steering output. Steering held runs StarPilot's own Pause steering rule (`starpilot/lateral/pause.py`) and shows only while `latActive` is off. |
| `pulseGlideCoasting` | No equivalent planner bit. `starpilotCarState.pulseAndGlide` and `forceCoast` remain separate indications. |
| `slcIsLimitingMaxSet`, `slcSpeedLimitOffset`, `slcSpeedLimit`, `slcSpeedLimitSource`, `slcPresentedSpeedLimitSource` | Read `slcState` via the runtime snapshot. Use `isLimitingMaxSet`, `offset`, and qualified accepted / pending / observed speed and source. Use the matching `*AdjustedLimit` when its presence flag is true. Speed and offsets are m/s. |
| `speedLimitChanged`, `unconfirmedSlcSpeedLimit`, `slcOverriddenSpeed` | Read the pending decision, `pendingSinceMonoTime`, `decisionId`, `presentationId` and `driverOverrideActive`. Reuse the upstream speed-limit observation for display and `SlcActionDispatcher` for Accept, Reject and Adopt. The planner owns the actual SET response. |
| `starpilotEvents` | Current `onroadEvents.name` and the qualified alert path. Departure advisories have original-source timestamps on `starpilotLongitudinalPlan`. Keep the alert epoch and clear stale presentation on transition. |
| `vCruise` | `carState.vCruiseCluster` describes SET. Use upstream's qualified navigation guidance and [intent](../../../starpilot/navigation/intent.py) for route-specific feedback. The legacy planner target comparison has no direct replacement. |
| `weatherId` | Weather display uses qualified location via the StarPilot 7 or Tandem forecast service. Drop weather-dependent gap tuning. |

### Missing Params

A dropped entry has no equivalent for the old control or data contract. Its screen can omit the old row when ported.
Some StarPilot 7 features cover part of the old UI through an owner with a different meaning.

| Release Params | StarPilot 7 disposition |
|---|---|
| `AccelerationPath`, `PathColor`, `PathEdgeWidth`, `PathWidth`, `LaneLinesWidth`, `DynamicPathWidth` | Use `OnroadCustomizations` and `OnroadLayoutOwner.save()` for supported path modes and colors. Drop legacy width knobs. |
| `AccelerationProfile`, `DecelerationProfile`, `AdvancedLongitudinalTune`, `IncreasedStoppedDistance` | `FeatureSettingsOwner` and `LongitudinalPersonalityProfiles`. Use selected acceleration / braking presets and `extraStoppedGapM`. Drop the tuning master switch. Use the owner's named choices and SI units. |
| `AdjacentPath`, `AdjacentPathMetrics`, `DeveloperMetrics`, `DeveloperWidgets`, `FPSCounter`, `NumericalTemp`, `ShowCPU`, `ShowGPU`, `ShowMemoryUsage`, `RadarTracksUI` | Drop the legacy switches. Port Tandem's Developer View using `DeveloperUI` / `DeveloperSidebar` and its owned strip preference, with available Dom metrics. Keep adjacent lead data separate from old adjacent-path settings. |
| `AdvancedCustomUI`, `CustomUI`, `ModelUI`, `NavigationUI`, `QOLVisuals`, `HideDistanceProfileBanner` | Drop the master switches and old banner flag. Use the relevant appearance owner and `OnroadCustomizations` for supported widget choices, including the following distance or driving mode widgets. |
| `AlertVolumeControl`, `BelowSteerSpeedVolume` | `SoundsOwner` exposes individual supported volume settings. Drop the group flag and dedicated below-steer-speed volume. Keep the upstream alert policy. |
| `AutomaticUpdates` | `UpdaterAutomaticDownloads` via `SoftwareOperations` `preferences` action. Read automatic install scheduling and the global `DisableUpdates` gate independently. |
| `AutomaticallyDownloadModels` | Drop the legacy automatic catalog toggle. Use `ModelManager.snapshot()` and its guarded `action()`. |
| `BlindSpotPath` | Drop legacy path shading. `AppearanceOwner` exposes the supported blind-spot border. For vision warnings follow `PiPWarningSource`'s freshness handling of `spotMonitorState`; retain native car blind-spot status separately. |
| `BootLogo`, `StartupMessageTop`, `StartupMessageBottom` | Dropped. Use the StarPilot 7 startup screen and alert owners. |
| `CECurves`, `CELead`, `CESlowerLead`, `CEStopLights`, `CEStoppedLead`, `ConditionalChill`, `ConditionalExperimental` | `ConditionalModeConfig` via `ConditionalFeature`. Use CEM / CCM / stock modes and `cem.curves`, `lead`, `slower_lead`, `stop_lights`, `stopped_lead` options. The upstream legacy-adoption helper produces a preview that requires explicit adoption. |
| `CancelDownloadMaps`, `DownloadMaps`, `LastMapsUpdate`, `MapsDownloadProgress`, `MapsDownloadSizeCache`, `MapsSelected`, `PreferredSchedule` | `MapSnapshotOperationOwner` through `request_operation()` for catalog, status, start and cancel. Use the operation ID and selected generation. Offline navigation areas use `OfflineMapsOwner`. The map snapshot protocol has no equivalent weekly/monthly schedule or set of legacy cache flags. Resolve scheduled updates in stage 5. |
| `CarMake`, `CarModel`, `CarModelName`, `ForceFingerprint` | `VehicleSelectionOwner` with `VehicleSelection` for a manual override or Auto. Use the active `CarParams` fingerprint and platform metadata for the detected vehicle. |
| `ClearNavOnOffroad`, `FavoriteDestinations`, `MapboxPublicKey`, `MapboxSecretKey` | `NavigationOwner` owns route lifecycle, favorites and the supported provider credentials. Use its revision-bound actions. The Dom Mapbox token is a public token. The legacy clear-on-offroad switch has no replacement. |
| `Compass` | No Dom key. Use a Tandem-owned preference for the Essentials compass with qualified GPS heading. |
| `CustomThemes`, `HolidayThemes`, `RandomThemes`, `SignalAnimation` | Drop the old theme and pack controls. Use Dom appearance preferences for supported native signal indicators. |
| `DisableOnroadUploads`, `NoUploads` | No exact equivalents. `AlwaysAllowUploads` permits metered uploads and does not implement either privacy policy. Omit the legacy choices until the uploader policy is ported in stage 6. |
| `DiscordUsername`, `IssueReported` | Drop the saved identity and report marker. Galaxy's `StarPortLogSender` accepts an optional Discord username per explicit report. |
| `DynamicPedalsOnUI`, `StaticPedalsOnUI` | Drop the two legacy pedal modes. `AppearanceOwner` exposes the supported wheel brake/acceleration feedback through `ShowBrakeStatus` and `PedalsOnUI`. |
| `ForceTorqueController`, `LateralTune`, `NNFF`, `NNFFLite` | `LateralControllerSelection` and `SteeringLearningPreferences` through `FeatureSettingsOwner`. Show choices for the active platform. Drop the old controller modes and master switch. |
| `GMDashSpoofOffsets`, `LockDoorsTimer`, `SubaruSNGManualParkingBrake` | Dropped. The retained lock/unlock and Subaru SNG switches have separate meanings. |
| `IsOnroad` | UI uses `UIState.is_onroad()`. A background owner can use explicit `IsOffroad` and its activity checks. Missing or unreadable state does not authorize parked work. |
| `LaneChanges`, `MinimumLaneChangeSpeed`, `NudgelessLaneChange` | `LaneChangeFeature` writes `LaneChangePreferences` with enabled, minimum speed in m/s and automatic lane-change options. |
| `LeadDetectionThreshold`, `RadarTakeoffs`, `TrailerLoad` | Dropped. Use Dom's qualified lead observations and native longitudinal behavior. |
| `LongitudinalActuatorDelay`, `LongitudinalActuatorDelayStock`, `StartAccel`, `StartAccelStock`, `StopAccel`, `StopAccelStock`, `StoppingDecelRate`, `StoppingDecelRateStock` | Drop the generic tuning overrides and stock shadows. New settings use the upstream vehicle and longitudinal profile owners. |
| `MaxDesiredAcceleration` | Use the selected acceleration profile. The vehicle-specific `LongitudinalMaxOutputAcceleration` is an output limit with a different scope. |
| `NavInstructionState` | Use `starpilotNavigation` and the native rendering path, plus the official-nav fallback. Drop the legacy shared-memory JSON. |
| `Offroad_ChestnutUncompiled` | Use `UIState.chestnut_state` for readiness and the current Chestnut/model alerts for actual alerts. |
| `Offroad_IsTakingSnapshot`, `Offroad_NeosUpdate` | Drop the snapshot alert. Use `UpdaterOSUpdate` via the software owner for OS update status. |
| `SLCConfirmationHigher`, `SLCConfirmationLower` | `SLCConfirmation` is an integer choice via `FeatureSettingsOwner`: 0 off, 1 both, 3 higher only, 4 lower only. |
| `SLCForceCruiseSpeed`, `SpeedLimitAccepted` | Use the planner's current `slcState` and state-bound `slcAction` via `SlcActionDispatcher`. Omit the old direct SET mailbox and acceptance bit. |
| `SLCMapboxFiller`, `SpeedLimitSources`, `SpeedLimitChangedAlert` | Use the native SLC source priority settings and live `sourceReadings`. Drop the Mapbox filler, old diagnostic switch and dedicated limit-change chime setting. |
| `ScreenManagement`, `StandbyMode` | `DisplayOwner` owns display preferences, including `StarPilotDisplayPreferencesEnabled`, brightness, timeout and `TurnOffCommaScreen`. The old standby flag has no equivalent. |
| `SentryModeEnabled`, `SentryModeSensitivity` | `SentryOwner` writes `SentryMotionPreferences` using its named sensitivity choices and parked checks. |
| `SetSpeedLimit` | `SLCOnEngage` via `FeatureSettingsOwner` for setting initial cruise from the limit. Keep it distinct from enabling `SpeedLimitController`. |
| `ShowStoppingPoint`, `ShowStoppingPointMetrics` | Dropped with the old distance feed. Display the native stop advisory when qualified. |
| `SteerDelay`, `SteerDelayStock`, `SteerKP`, `SteerKPStock`, `UseAutoSteerDelay` | Read live `lateralDelay` for diagnostics. For supported manual torque gain use `GainFeature` and `TorqueOverrideDocument`. Drop generic override fields and stock shadows. |
| `TestAlert`, `WheelControlTestActive` | Drop the Param mailboxes. Connect alert previews and controller actions to their StarPilot 7 runtime owners when those screens port. |
| `TuningLevel`, `TuningLevelConfirmed` | Dropped. Use each setting's owner and its capability and admission checks. |
| `UseVienna` | `onroad_appearance()` has a bounded compatibility read of the old file. Drop the edit switch unless a supported Dom writer is added. |
| `WeatherPresets` | Drop weather-dependent following-distance tuning. Weather display is independent. |

### Retained Params

These release keys are still registered in Dom. Registration alone gives no write permission or semantic equivalence.
`SLCConfirmation` moved from BOOL to INT, `NavDestination` from STRING to JSON and `LastGPSPosition` from STRING to BYTES.
Use the typed owner for each. Upstream retirement folds `AdvancedLateralTune`, `QOLLongitudinal`, and `RainbowPath`
into its current settings and layout. Use `SLCOffsetSchedule` via `FeatureSettingsOwner` for speed-limit offsets, and
`TorqueOverrideDocument` for supported torque edits, including when the old torque fields remain registered.

```text
AdbEnabled AdvancedLateralTune AggressiveFollow AlphaLongitudinalEnabled AlwaysOnDM AlwaysOnLateral BlindSpotMetrics
CalibrationParams CameraView CancelButtonControl CarParamsPersistent CurveSpeedController CustomCruise
CustomPersonalities DeveloperSidebar DeveloperUI DisableOpenpilotLongitudinal DisengageOnAccelerator DisengageVolume
DistanceButtonControl DoUninstall DongleId DriverCamera EVTuning EngageVolume ExperimentalMode ForceStops
GMPedalLongitudinal GitBranch GithubSshKeys GithubUsername GreenLightAlert GsmApn GsmMetered GsmRoaming
HKGRemoteStartBootsComma HardwareSerial IgnoreIgnitionLine IsLdwEnabled IsMetric IsOffroad JeepBrakeHold
JoystickDebugMode LKASButtonControl LanguageSetting LastGPSPosition LeadDepartingAlert LeadInfo LockDoors
LongDistanceButtonControl LongitudinalManeuverMode LongitudinalPersonality LoudBlindspotAlert
MainCruiseButtonControl ModeButtonControl NavDestination NostalgiaMode Offroad_CarUnrecognized
Offroad_ChestnutNotDetected Offroad_ChestnutOverheated Offroad_ChestnutPcieUnavailable Offroad_ChestnutUpdateFailed
Offroad_ChestnutUsbSlow Offroad_ConnectivityNeeded Offroad_ConnectivityNeededPrompt
Offroad_DriverMonitoringUncertain Offroad_ExcessiveActuation Offroad_Recalibration Offroad_TemperatureTooHigh
Offroad_UnregisteredHardware Offroad_UpdateFailed OnroadCycleRequested OpenpilotEnabledToggle PedalsOnUI
PromptDistractedVolume PromptVolume QOLLongitudinal RainbowPath RecordAudio RecordFront RecordFrontLock RefuseVolume
RelaxedFollow RemapCancelToDistance RemoteStartBootsComma SLCConfirmation SNGHack SafeMode ScreenBrightness
ScreenBrightnessOnroad ShowDebugInfo ShowSpeedLimits SignalMetrics SpeedLimitController SshEnabled StandardFollow
StarButtonControl SteerFriction SteerFrictionStock SteerLatAccel SteerLatAccelStock SubaruSNG TrafficFollow
TruckTuning UnlockDoors UpdateAvailable UpdateFailedCount UpdaterAvailableBranches UpdaterCurrentDescription
UpdaterCurrentReleaseNotes UpdaterFetchAvailable UpdaterNewDescription UpdaterState UpdaterTargetBranch VoltSNG
WarningImmediateVolume WarningSoftVolume
```

## Stage 4: parked Home

- The six approved Home variants are in `design/stage4-home*.html`. `TANDEM_HOME=0` gives openpilot's original Home.
  Native terms and training still open through `MainLayout`. Pairing and Firehose remain available in native Settings.
- Software opens the ported Software panel. A qualified staged update opens its notes and uses StarPilot's
  revision-bound install request. The schedule note uses the owner's next scheduled restart. StarPilot's offroad alert
  widget still supplies active alerts, priority, Snooze update, and Acknowledge excessive actuation.
- Home shows weather from the current validated fix or StarPilot's last recorded navigation location. The forecast
  cache and temperature unit preference carry forward. The onroad weather chip and chime return with onroad.
- Where to? is back beside Software (as in `home.html`), on StarPilot 7's navigation owner (stage 5). The Tandem setup
  choices and settings remain to port.

## Stage 4: driving screen

- Release's drawing and chip rules carry over whole: `onroad/layers.py` (bar, chips, steering arc, Help steer, new-limit
  card, speed, sign, driver monitor tile), `onroad/status.py` (which chips show, their order and hold) and
  `onroad/alerts.py` (the three alert levels). Only StarPilot 7's needs changed them: a missing speed draws "–", the
  arc's round ends are triangle fans (raylib 6 has no circle sectors), chips stop at the road view's width, and the
  bar's MAX − / + and wheel follow StarPilot's permissions (`BarState.can_adjust`, `can_disengage`).
- `onroad/view.py` is StarPilot 7's: openpilot's camera and model view, StarPilot's runtime snapshot, its selected
  alert and its action publishers. It fills release's state objects once a frame. The pure choices (which alert shows,
  the new-limit offer, the model's lane change) are in `onroad/binding.py`, tested off the device.
- MAX adjustments, disengage and speed-limit answers go through StarPilot's qualified publishers; the screen can't
  engage. A card answers only the proposal it showed. A critical alert closes the sidebar and takes the screen.
- Chips from StarPilot 7 so far: steering and speed pauses, coasting, pulse and glide, lane changes and blocked lane
  changes, curves, green light, car ahead moved, ready to resume, steering only, turns, Low on RAM, and (stage 8) the
  rest: stopping and stopping for a stop sign, slowing for traffic, steering held and Matching limit, from the sources
  under "Stage 8: the planner chips". Help steer shows and replaces the steering-limit alert; its chime waits for the headroom service
  (stage 5).
- Navigation (stage 5): the turn card, ARRIVE and LEFT, End route and the bar's Where to? read StarPilot's guidance
  (`OnroadState.navigation`); Slowing for turn asks StarPilot's own turn speed rule (`navigation/intent.py`) with the set
  speed, since the planner doesn't publish it. The comparison page uses release's `onroad`,
  `onroadlarge-limit`, `alertstyles` and `memorychip` mocks.

## Stage 4: Software

- Release's Software tab (`design/softwaretab.html`) in release's settings window, on StarPilot 7's software owner.
  Home and the tab share one watch (`tandem/software.py`), which reads the owner on a worker thread and sends every
  action with the revision the driver saw.
- Automatic Updates is one switch, as on release: it turns StarPilot's automatic downloads and automatic installation
  on or off together, keeping the saved restart schedule and time zone (or the owner's default when none was saved).
  Its subtitle says "Download and install while parked", since StarPilot 7 installs at a restart while parked.
- Release Channel shows the branch; choosing another opens in Tuner Mode, which isn't ported yet. Reset Settings is
  inactive until the Essentials defaults port. Uninstall asks once and sets `DoUninstall`, as StarPilot 7's own panel
  does: StarPilot 7 has no factory-reset step, and clearing params wouldn't erase the settings it keeps elsewhere.

## Stage 4: match the release Settings layout

- Use the running `release` UI at `a4dbe5bcc6` as the visual reference. It has four bottom tabs (Driving, Device,
  Connections, Software), independent page stacks, a back or close button, and a separate section rail inside Device.
  MainLayout uses the four-tab window. Unported screens use openpilot’s panels in that window.
- Port the presentation from `settings/window.py`, `settings/pages.py`, and the Device sections on `release`. This Device
  keeps Phone App, Remote Access, Camera Calibration, How It Works, the lower identity rows and the pinned power buttons.
  General keeps language, and Driving › Assistance keeps the driver camera and driver monitoring reset. The Device
  section order is This Device, General, Backups, Storage & Data, RAM when snapshots exist, Report a Problem,
  and Developer when Tuner Mode is on. Release page captures are authoritative where the older HTML differs.
- Keep the release screens and dialogs backed by current owners. Use the active provider and native token flow for
  Phone App, Galaxy Access for Remote Access, the cache schema and `calibration_reset` for calibration, and recheck
  vehicle admission when confirming power and calibration. General uses the localization and display owners. The
  backup, storage and report screens need adapters for ToggleBackup, the snapshot and model owners, and StarPort log
  sending. RAM needs the drive snapshots as well as the existing chip. Preserve the recovery switch.
- Host preview checked This Device in the parked, paired, engaged, calibrating, and scrolled states, plus Phone App
  pairing. Each matched its release capture pixel for pixel at 2160 × 1080. The three confirmation dialogs matched
  the release positions, controls and wording, with small raster differences. The Remote Access render
  also matched its layout with small raster differences. Host renders use sample data.
  End-to-end wiring and checks on the comma are pending.
- The release Settings navigation and This Device are connected through MainLayout. Phone App uses the native token
  flow. Remote Access uses the native Galaxy owner and keyboard. Driving and Connections still host the native panels.
  Carry forward the release General, Backups, Storage & Data, Report and Developer widgets as their owner adapters land.

## Stage 4: Device › General and the Device rail

- Reuse the approved release Device screens and the release General row order, wording, controls and Language sheet.
  Use the running release captures for comparison where the older HTML differs. The native language catalog includes
  Vietnamese. The units action keeps the physical speed-limit offsets. Temperature still uses Tandem’s forecast
  preference. Presets use StarPilot 7’s parked and driving brightness values and Standby uses its screen-off switch.
- General, Backups, Storage & Data, RAM, Report a Problem and conditional Developer are mounted on the release
  Device rail. Native onboarding opens Firehose via a separate Settings page. RAM appears after the first snapshot.
  Developer and Release Channel use the same saved Tuner Mode presentation flag.
- Report a Problem sends the release category, details, optional Discord name and RAM summaries through StarPilot's
  manual issue project using the existing acknowledged Bugsink transport. The release keyboard is used for text entry. Developer uses the native toggle and SSH owners. CAN recording is stage 5.
- The approved Delete offline maps dialog covers managed road snapshots, native navigation tiles, and downloaded
  packages from release. Data removal uses the map admission lock and the tile writer's acknowledgement. Region
  selections stay in place. A host check ran the map owner and tile writer against temporary map stores and verified
  the parked, active-route, stale-selection and admission-lock guards. The parked comma still runs an earlier
  development checkout. It has both native services and roughly 1.1 GiB of release maps. The live files were left in place.
  Porting the routing service and its download screens remains stage 5.

## Stage 4: keyboard

- Reused release’s keyboard, voice panel, speech workers and tests. The native InputBox still owns cursor positioning,
  editing and password masking. The only hook is its font getter. Passwords use the approved release keyboard.

## Stage 4: native font loading

- With Tandem active on the big UI, Inter Medium and SemiBold load on first use. Tandem's subclasses skip the
  unused native HUD and sidebar fonts. Inter Regular, Bold, Unifont and the selected language fallback are ready
  at startup. Inter keeps its atlas and metrics and releases its CPU glyph images after each texture upload.
  A host render kept identical text pixels and metrics after releasing the glyphs twice and unloading the font.
  Stock and recovery paths keep their font storage and loading order. The bundled Linux/ARM64 raylib extension
  was rebuilt in a temporary directory on AGNOS 20.5.2 with the pinned nanobind and raylib headers. The other
  native artifacts and their build inputs match the upstream prebuilt. The device artifact and Params registry
  checks passed.
- An isolated font-loader run on the parked comma rendered identical text and loaded Inter Medium on demand.
  Regular and Bold released 13.5 MiB of CPU glyph images at startup. The measured RSS added by font loading
  dropped by about 8 MiB compared with lazy loading alone and about 53 MiB compared with eager loading.
  Full UI boot and first-alert checks are pending.

## Stage 4: Device › Backups

- Reused the approved release Backups panel and its Delete and Restore confirmations. The running release capture is
  the reference for the list, with the existing Device rail and no schedule controls.
- StarPilot 7's `ToggleBackup` exports and restores through its settings and layout owners. The parked check covers the
  restore, including while the owner writes. The old raw Params directory backups remain on disk. New settings
  snapshots and copies of Tandem's preferences are stored under `/data/tandem_backups`.
- File work and the native backup owner run in one worker per operation. The panel reports rejected, skipped and
  incomplete restores through the existing notice dialog. Tandem preferences restore after a completed native restore.

## Stage 4: Device › Storage & Data

- Reused release’s Storage & Data rows, storage bar and confirmations. The usage scan runs in the background and
  counts shared map tiles once across installed generations.
- Recording settings delegate to the native toggle request so the restart and camera lock use StarPilot’s rules.
  Delete all works on recognized drive segments through the native recording-root, inode and lock checks. Boot
  and crash logs stay outside the drive list. Remove unused models rechecks the confirmed model set and delegates
  deletion to the native model manager, which protects selected models.
- Off, Parked and Always gate the automatic uploader through the manager, as on release. StarPilot 7's separate
  network rules still apply. The panel is mounted. Offline Maps Delete uses the approved confirmation and the parked operation owner.

## Stage 4: Device › RAM

- Reused release’s recorder, process names, panel and recorder tests. The drive screen samples a baseline after
  one minute of live driving, then updates the saved snapshot at new peaks while StarPilot reports low RAM. Playback
  and projection do not write snapshots. The same three-drive history format loads existing release snapshots.
- The RAM section appears after the first snapshot and opening it clears the unread indicator. It sits before Developer
  in the release section list. The release footer and snapshot attachment are active on Report a Problem.

## Stage 4: Driving tab data layer

- `settings/store.py` and `settings/live.py` come from release unchanged but for StarPilot 7's typed Params (no
  `get_int`; `put` takes the value's own type).
- `settings/starpilot7.py` reads StarPilot 7's feature-settings pages. `FeatureRows` reads a page at most every
  half second and sends each change as `row_request` for the row as shown, so StarPilot refuses a change to a row
  that moved under it. `StarPilotOwners` makes the owners with `runtime_app`'s permissions: changes only while
  settings are open, parked-only groups only when StarPilot confirms parked, car groups only with a matching car.
  Recheck `_feature_authority` after each upstream merge.
- `settings/speed_steering.py` keeps release's choices on those rows, as the owner decided: Driving Style sets
  the personality and the acceleration and braking presets, Higher and Lower limits are the one `SLCConfirmation`
  choice, the offset is written to all seven `slc:offset` ranges, lane changes need the driver's confirmation,
  Smart Slowdowns is the Automatic driving mode with the curve controller, and MAX follows limits only applies where
  StarPilot owns SET. Sentry goes through StarPilot's Sentry owner (parked and confirmed). Vehicle Profile and
  Navigation wait for their stages.

## Stage 4: the Driving tab

- The Driving hub replaces openpilot's Toggles panel (`settings/essentials.py`, `settings/driving_tab.py`). Every page
  reads and writes StarPilot 7's owners through `FeatureRows`: Sounds (Alerts), Appearance and the onroad layout's road
  colors (Display), the model manager (Driving Model), vehicle selection and the `wheel` and `vehicle` pages (Vehicle),
  and the lane, torque, profiles and personality pages (Tuner Mode). Their permissions are StarPilot's: changes only
  while settings are open, and Sounds, Appearance, the path, models, the car and door locks only while parked.
- Dropped with StarPilot 7: Turn Signal animations, Boot Logo, Startup Message, Thin path, the Speed Limit
  Change chime, the volume for steering below its minimum speed, Use recommended's automatic downloads (it now means
  StarPilot's default model), the door lock timer, and Tuner Mode's raw gas and brake values, steering controller
  choice, cruise step and bundle overrides.
- The compass is Tandem's own now (StarPilot 7 dropped its compass): `prefs.COMPASS`, on by default, and
  `onroad/compass.py`, which reads the GPS source StarPilot selects from openpilot's UI subscriber.
- Tuner Mode is Tandem's own preference now (StarPilot 7 has no tuning level). Developer View is StarPilot's developer
  sidebar; Lead Insights is its lead indicator, lead distance and gas and brake display.
- Waits for later stages: Display › Map and Speed & Steering › Navigation (routing), Vehicle Profile, the onroad
  drawing of Developer View and the lead tag (onroad).
- `tools/render/scene_driving.py` renders each page under its mock's name.

## Stage 4: Connections

- Connections replaces openpilot's network panel with release's sections for Wi-Fi, Cellular and Network Test
  (`settings/connections.py`, `network_tab.py`, `network_test.py`) on Tandem's Wi-Fi, cellular, radio and network-test
  services. StarPilot 7's modem service applies `GsmApn`, `GsmRoaming` and `GsmMetered` itself, so the page saves them
  and nothing more. In `starpilot/tandem/wifi.py`, StarPilot 7's `_exit` means NetworkManager can't be reached.
- Bluetooth Remote and Car Audio & Devices come back with stage 6, on StarPilot 7's `ControllerOwner` and
  `BluetoothOwner` (release's screens used StarPilot 6's wheel-controls daemon and Bluetooth manager).
- `tests/fakes.py` holds release's network and Bluetooth stand-ins. `tools/render/scene_connections.py` renders the sections.

## Stage 3: settings search

- `settings/search.py` comes from release with its index rewritten for these screens: Speed & Steering has Everyday
  and Weather, Display has Driving Screen and Path, Connections has Wi-Fi, Cellular and Network Test, and Tuner Mode's
  sections are found by name and what they hold (StarPilot lists their rows for the detected car). The Driving hub has
  the Search button; `SettingsWindow.open_at` opens a Driving page by name.
- `tests/test_settings.py` builds Driving and Connections over the stand-ins and checks every row against the index;
  Device and Software rows are checked against their screens' strings.

## Stage 4: MAX follows limits

- `onroad/limits.py` adopts each new posted limit once through StarPilot 7's `SlcActionKind.ADOPT` (what its "Match the
  speed limit" wheel action sends), so StarPilot sets MAX from the limit and offset. It runs only with the switch on,
  engaged, where StarPilot sets MAX (`not CP.pcmCruise`), outside Safe Mode and replay. ADOPT is refused while a limit
  is pending, so a higher limit is followed after the driver accepts it. `tests/test_limit_follower.py` is rewritten for
  this; release's checked MAX values Tandem worked out itself.

## Stage 4: lead tag and Developer View

- The lead tag (`onroad/lead.py`) takes the place of the text StarPilot 7's model renderer draws above its lead marker:
  the view sets `model_renderer.lead_display` as StarPilot's own screen does and draws Tandem's tag from
  `_draw_lead_info` (the stock text when Lead Car Tag is off). StarPilot's marker stays its own; release's lead bars
  and adjacent-lead markers relied on StarPilot 6's renderer hooks and aren't ported.
- Developer View (`onroad/developer.py`) shows when StarPilot's Developer Sidebar setting is on: the panel takes the right
  of the screen, its Controls section lists StarPilot 7's developer metrics, and the strip sits above the bar. StarPilot
  7 publishes no planned jerk or danger factor, so the strip offers the other seven metrics.
- `tests/test_lead_tag.py` keeps release's tracker and drawing tests; its view tests targeted StarPilot 6's renderer.
  `tools/render/scene_developer.py` renders `onroaddev` and `gaptag`.

## Stage 4: defaults, first-run setup and Home's other pieces

- `settings/defaults.py` applies the Essentials defaults through StarPilot 7's owners; a value StarPilot won't change
  now (sounds, display and path while driving) is left as it is. Software › Reset Settings runs it after the release
  confirmation, while parked. Release's boot logo, compass param, Speed Limit Change chime and holiday themes are gone.
- First-run setup (`setup.py`) applies the defaults, then the three answers; choosing Auto lane changes asks StarPilot's
  confirmation once setup has closed. Home checks for it as release's did; the existing `.tandem_setup_done` marker
  keeps it from showing again on a device that already ran it.
- `menu_idle.py` (the menu's timeout closes what's open on top of settings) and `drivercamera.py` (release's overlay
  on openpilot's `CabinCameraDialog`; attention comes from `driverMonitoringState.awarenessStatus`) are ported.
- Waits for routing: Home's destinations, route map, Mapbox help and routing status.

## Stage 6: StarPilot's input on Tandem's screens

- StarPilot 7 runs wheel buttons, favorites, controllers (Bluetooth remotes, keyboards, gamepads) and Android Auto taps
  from its own app's session, which Tandem replaces. `star_input.py`'s `TandemStarSession` is that session for input
  only: it subclasses `StarShellSession`, sets what the input methods read the way StarPilot's `__init__` does, skips
  the drawing (fonts, view, PiP, map layer, favorite tiles), and inherits every decision. ui.py's frame loop polls it
  as it does StarPilot's (one line, `screens.star_input`), and `TandemInput` adds the wheel while driving and StarPilot's
  `ControllerRuntime`. Bookmark, personality and Experimental mode come from openpilot's MainLayout, toggles and button.
- `tests/test_star_input.py` fails when a merge changes what those methods read or how StarPilot sets it.
- Starting it can't take the screens down: a failure to start leaves Tandem as before, and a failing poll is logged once.
- Still to check on the device: a wheel button press while driving, and a Bluetooth remote.

## Boot logo

- AGNOS shows `/usr/comma/bg.png` (older AGNOS `bg.jpg`) while the comma starts, and every AGNOS update rewrites it.
  StarPilot 6 replaced it on each start; StarPilot 7 doesn't. `starpilot/tandem/boot_logo.py` does it the same way when
  the UI starts with Tandem's screens (owner, 2026-11-17): only when the images differ from Tandem's logo
  (`selfdrive/ui/tandem/assets/boot_logo.jpg`) does it remount `/` read-write, copy them, and restore the mount options.

## Stage 6: Connections' Bluetooth

- Bluetooth Remote and Bluetooth Devices are back in Connections (`settings/bluetooth_tab.py` from release, with
  `settings/bluetooth_sources.py`). `StarPilotControllers` drives the `ControllerOwner` the running controller runtime
  feeds (`star_input.controller_owner()`): a button is learned into a free action slot and the slot holds its action;
  StarPilot moves a learned button only by learning it again, so a button on a Quick Select or shared slot can only be
  removed and added again, and remotes don't offer release's Favorite 1-3. `StarPilotBluetooth` drives
  `NativeBluetoothOwner` on one worker thread with a pairing session per visit, as StarPilot's own page does.
- StarPilot 7 plays no openpilot sounds through Bluetooth (Soloist plays a phone's music), so release's Car Audio
  switch and sound test are gone and the section is Bluetooth Devices: paired, then nearby.
- `tests/test_bluetooth_sources.py` runs the remote against StarPilot's real `ControllerOwner`. Release's
  `test_bluetooth_discovery.py` and `test_bluetooth_policy.py` tested StarPilot 6's manager and are replaced by it.

## Stage 6: diagnostics policy

- Release's fork-wide policy is back: StarPilot 7's crash-reporting SDK (`system/sentry.py`) sends exceptions and native
  crash dumps to Bugsink on its own; `starpilot/tandem/diagnostics.py` filters them so they stay on the device. Every
  SDK user in StarPilot 7 is automatic; Report a Problem uses StarPilot's separate Bugsink sender and is unaffected.

## Stage 6: Help steer chime

- The driving screen writes `starpilot/tandem/state.HEADROOM` when Help steer appears and clears it when it goes;
  StarPilot 7's sound daemon (one-line hook in `main()`) plays its prompt chime once per warning, at the prompt volume,
  only when nothing else sounds or shows. StarPilot 7's daemon has no alert filter, so release's quieting of the turn
  steering-limit alert during Help steer is gone. The daemon picks this up when it next starts (a reboot).

## Stage 4: onroad extras

- `onroad/extras.py` draws StarPilot 7's pedal and border highlights on Tandem's screen: the pedal tiles follow its wheel
  feedback (measured acceleration, with its fade) while its wheel brake and acceleration colors setting is on, and the
  border's sides follow its signal and blind-spot border settings. StarPilot draws those borders only on the comma four;
  Tandem shows them on the 3X, as release did.
- Gone with StarPilot 7: the stopping point, adjacent-lane paths, radar points and signal animations (`turn_signals.py`,
  `starpilot/tandem/signals.py`).
- Not needed on StarPilot 7: the speed-sign model's memory hook (`vision_slc` runs only while driving) and Galaxy's
  dashboard worker (drive statistics run in Galaxy's own process now).
- The model chip (`extras.ModelChip`, `onroadextras.html`) shows Jetlink's state (StarPilot 7's external-GPU link) under
  the driver monitor tile and pedals, while StarPilot's onroad layout places its Jetlink widget.

## Tests still on `release` only

Ported so far: `test_destinations.py` (but StarPilot 6's search client and Mapbox key help), `test_routemap.py` (but the
StarPilot 6 position readers), `test_fallback_font.py`, `test_compass.py`, `test_network_test.py` (but its settings search test), `test_cellular_status.py`, `test_hotspot_name.py`, `test_network_touches.py` (StarPilot 7 has no PC-only touch path), `test_alert_levels.py`, `test_bar.py`, `test_streets.py`, `test_keyboard.py`,
`test_voice.py`, `test_speech_native.py`, `test_larger_text.py` but its Display settings test, the component, chip and
Help steer tests of `test_tandem.py`, the catalog-mechanics tests of `test_translations.py`, the atlas crop tests of
`test_font_loading.py`, and the text hook test of `test_upstream_integration.py`. Each of the rest comes back with the code it tests. When one comes back, take it from `release` whole.

| `release` test | Waits for |
|---|---|
| `test_tandem.py` from `test_release_notes_lead_with_a_tandem_entry` on | Home and settings screens (stage 4) |
| `test_translations.py`: the template, metadata, coverage and completed-language checks, Developer View labels, picker languages | Every screen ported, then `tools/translations.py update` (end of stage 4) |
| `test_font_loading.py`: lazy fonts, glyph release and alert faces | Glyph release when restored, then lazy loading and alert faces with the screen port (stage 4) |
| `test_upstream_integration.py`: all but the text hooks and the sidebar factory | Their hooks and modules (stages 3 to 6) |
| `test_turn_signals.py`, `test_onroad*.py`, `test_chip_events.py` (StarPilot 6's message reader; its rules are covered by the chip tests), `test_headroom_warning.py`, `test_limit_offers.py`, `test_developer_view.py` | Onroad (stage 4) |
| `test_ram.py` | Home and sidebar (stage 4) |
| `test_developer.py`, `test_software_dialogs.py`, `test_storage_sizes.py`, `test_prebuilt_params.py` | Settings screens and owner integration (stage 4) |
| `test_routing_ui.py`, `test_map_progress.py` | Offline routing (stage 5, phase B) |
| `test_remote_actions.py`, `test_galaxy_signals.py` | Controllers and Galaxy (stage 6) |
| `test_workflow_policy.py` | Workflows (stage 6) |
| `starpilot/tandem/tests/` | The services they test (stage 5) |

## Stage 5: navigation (phase A)

- `places.py` (StarPilotPlaces) gives Where to? StarPilot 7's `NavigationOwner`: its place search, favorites with Home and
  Work as labels, recents, and revision-checked changes. Start turns StarPilot's navigation on if it's off, then sets the
  destination. The preview route comes from StarPilot's own route engine (Mapbox, or Google with its key) from the
  last saved position, with the driver's avoidances.
- Release's `UpstreamPlaces`, its direct Mapbox fetch and the LastGPSPosition readers are gone with StarPilot 6.
- Waits for its own mock: an Offline Maps page on `OfflineMapsOwner` (areas around a point, not release's regions).
  Where to?'s Offline maps button shows only when a maps page is given.
- Phase B: Valhalla as a route provider (release's offline-maps chip and "Choose regions" in the preview come back then).
  Owner, 2026-11-18: Offline Maps downloads both, as on release: choosing a state downloads its routing graph and asks
  StarPilot 7's map owner (`starpilot/maps/operation_owner.py`) for the same region's road data.
- Phase B, part 1 (engine), done: release's `starpilot/tandem/routing` broker, native worker, bundles, images,
  downloads and catalog, with `routing/navigation.py` in place of release's navigationd subclass and policy engine.
  StarPilot 7's `RouteRuntime` keeps following the route; Tandem's subclass only picks the provider (hooks in the
  README). Avoidances reach Valhalla as its auto costing preferences. `regions.py` keeps the US state list that
  StarPilot 6's `maps_selection`/`maps_catalog` held.
- Phase B, part 2: downloads done. A map job asks StarPilot 7's map owner for each chosen state's road data it doesn't
  have yet (`routing/road.py`, one region at a time, while parked), then installs the routing graphs. `map-road.json`
  records which states Tandem got road data for; StarPilot's snapshot doesn't name its regions. Release's
  `handoff.py`, `paired.py` and road-tile pruning are gone with StarPilot 6's downloader, and so are the tests of its
  schedule and companion hook. StarPilot 7 has no scheduled map refresh, so release's Weekly and Monthly updates have
  nothing to hook into.
- Phase B, part 2, screens done: Offline Maps (`settings/maps.py` on `settings/map_source.TandemMaps`), its region
  picker and download view against release's approved `valhalla2`/`valhalla3`/`valhalla4`/`valhalla5` mocks, and
  Navigation's Offline maps only, Preferred maps and Offline Maps rows (`stage5-drivingnav`, `stage5-drivingnav-end`).
  Where to?'s Offline maps button opens the page. Remove maps is Storage & Data's Delete.
- Phase B, routing chips done: `onroad/status.routing_state` maps StarPilot 7's published navigation status
  (`starpilotNavigation`) and Tandem's `routing-status.json` onto release's `routing_chip` (`valhalla2-chip-*`). The bar
  shows a route (End route, dashes for estimates) for any StarPilot destination, not only while guiding.
- Phase B, Where to? done: Offline maps ready shows while Tandem's routing data is ready (`valhalla2-places`), and with
  Offline maps only a preview without an offline route says why, holds Start and offers Choose regions
  (`valhalla2-preview-strict-missing`). Phase B is complete.
- Speed & Steering › Navigation (`settings/navigation.py`, `design/stage5-drivingnav.html`) writes StarPilot's own
  navigation settings: on or off, directions (Google only with its key), avoidances and position. Saved Places opens
  Where to?. Keys are pasted in Galaxy; `map_keys.py` (`stage5-mapboxkey.html`) explains how. Release's End Route When
  Parked has no StarPilot 7 setting.
- Display › Map is left out: StarPilot 7 dropped Turn-by-Turn on Screen (`NavigationUI`; Tandem's turn card shows
  with every route) and has no writer for the sign style (`UseVienna`), so only the Offline Maps link was left, and
  Speed & Steering › Navigation has it.

## Stage 8: translations, Arabic and the weather heads-up

- The catalog covers every ported screen (1,458 strings). The 12 languages release finished have the new and reworded
  ones, release's English placeholders are translated, and Vietnamese is translated whole. `NotoSans-Fallback` is
  rebuilt for the new characters; StarPilot 7's raylib adds `load_font_data`'s glyph count argument, which the font
  tools now pass.
- Text Tandem's catalog doesn't have falls back to StarPilot's own translation (`multilang.tr`), so StarPilot 7's row
  labels read in the driver's language.
- Arabic: StarPilot 7 has no Arabic, so General's picker saves `LanguageSetting` "ar" and StarPilot keeps drawing its
  screens in English while Tandem's read Arabic.
- The weather heads-up is back: `forecast.py`'s announcer shows the chip before rain, snow or storms and chimes once
  through the headroom soundd subclass (`weather-chime.json`), with the position from StarPilot 7's location.

## Following `testing`

- Owner, 2026-11-20: `development` follows upstream's `testing`, Dom's successor. Dom's hand-off commit adds
  `scripts/branch_migration.py`, which moves a device on `Dom` to `testing` at boot; it leaves `development` alone (it
  runs only on that exact commit, on a branch named `Dom`).
- `testing` moves AGNOS to 20.5.3 and rebuilt every native file on it. `development` takes upstream's
  `_raylib_extra.so`, which lacks Tandem's `release_font_glyph_images`, so Tandem skips the glyph release (screens are
  the same; the font memory saving is off) until the extension is rebuilt from Tandem's `raylib_extra.cc` on a comma
  running 20.5.3 and `prebuilt.json` is refreshed (README › Keeping merges easy).
- StarPilot's small default model is now `cheddar`; the Driving Model test reads `DEFAULT_SMALL`.

## Stage 8: the planner chips

- Each reads what StarPilot's own onroad UI reads (`onroad/view.py`, with the choices in `onroad/binding.py`):
  - Stopping ahead and Stopped: `onroad_conditional.stop_active`, conditional mode's accepted stop while it controls the
    speed (StarPilot's gauge shows STOP for it). A stop it only perceives isn't one.
  - Stopping for stop sign: that stop, with StarPilot's camera stop-sign sighting still on screen
    (`OnroadState.stop_sign_observed_ns`) or the car's dashboard stop sign (`starpilotCarState.dashboardStopSign`).
  - Slowing for traffic: conditional mode's `cem_lead` reason while openpilot controls the speed.
  - Steering paused (under a speed, for a signal, after a turn): StarPilot's `LateralPause` run on the same car state
    as controlsd, while steering is really off (`latActive`).
  - Matching limit: release's `LimitWatch` on the limit StarPilot accepted, its adjusted target and whether its speed
    limit control holds the set speed (`SpeedLimitObservation`).
- `tests/test_planner_chips.py` checks the choices and that the StarPilot fields they read still exist.

## Stage 8: statistics and athenad

- Release kept unattended diagnostics on the device. On StarPilot 7 that's three hooks: crash reports (`sentry.py`, done
  earlier), athenad's `log_handler` (its `stat_handler` is gone), and the `usage_stats` process that replaced StarPilot
  6's stats upload, which no longer starts. All read `starpilot/tandem/diagnostics.AUTOMATIC_DIAGNOSTICS_ENABLED`.
- `RELEASE_BRANCHES` is left as StarPilot 7 has it. Release added `release` beside StarPilot 6's own release branch; StarPilot
  7 counts none of its own branches as release channels, and one would clear development-only settings, hide developer
  options and turn off alpha longitudinal. Waiting on the owner.

## Stage 8: workflows

- StarPilot 7 brings 14 workflows, none of release's. `tools/workflow_policy.py` and `workflow-policy.json` (release's
  tool) pin each by hash with what it does in Tandem's repository; `tests/test_workflow_policy.py` fails until a new or
  changed one is reviewed.
- Gated to `StarPilotHQ/StarPilot`, as release gated its inherited publishers: `stale.yaml` (closes PRs daily once this
  is the default branch) and `jenkins-pr-trigger.yaml` (force-pushes and deletes Jenkins branches). The rest are already
  gated upstream, read-only, manual, or trigger only on upstream's branch names.
- Release's `tandem_routing_maps.yaml` (the monthly routing-data build) isn't ported: its bootstrap script and hosted
  build tests stay on `release`, which keeps building the data until this branch replaces it.

## Stage 8: Galaxy's drive analyzer

- Release's `dashboard_worker.py` (a launch lock, and a driving check between log segments) isn't needed: StarPilot 7's
  analyzer (`starpilot/galaxy/drive_stats.DriveStatsOwner`) is one worker thread in Galaxy's server, and it rechecks
  every 0.1 s that the device is offroad (`IsOffroad`, with Force Offroad) before each step.

