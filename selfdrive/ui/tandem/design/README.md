# Essentials: Tandem's design language

Essentials is Tandem's design language: an opinionated take on the StarPilot 3X settings UI. Instead of exposing a control for every param, Tandem ships good defaults and offers a small number of controls. Each control writes several existing params at once. Detail that most drivers never need sits behind one-switch bundles.

This builds on the visual direction in *StarPilot 3X UI Directions*, pages 6–9: the hub, the sidebar panel, the option sheet and the onroad bar. The look stays the same. The number of choices goes down.

For fonts, colors, sizes, states and motion, and how to convert mock values to the device, see [tokens.md](tokens.md). The code side is `selfdrive/ui/tandem/`: tokens plus the component library (see its README).

Open any `.html` file in this folder in a browser. Each screen is 1125×563, the same frame as the PDF. Screenshots are in `screenshots/`.

| Screen | File |
| --- | --- |
| Hub | [hub.html](hub.html) |
| Driving | [driving.html](driving.html) |
| Display and bundles | [display.html](display.html) |
| What a bundle sets | [bundlesheet.html](bundlesheet.html) |
| Onroad, default | [onroad.html](onroad.html) |
| Onroad, Developer View + Lead Insights | [onroaddev.html](onroaddev.html) |
| Alerts | [alerts.html](alerts.html) |
| Tuner Mode | [tuner.html](tuner.html) |
| Steering controller | [steeringcontroller.html](steeringcontroller.html) |
| Defaults map | [defaults.html](defaults.html) |
| Destinations | [destinations.html](destinations.html) |
| Search with keyboard | [navsearch.html](navsearch.html) |
| Route preview | [routepreview.html](routepreview.html) |
| Onroad, navigating | [onroadnav.html](onroadnav.html) |
| Offline maps | [mapdata.html](mapdata.html) |
| Onroad alert levels | [alertstyles.html](alertstyles.html) |
| Confirm new speed limit | [confirmlimit.html](confirmlimit.html) |
| Confirm dialogs | [confirmdialog.html](confirmdialog.html) |
| Keyboard | [keyboard.html](keyboard.html) |
| Progress, blocked, done, empty | [feedback.html](feedback.html) |
| Path and lead marker | [leadmarker.html](leadmarker.html) |
| Lead gap tag | [gaptag.html](gaptag.html) |
| Parked home | [home.html](home.html) |
| Home: alerts, update ready | [homealerts.html](homealerts.html), [homeupdate.html](homeupdate.html) |
| First-run setup | [setup.html](setup.html) |
| Driving Model | [model.html](model.html) |
| System | [system.html](system.html) |
| Vehicle | [vehicle.html](vehicle.html) |
| Steering headroom | [steeringheadroom.html](steeringheadroom.html) |
| Status chips | [statuschips.html](statuschips.html) |
| Onroad extras (StarPilot options) | [onroadextras.html](onroadextras.html) |
| Device tab | [devicetab.html](devicetab.html) |
| Device › Developer › CAN test recorder | [canrecorder.html](canrecorder.html) |
| Pair the phone app | [pairing.html](pairing.html) |
| Driver camera preview | [drivercamera.html](drivercamera.html) |
| Remote Access (Galaxy) | [remoteaccess.html](remoteaccess.html), set up: [remoteaccessqr.html](remoteaccessqr.html) |
| Assistance | [assistance.html](assistance.html) |
| Settings search | [search.html](search.html) |
| Connections: Wi-Fi | [connections.html](connections.html) |
| Connections: Cellular | [connectionscellular.html](connectionscellular.html) |
| Connections: Bluetooth Remote | [connectionsremote.html](connectionsremote.html) |
| Connections: Car Audio & Devices | [connectionsaudio.html](connectionsaudio.html) |
| Software tab | [softwaretab.html](softwaretab.html) |
| Assign a wheel button | [wheelbuttonlearn.html](wheelbuttonlearn.html) |
| Driving › Vehicle Profile | [drivingvehicle.html](drivingvehicle.html) |
| Driving › Weather | [drivingweather.html](drivingweather.html) |
| Driving › Navigation | [drivingnav.html](drivingnav.html) |
| Display › Theme & Startup | [displaytheme.html](displaytheme.html) |
| Display › Map | [displaymap.html](displaymap.html) |
| Path Style picker | [pathstylepicker.html](pathstylepicker.html) |
| Turn Signal picker | [signalpicker.html](signalpicker.html) |
| Device › Backups | [systembackups.html](systembackups.html) |
| Device › Storage & Data | [systemstorage.html](systemstorage.html) |
| Device › Report a Problem | [systemreport.html](systemreport.html) |
| Tuner › Gas & Brake | [tunergas.html](tunergas.html) |
| Tuner › Following & Stops | [tunerfollowing.html](tunerfollowing.html) |
| Tuner › Bundle Overrides | [tunerbundles.html](tunerbundles.html) |
| Vehicle › Choose your car | [vehiclepicker.html](vehiclepicker.html) |
| Numeric value editor | [valueeditor.html](valueeditor.html) |
| Volume editor | [volumeeditor.html](volumeeditor.html) |
| Offline maps › Choose regions | [mapregions.html](mapregions.html) |
| Offline maps › Downloading | [mapdownloading.html](mapdownloading.html) |
| Driving Model › Browse and download | [modelcatalog.html](modelcatalog.html) |

