# Passive CAN test recorder

Open **Device › Developer › CAN test recorder** with **Tuner Mode** on. Choose **Camera** for the normal receive feed or **OBD** for the Bolt test below. Start logging creates a fresh session. Tap **Mark lock** or **Mark unlock**, then press the matching factory control within about a second. Each accepted tap is timestamped in the UI callback, before the worker writes it. These are operator markers, not confirmation that the locks moved; the human delay between actions remains.

If a test goes wrong, tap **Abort** in the controls header. It stays visible when the panel scrolls. One tap stops the writer and deletes this session's full log, focused log, markers, health and metadata, with no confirmation dialog. It also works just after Stop or a recording error. The background cleanup waits for open files to close; the screen remains responsive. **Discarded** confirms deletion, the counters reset, and **Start logging** creates a clean session. Earlier tests are preserved. A deletion failure keeps the session selected, displays an error and leaves Abort available to retry; a new recording stays blocked until deletion succeeds.

The recorder subscribes to pandad's existing receive feed and sends no CAN messages. Camera mode opens no panda connection. Both modes leave safety, heartbeat, bus speeds and power saving unchanged, and add no upstream integration hooks. Camera mode requires offroad or the existing fresh stationary-Park check. Recording stops when the page hides, permission is lost, storage is low, the time limit elapses (ten minutes for Camera, two for OBD), or one million frames have been received. File work runs outside the UI thread. Stop drains accepted markers and closes the compressed files before displaying Saved. No logger process starts at boot.

With the ignition off, panda power saving can silence auxiliary channels. An empty session therefore does not establish that a particular signal is absent from the vehicle. The page shows a waiting explanation, and the health file records power saving and receive-loss counters.

## Bolt OBD test

The RJ45 cable from the OBD adapter must be connected to the harness box. With this 2023 Bolt EUV powered on, in Park, stationary and controls inactive:

1. Select **OBD**, then **Start logging**. Wait for **OBD frames** to increase; this counts bus 1 separately from the full feed. Do not collect a lock test while it stays at zero.
2. Leave the locks alone for about ten seconds.
3. Tap **Mark lock**, then press the interior Lock switch within a second. Confirm the doors moved. Wait five to eight seconds, then do the same for **Mark unlock** and the Unlock switch. Repeat four or five times, varying the pauses.
4. Wait another ten seconds, then **Stop logging**. **Saved** means the files closed and normal input was restored. **Abort** restores the input and deletes the current log for a clean retry.

`starpilot/tandem/obd.py` selects the spare bus 1 input using panda control request `0xdb`. It never calls `Panda.connect()`, sends CAN, changes the safety policy, or pauses pandad or the UI. Selection requires the exact `CHEVROLET_BOLT_ACC_2022_2023` GM camera fingerprint, one integrated tres panda, GM safety parameter 3, power saving off, and fresh live Park/inactive-control messages. This policy's TX allowlist contains only buses 0 and 2, and its forwarding is only between 0 and 2; bus 1 is receive-only apart from normal CAN acknowledgements. Its TX counter must remain unchanged. Native pandad and the Python SPI handle use the same device flock for each transaction.

An independent child owns the route with a two-second heartbeat lease and a two-minute maximum. Stop, Abort, page closure, parent death, stale messages or lost Park restore the normal input. A file lock prevents overlapping leases. The UI waits for the child's restoration result before Saved or a new test. A restoration failure blocks another test and asks for a device restart. Tests check these upstream safety and SPI assumptions so a merge cannot silently change them. This does not add access to GM single-wire CAN.

## Local files and timing

Sessions stay in `/data/tandem/diagnostics/can-tests/<UTC-date-and-random-suffix>/`, outside the drive-log uploader's folders. On a desktop they use `Paths.comma_home()/tandem/diagnostics/can-tests/`. Nothing here uploads these logs or reports errors automatically. Saved tests remain until manually removed.

