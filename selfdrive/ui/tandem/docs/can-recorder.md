# Passive CAN test recorder

Open **Device › Developer › CAN test recorder** with **Tuner Mode** on. Start logging creates a fresh session. Tap **Mark lock** or **Mark unlock** as you press the factory control, then stop logging. Each accepted tap is timestamped in the UI callback, before the worker writes it. These are operator markers, not confirmation that the locks moved; the human delay between actions remains.

The recorder subscribes to pandad's existing receive feed. It sends no CAN messages, opens no panda connection, changes no safety mode or power-saving setting, and adds no upstream integration hooks. Both the page and worker require offroad or the existing fresh stationary-Park check. Recording stops when the page hides, permission is lost, storage is low, ten minutes elapse, or one million frames have been received. File work runs outside the UI thread. Stop drains accepted markers and closes the compressed files before displaying Saved. No logger process starts at boot.

With the ignition off, panda power saving can silence auxiliary channels. An empty session therefore does not establish that a particular signal is absent from the vehicle. The page shows a waiting explanation, and the health file records power saving and receive-loss counters.

## Local files and timing

Sessions stay in `/data/tandem/diagnostics/can-tests/<UTC-date-and-random-suffix>/`, outside the drive-log uploader's folders. On a desktop they use `Paths.comma_home()/tandem/diagnostics/can-tests/`. Nothing here uploads these logs or reports errors automatically. Saved tests remain until manually removed.

| File | Contents |
| --- | --- |
| `metadata.json` | Format version, session, clock, start/ready/end times, vehicle fingerprint/brand/network location, exact focus exclusions, final status, stop reason and counts. No VIN is added. |
| `can.jsonl.gz` | Full received CAN feed, including messages omitted from the focused copy. Each JSON line is `[logMonoTime_ns, logical_bus, decimal_address, hex_payload]`. Transmit echoes (`src >= 128`) are excluded. |
| `focus.jsonl.gz` | Same format, with the GM driving-message exclusions below applied only on bus 0. Other brands retain every received frame. |
| `markers.jsonl` | One object per accepted tap: `{"time_ns":123,"elapsed_ns":23,"event":"lock"}` or `"unlock"`. |
| `health.jsonl` | pandaStates timestamps, power saving, safety mode, bus speeds, receive loss and receive-buffer overflow. |

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