## Steering controller

[steeringcontroller.html](steeringcontroller.html) is the interactive steering-controller mock,
with the same choices as [tuner.html](tuner.html). Click a choice for its explanation, or use the
arrow keys. The choices are **Vehicle default**, NNFF auto, NNFF, Lite and Torque.

Vehicle default clears the NNFF, NNFF Lite and Force Torque overrides, matching StarPilot's
registry defaults. NNFF auto means NNFF when supported, otherwise Lite. New Essentials setups,
Reset Settings and Reset all tuning choose Vehicle default. Saved selections are read from the
existing StarPilot params; no new preference key or startup migration is needed.

## Settings structure

The CAN recorder uses the shared Camera/OBD segmented control, locked while a test runs. The OBD frame count confirms the selected input is receiving before manual markers are recorded. Abort stays in the panel header; each column scrolls independently. OBD tests stop after two minutes and restore the normal input before Saved.

- **Assistance** is a hub tile ([assistance.html](assistance.html)): openpilot's core switches beside Driver Monitoring, which gathers Always-On Driver Monitoring, the Driver Camera preview and the driver monitoring reset.
- **Search settings** sits at the top right of the hub ([search.html](search.html)). It searches every setting's name, what it does and where it lives, with the Essentials keyboard; the best four show above the keyboard and Search lists them all. Picking one opens its page and section. Settings behind Tuner Mode are found only while it's on.
- **Connections** replaces the Network and Bluetooth tabs ([connections.html](connections.html) and its sections).

## Path and lead marker

[gaptag.html](gaptag.html) is the approved lead marker. It supersedes the primary ground bar in
[leadmarker.html](leadmarker.html) and the triangle in the older Developer View mock.

- **Path:** Essentials blue (`#5AAAF8`, 50% at the car fading toward the horizon) for the Standard and Thin path styles, through StarPilot's `PathColor`. Rainbow and Acceleration keep their own colors.
- **Lead marker:** the existing developer tag, with its JetBrains Mono type, dark fill, border and rounded corners. An anchor above the car's estimated roof and a thin connector associate it with the car.
  - Normal view shows the actual time gap in seconds, centered in the tag. Near a stop it shows meters or feet, using the driver's units.
  - Developer View or Lead Insights keeps the existing distance, time gap and relative speed, centered as a group.
  - The anchor and connector, and the normal tag's value, turn amber with the Slowing for traffic rule. The developer values keep their existing text colors.
  - An uncertain lead dims the tag to 45% opacity and replaces its numbers with `--`. Stale, invalid or missing data hides the tag.
  - A new lead or the existing cut-in rule starts a 250 ms entrance: anchor, connector, then the tag fading in and rising slightly. Text stays at full size.
  - The displayed value is smoothed. A small speed band keeps seconds and distance from flickering near a stop.
  - Other detected cars retain their faint ground bars and existing optional Lead Insights behavior.