| File | Contents |
| --- | --- |
| `metadata.json` | Format version, session, clock, start/ready/end times, input (`camera` or `obd`), vehicle fingerprint/brand/network location, exact focus exclusions, final status, stop reason and counts (including `obd_frames`). OBD adds its bus and safety-policy assumption under `vehicle`. No VIN is added. |
| `can.jsonl.gz` | Full received CAN feed, including messages omitted from the focused copy. Each JSON line is `[logMonoTime_ns, logical_bus, decimal_address, hex_payload]`. Transmit echoes (`src >= 128`) are excluded. |
| `focus.jsonl.gz` | Same format, with the GM driving-message exclusions below applied only on bus 0. Other brands retain every received frame. |
| `markers.jsonl` | One object per accepted tap: `{"time_ns":123,"elapsed_ns":23,"event":"lock"}` or `"unlock"`. |
| `health.jsonl` | pandaStates timestamps, power saving, safety mode, bus speeds, transmit counters, receive loss, receive-buffer overflow, SPI errors and faults. |

CAN and markers share **CLOCK_BOOTTIME** on Linux, matching `common/timing.h` and cereal's `logMonoTime`. The macOS fallback is CLOCK_MONOTONIC, as in the native code. The CAN timestamp is pandad's message timestamp, shared by frames in that batch, rather than an individual hardware-arrival timestamp. For analysis, subtract the session's `started_ns` from CAN times and compare with a marker's `elapsed_ns`. UTC is used only to name the session; it is not used to align events.

## Focus exclusions

These IDs are named in `opendbc/dbc/gm_global_a_powertrain_generated.dbc`. The focused copy omits them **only on logical bus 0** when CarParams identifies the brand as GM. A known message can contain undocumented bits, so the full copy always retains them.

| CAN ID (hex) | Known message |
| --- | --- |
| `0xBE` | ECMAcceleratorPos |
| `0xD1` | EBCMBrakePedalSensors |
| `0xF1` | EBCMBrakePedalPosition |
| `0x180` | ASCMLKASteeringCmd |
| `0x1A1` | AcceleratorPedal |
| `0x1C4` | AcceleratorPedal2 |
| `0x1E5` | PSCMSteeringAngle |
| `0x2CB` | ASCMGasRegenCmd |
| `0x348` | EBCMWheelSpdFront |
| `0x34A` | EBCMWheelSpdRear |

Body/door messages, unknown IDs, diagnostic traffic and traffic on all other buses remain in both copies. Start with the focused copy for readability, then check candidates against the full recording. Do not treat all DBC-known IDs as safe exclusions. The test suite checks that these message names still match the DBC after upstream updates.

## Bolt EUV research leads

The [OVMS Bolt source](https://github.com/openvehicles/Open-Vehicle-Monitoring-System-3/blob/master/vehicle/OVMS.V3/components/vehicle_boltev/src/vehicle_boltev.cpp) has relevant `CommandLock` and `CommandUnlock` implementations, but its [documented vehicle coverage](https://docs.openvehicles.com/en/stable/components/vehicle_boltev/docs/index.html) does not verify our 2023 Bolt EUV.

| ID (hex) | Why inspect it |
| --- | --- |
| `0x241` | OVMS's commented high-speed BCM alternatives for lock, driver unlock and passenger unlock. Their comments distinguish door actuation from alarm arming/disarming. These are unverified leads, not implemented commands. |
| `0x641` | Response-address hypothesis from GM's `+0x400` diagnostic offset, not a confirmed BCM response on this car. |
| `0x1024E097` | OVMS's active OnStar-style lock/unlock path on single-wire CAN, with a wakeup sequence. This requires the appropriate physical network. |
| `0x414000` | Generic low-speed DBC door-command entry; not established as this car's command. |

None of these four IDs appeared in our initial factory-button captures. Factory switches need not generate diagnostic traffic, so that absence does not prove that a diagnostic path is unreachable. The current GM and ELM327 panda transmit policies do not permit requests to `0x241`. This screen neither relaxes those policies nor offers active queries. Any future diagnostic request needs separate review of the network, addressing and permitted operation.