## Principles

1. **One control per decision a driver actually makes.** About 190 rows in `selfdrive/ui/layouts/settings/starpilot/` become 14 controls.
2. **Presets over sliders.** A segmented choice, such as Relaxed / Standard / Sport, writes a coherent set of values. Raw numbers live only in Tuner Mode.
3. **Bundles for power users.** Developer View, Lead Insights and Tuner Mode are each one switch. Turning a bundle off restores the values it replaced.
4. **Safety info is never hidden.** The Hide* toggles for speed, max speed, alerts, steering wheel, driver monitoring icon and lead marker are removed.
5. **Show state, not descriptions.** Hub tiles show current values ("Standard · Auto lane change") so a driver can check their setup at a glance.

## Controls and the params they write

Defaults are in **bold**.

### Driving

| Control | Choices | Params |
| --- | --- | --- |
| Driving Style | Relaxed · **Standard** · Sport | `LongitudinalPersonality` `AccelProfile` `DecelProfile` `HumanLaneChanges` |
| Speed Limits | Off · Show · **Match** (offset **+3**). Higher limits: **Tap to confirm** · Update automatically | `ShowSpeedLimits` `SetSpeedLimit` `SLCConfirmation` `SLCConfirmationLower` `SLCConfirmationHigher` `SLCFallback` `SLCPriority` `SLCMapboxFiller` `VisionSpeedLimit` `ConfigureOffsets` `UseVienna` (from region) |
| Lane Changes | **Nudge** · Auto | `NudgelessLaneChange` `OneLaneChange` `LaneChangeTime` `MinimumLaneChangeSpeed` `LaneDetectionWidth` `LaneChangeSmoothing` |
| Smart Slowdowns | **On** · Off | `ConditionalExperimental` `CECurves` `CEStopLights` `CEStoppedLead` `CESlowerLead` `CurveSpeedController` `MapDecel` |
| Always-On Steering | **On** · Off | `AlwaysOnLateral` |
| Vehicle Profile | **Car** · EV · Truck · Towing | `EVTuning` `TruckTuning` `TrailerLoad` |
| Weather | **Auto** · Off | `WeatherPresets` `LowVisibility` `Rain` `RainStorm` `Snow` |

### Display and alerts

| Control | Choices | Params |
| --- | --- | --- |
| Path Style | **Standard** · Thin · Rainbow · Acceleration | `PathColor` `PathWidth` `PathEdgeWidth` `PathEdgesColor` `LaneLinesColor` `LaneLinesWidth` `RoadEdgesWidth` `RainbowPath` `AccelerationPath` `DynamicPathWidth` |
| Turn Signal | **Standard** · Whimsy: Jumping frog · Pouncing cat · Bouncing ball | `SignalAnimation` (`stock`, `frog`, `pouncing_cat`, `bouncing_ball`); a Whimsy choice also sets `CustomThemes` on and `RandomThemes` off, as StarPilot's picker does |
| Driving Style Banner | On · **Off** | `HideDistanceProfileBanner` (inverted) `AdvancedCustomUI` |
| Compass | **On** · Off | `Compass` |
| Blind Spot Highlights | **On** · Off | `BlindSpotPath` `BlindSpotMetrics` `SignalMetrics` `BorderWidth` |
| Alert Volume | Quiet · **Normal** · Loud | `EngageVolume` `DisengageVolume` `PromptVolume` `PromptDistractedVolume` `RefuseVolume` `WarningSoftVolume` `WarningImmediateVolume` `BelowSteerSpeedVolume` |

The four chime switches stay as they are: Green Light (**on**), Lead Departure (**on**), Speed Limit Change (off) and Loud Blind Spot (off). Warning volumes keep their existing 25% floor.

Lane-change and turn progress always use the status chips; their full-width status banners stay hidden. Driving Style Banner only controls the personality message shown when the style changes.

### Power user

| Control | Default | Params |
| --- | --- | --- |
| Developer View | **Off** | `DeveloperSidebar` `DeveloperSidebarMetrics` `DeveloperMetrics` `FPSCounter` `ShowCPU` `ShowGPU` `NumericalTemp` `ShowMemoryUsage` `AdjacentPathMetrics` `ShowCSCStatus` `ShowSLCOffset` `SpeedLimitSources` |
| Lead Insights | **Off** | `LeadInfo` `RadarTracksUI` `ShowStoppingPoint` `ShowStoppingPointMetrics` `AdjacentPath` `PedalsOnUI` |
| Tuner Mode | **Off** | Writes nothing. It unhides `SteerDelay` `UseAutoSteerDelay` `SteerFriction` `SteerKP` `NNFF` `NNFFLite` `ForceTorqueController` `ForceAutoTune` `ActuatorDelay` `MaxAccel` `StartAccel` `StopAccel` `StoppingRate` `StartSpeed` `StopSpeed` `LeadDetection` `CustomCruise`, plus per-item overrides inside bundles |

## Fixed values, no longer shown

Holiday themes off (`HolidayThemes`; this redesign drops them), rotating wheel **on**, stopped timer **on**, wheel speed off, reverse cruise increase off, pulse and glide off, map gears off, force stops and force standstill off, model randomizer off. The onroad personality button (`OnroadDistanceButton`) is removed.

## Navigation changes

- The bottom bar has four tabs: **Driving**, Device, Connections, Software. The **Toggles** and **Developer** tabs are gone. Metric units and language move to Device › General. SSH, ADB and joystick move under Tuner Mode.
- The Driving tab opens on a hub with five tiles: Speed & Steering, Display, Alerts, Driving Model, Vehicle. A "Power user" strip below them holds the three bundle switches.
- **Labels describe what things do** rather than naming the product: "Reset Settings", "How It Works", "Phone App", "Version [version]".
- The onroad bar drops the Experimental flask, because Smart Slowdowns switches modes automatically. A status chip such as "Slowing for curve" shows when it acts.
- **The onroad bar has no panel or scrim behind it.** The camera view runs to the bottom edge with no dark fade. The controls have 80%-opaque backgrounds to stay readable over bright scenes such as snow or low sun. Avoid a live blur behind the bar: blurring the camera image every frame costs GPU time on the device.
- **The onroad bar holds four things:** menu, MAX −/+, the current street name, and the engage button.
  - Driving Style is set in Settings › Driving and with the wheel's distance button. There is no onroad toggle for it.
  - The street name is always on, which retires the `RoadNameUI` toggle. While navigating, arrival time, distance left and End route take its slot, and the street name moves to a chip above the steering headroom arc.

## Steering headroom

This builds on the existing torque bar in `selfdrive/ui/onroad/starpilot/torque_bar.py`. That bar is the clearest early signal that the car is running out of steering on a curve, so it is always on. The `EnableTorqueBarWidget` and `ShowSteering` toggles go away.

- It keeps the current arc at the bottom of the road view and the current estimate (lateral acceleration plus path error plus road tilt, divided by the car's maximum).
- **Three stages instead of a gradual fade:**
  - **Comfortable (under 60%):** a thin white arc and no sound.
  - **Working (60–85%):** the arc turns amber and gets thicker.
  - **At limit (over 85%, held for about half a second):** the arc turns orange-red, the lane lines tint, and the Warning alert "Help steer" plays one chime. It draws like every other Warning alert, the amber card along the bottom in the bar's place, with the arc moved above it.
    The border turns amber. The warning clears below 80% to avoid repeated chimes near the threshold, and clears whenever steering becomes inactive. Existing driving alerts take priority.
- **Preview of the curve ahead.** A faint extension of the arc shows the steering the planned path will need 2–3 seconds out, based on the model's desired curvature at the current speed. The driver sees trouble before the car reaches it.
- The arc sits on the road view just above the onroad bar, where the driver is already looking. It replaces the flat "STEERING" bar from the earlier mocks.

Open: the 60% and 85% thresholds, and whether the preview should use the model's plan or map curvature when a route is active.

## Status chips

The bottom-left corner of the onroad view, just above the bar, answers "why is the car doing that?". A chip shows only while the car changes speed or steering on its own. When the corner is empty, nothing unusual is happening.

| Chip | Icon | Color | Triggered by |
| --- | --- | --- | --- |
| Slowing for curve | Curve | Blue | `CurveSpeedController` |
| Stopping ahead (Stopped once stopped) | Stop | Blue | `CEStopLights`: the model predicts a stop, at a light or a sign |
| Stopping for stop sign (Stopped for stop sign once stopped) | Octagon | Blue | The car's dashboard confirms a stop sign (`stopSignConfirmed`) |
| Slowing for traffic | Car rear | Blue | `CESlowerLead`, `CEStoppedLead` |
| Slowing for turn | Turn arrow | Blue | `NavDesiresAllowed`, while a route is active |
| Matching limit 45 | Gauge | Blue | `SetSpeedLimit`: after the limit the car drives to changes (accepted, not still asking), while the limit holds the speed under the set speed, until the car reaches it |
| Rain · longer gap (also Heavy rain, Snow, Fog) | Cloud with rain | Blue | `WeatherPresets`, only when that condition's preset adds following distance. Conditions are grouped as StarPilot's weather checker groups them |
| Steering paused | Wheel with pause bars | Amber | The steering wheel's Pause steering button. Also with Always On Lateral, which StarPilot turns off while it pauses |
| Steering paused · under 20 mph | Wheel with pause bars | Amber | `PauseLateralSpeed`: the speed is the driver's setting, not the car's. A car's own minimum steering speed shows in openpilot's "Steer Unavailable Under …" alert. Not shown with `PauseLateralOnSignal`, where speed alone doesn't pause |
| Steering paused after turn | Wheel with pause bars | Amber | `LateralResumeDelay`: StarPilot's hold for a few seconds after the signal ends, when the car slowed for the turn |
| Steering paused for signal | Signal chevrons | Amber | `PauseLateralOnSignal`: signalling below the Pause steering speed |
| Lane change blocked | Lane, car and cross | Amber | A car in the blind spot: shown whenever openpilot or StarPilot raises Car Detected in Blindspot (`laneChangeBlocked`, `laneChangeBlockedLoud`), in place of that banner; its chime still plays |
| Changing lanes right | Lane-shift arrow | Blue | `NudgelessLaneChange` |
| Steering only | Steering wheel | Blue | `AlwaysOnLateral` with cruise off |
| Speed control paused | Gauge with pause bars | Amber | Pause speed control from a wheel button (`pauseLongitudinal`): the driver has the pedals |
| Coasting | Coast arrow | Blue | Force coast from a wheel button (`forceCoast`), until either pedal |
| Pulse & glide (Pulse & glide · gliding in the glide phase) | Pulse wave | Blue | Pulse and glide from a wheel button (`pulseAndGlide`, `pulseGlideCoasting`) |
| Ready · tap resume | Play | Green | Stopped and waiting for the driver |
| Car ahead moved | Car with up arrow | Green | `LeadDepartingAlert` |
| Light is green | Traffic light, bottom lit | Green | `GreenLightAlert` |

Rules:
- Show up to four chips at once, stacked up from the bar, newest nearest it. With more reasons than that, the highest priority show: steering paused or blocked, then stopping, then slowing, then waiting.
- Each chip stays up while its reason holds, renews whenever it fires again, and fades 2 seconds after it ends; the chips above slide down into its place.
- Chips hide while an alert is showing. Driver attention warnings and takeover requests always use the alert levels instead.
- Each chip is an icon plus four words or fewer.

## Device, Connections and Software tabs

The bottom bar has four tabs: Driving, Device, Connections and Software. The current tab is highlighted. Connections holds what were the Network and Bluetooth tabs, as four sections: Wi-Fi, Cellular, Bluetooth Remote, and Car Audio & Devices.

- **Device** has a sidebar: This Device, General, Backups, Storage & Data, Report a Problem. Everything about the hardware and its data lives here.
  - This Device: Phone App pairing (Pair opens [pairing.html](pairing.html): three steps for comma connect beside the QR code, on a white tile so it scans; the Galaxy web app is Remote Access, under More, which opens [remoteaccess.html](remoteaccess.html): choose a password to create the link, then its code and Unpair), driver camera preview, camera recalibration, and "How It Works" (the training guide).
  - Restart and Power Off.
  - Serial, device ID and driver monitoring reset move to Developer View.
- **Connections › Wi-Fi and Cellular:**
  - The Wi-Fi list, with the connected network on top, plus "Join a hidden network".
  - Cellular status, Hotspot (tethering) with its current name, an Edit button and its password, and Save Data, which is on by default and covers metered Wi-Fi.
  - Roaming, APN and IP address sit behind one row.
- **Connections › Bluetooth Remote and Car Audio & Devices:** Bluetooth Remote comes first in the Bluetooth sections, because a remote mounted on the steering wheel is the main reason to pair something. It's named apart from the car's own Steering Wheel Buttons (Vehicle).
  - The connected remote is listed with its assigned buttons, each with its action.
  - New remotes start with four presets: engage, disengage, change driving style, and screen off / on.
  - **Press to find.** While this tab is open, the wheel controls test mode (`WheelControlTestActive`) is on, both parked and onroad. Pressing a button on the remote highlights its row and marks it PRESSED, and its action does not run. An unassigned button highlights Add a button instead, including before any buttons are mapped. Leaving the tab or closing settings ends testing and cancels pending button learning; normal mapped actions keep their previous enabled state. This replaces the separate Test button.
  - **Add a button** opens a two-step sheet. Step 1: press the button on the remote; listening stops after 20 seconds. Step 2: pick an action (driving style, screen, save a clip, run a favorite, always-on steering, coast, engage, disengage). Favorites are the saved settings/actions; each choice shows its configured name. Removing or moving a mapping releases its action slot when no other button uses it.
  - Pulse and glide and driver selfie are only in Tuner Mode.
  - This uses the existing wheel controls service (`WheelControlMappings`, `ControllerActionSlots`, `WheelControlLearnSlot`).
  - Car audio (Test sound) and Nearby devices sit in a smaller column. Pairing waits until the car is parked.
- **Software:**
  - Version and update status, with Check now and What's new.
  - Automatic Updates, on by default: they download while parked and install when the car turns off.
  - Release Channel shows Stable. Other branches, Fast Update and the error log are in Tuner Mode.
  - Reset Settings restores the Essentials defaults and keeps backups.
  - Uninstall sits at the bottom. Factory reset moves to Tuner Mode.

## Settings sub-screens

Every sidebar item has its own screen. Sidebar items link to each other, so the mocks can be clicked through.

- **Driving › Vehicle Profile:** four cards: Car, EV, Truck and Towing (`EVTuning`, `TruckTuning`). Trailer Load (Light / Medium / Heavy) is only available with Towing. Those three trailer presets are a proposal; `TrailerLoad` takes a number today.
- **Driving › Weather:** Auto or Off (`WeatherPresets`), plus plain-language cards for fog, rain, storms and snow (`LowVisibility`, `Rain`, `RainStorm`, `Snow`). The exact amounts and the weather API key are in Tuner Mode.
- **Driving › Navigation:** Home, Work and other favorites. End Route When Parked (`ClearNavOnOffroad`, on). A link to Offline Maps. Route speed and turn behavior have no toggles.
- **Display › Theme & Startup:**
  - Camera View: Auto / Standard / Wide (`CameraView`; default Standard). The Driver view option moves to Developer View.
  - Driver Camera in Reverse (`DriverCamera`), Boot Logo (`BootLogo`) and Startup Message (`StartupAlert`).
- **Display › Map:**
  - Turn-by-Turn on Screen (`NavigationUI`).
  - Speed limit sign style: Auto / US / Vienna (`UseVienna`; Auto follows your region).
  - A link to Offline Maps.
- **Path Style picker:** a sheet with live previews of Standard, Thin, Rainbow and Acceleration.
- **Turn Signal picker:** Standard (the chevrons in the speed pill) and, under Whimsy, StarPilot's jumping frog, pouncing cat and bouncing ball, each shown by a frame of its animation. A Whimsy animation crosses the road above the bar while signalling, drawn by StarPilot's renderer (its frames, timing and blind spot frame), and hides while an alert shows; the chevrons stay. Other StarPilot animations, chosen in StarPilot's own settings, aren't drawn in Essentials and read as Standard.
- **Device › Backups:** Back up now; Automatic Off / Weekly / Monthly, which also saves before every update; the saved list with Restore and Delete.
- **Device › Storage & Data:** a storage bar (drives, maps, models); Delete all drives; Record Driver Camera and Record Microphone, both off by default.
- **Device › Report a Problem:** six plain-language categories, optional details, "Attach last drive" (logs only), an optional Discord name, and Send.
- **Tuner › Gas & Brake:**
  - Each value shows where it comes from: FROM STYLE, DEFAULT or OVERRIDE.
  - Acceleration and Braking profile, Maximum Acceleration, Start and Stop Acceleration, Stopping Rate, Actuator Delay.
- **Tuner › Following & Stops:**
  - Following gap per style: Relaxed, Standard, Sport and Traffic.
  - Lead Detection Sensitivity, Stopped Distance, Use Radar for Take-Offs, Force Stops at Lights, Cruise Button Step.
- **Tuner › Bundle Overrides:** a tab per bundle, with one toggle for each param it sets. Items that differ from the bundle are marked OVERRIDE, and the sidebar shows a count of changes.
- **Vehicle › Choose your car:** Make and Model lists, with the detected model marked. Saving turns off automatic detection (`ForceFingerprint`).

Values in square brackets are placeholders, not proposed defaults.

## Value editors and download flows

- **Numeric value editor.** One bottom sheet for every number setting. The example is Speed Limit Offset.
  - A large value with big − and + buttons. Holding a button speeds it up.
  - A slider with the default marked and the range shown at each end.
  - Quick-pick chips and Reset to default.
  - This builds on the existing `AetherSliderDialog`, which already has min, max, step, unit and labels.
- **Volume editor.** The same sheet plus Play sample, which uses the car speakers when they're connected.
  - The slider marks the Quiet, Normal and Loud presets. Quiet is 25% for every group, the lowest the safety warnings can go. Normal is 35% for engage and disengage chimes, 45% for prompts, 60% for driver attention and 80% for take-control warnings, so safety sounds stay louder than routine ones.
  - For safety alerts, the area under 25% is hatched and can't be selected.
  - Changing a single level switches the Alert Volume preset to Custom.
- **Choosing map regions.** Tabs for U.S. regions, U.S. states and other countries.
  - Region cards show state count and size, and your region is tagged.
  - A summary column shows download size and storage left afterwards, a readiness checklist (parked, on Wi-Fi, enough storage) and Download. Download stays disabled, with the reason shown, until every check passes.
- **Map download progress.**
  - Overall percent, size and time left.
  - Four steps: Prepare, Download, Install, Ready.
  - A grid of states showing which are done, which is in progress and which are queued.
  - It pauses when driving or off Wi-Fi and resumes on its own. You can leave the screen. Cancel sits at the top right.
- **Model catalog.** Tabs for For your car, Community picks and On device.
  - Each row shows one state: Active, Downloading (with progress and Cancel), On device (Use), Download (with size), or Not available (e.g. needs an eGPU).
  - A side column shows storage, with Remove unused models.
  - Only one download runs at a time. A new model takes effect at the next drive.

## Navigation

- **Destinations are one tap from the parked home screen** ("Where to?"), not buried under Driving Controls › Navigation & Maps.
- Destinations shows Home, Work, up to 3 more favorites and recent places. Search uses the on-device keyboard.
- **The route preview has no toggles.** While a route is active, `NavDesiresAllowed` and `NavLongitudinalAllowed` are always on: the car slows for turns and uses route speed limits where signs are missing.
- Onroad, the speed limit sign stays top left and the turn instruction sits below it. Arrival time, remaining distance and End route replace the steering bar.
- **Offline maps start from one detected region**, with weekly updates by default (only while parked on Wi-Fi). The full state and region picker stays behind "Add another region".

## Alerts and dialogs

- **Three onroad alert levels.** Info is a small banner and the border stays green. Warning has an amber border and a two-line banner. Critical is a full-screen red takeover. Driving Style Banner only controls personality messages; safety alerts stay visible.
- **New speed limits.** Under Match, a "Higher limits" choice offers **Tap to confirm** (the default) or **Update automatically**.
  - **Lower limits always apply on their own.** If a lower limit waited for a tap, ignoring the prompt would leave the car above the posted limit. In both modes `SLCConfirmationLower` stays off.
  - **Tap to confirm** sets `SLCConfirmation` and `SLCConfirmationHigher` on. A higher limit shows a card on the speed sign with Ignore and Match buttons, ignored after 8 seconds. Pressing Resume on the wheel also matches.
  - **Update automatically** sets `SLCConfirmation` off, so every change applies with no taps. The blue "Matching limit" status chip explains the speed change.
- **Confirm dialogs come in two kinds.** Destructive actions get a red button and a "can't be undone" line. Actions that need a restart get a blue "Restart now" button and a Later option.
- **Every long-running job uses the same four states:** in progress (bar and cancel), blocked (lock icon and the reason, e.g. "park to download"), done (a 4 second toast, never shown while driving) and empty (a short explanation and the next action).

## Remaining screens

- **CAN test recorder**, under Device › Developer with Tuner Mode on: two independently scrolling panels, using the shared settings components. Start and Stop sit above large Mark lock and Mark unlock buttons. Abort stays in the controls header; one tap deletes the current test and resets the page for a retry. The status panel shows elapsed time, received frames, marker counts, the last marker and the session name. Markers describe manual actions; the page never operates the locks. Leaving the page saves the session.
- **Parked home** shows readiness and the current setup, plus Where to? and update status. Detailed device stats move to Developer View.
- **First-run setup** asks three questions: driving style, then speed limits, then lane changes. "Use defaults" skips all three.
- **Driving Model** defaults to the recommended model for the car, which updates automatically. Picking another model means turning Use recommended off. The randomizer and blacklist move to Tuner Mode.
- **Device › General** keeps units, language, brightness (Dimmer / Auto / Brighter), Standby, uploads and weekly backups.
- **Vehicle** shows the detected car with a "Wrong car?" link, which covers `CarMake`, `CarModel` and `ForceFingerprint`. Steering wheel buttons come preset for each car, and Auto-Lock Doors is a single switch.

## Open questions

- **Preset values.** The values each Driving Style and Alert Volume preset writes are placeholders. They need tuning against real drives.
- **Bundle state storage.** When a bundle turns off, the prior values need to be restored. That needs either a saved snapshot per bundle or a rule of "bundle owns these keys while on".
- **Interaction between bundles and Tuner Mode.** If someone overrides one param inside a bundle, is the bundle still "on"? The mocks show it as on, with the override listed under Tuner Mode › Bundle Overrides.
- **Migration.** Existing users have custom values. On first launch, map them to the nearest preset, or show "Custom" until the user picks one.
