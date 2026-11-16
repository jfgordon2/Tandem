# Cellular connection feedback

Approved for implementation on November 6, 2026, including the No signal states.
The nine approved HTML mocks and screenshots are preserved. The implementation
uses shared Essentials components and adds no upstream hooks.

## Confirmed gap

`settings/network_tab.py` shows hotspot/data controls and APN editing without
live modem status. `Network.edit_apn()` saves the param and calls upstream's
`WifiManager.update_gsm_settings()`. Returning from the keyboard gives no visible
acknowledgement or connection transition. `advanced_panel()` currently reads
`wifi.ipv4_address`, which comes from the active Wi-Fi connection, not the modem.
The parked sidebar independently reads device network state.

## Approved states

| Mock | When shown |
| --- | --- |
| `cellular-status-connected` | Cellular page, with a current active cellular data connection. Existing hotspot and Save Data rows stay in place. |
| `cellular-status-no-signal` | SIM is detected and fresh modem information confirms no cellular service. Show an amber No signal badge while keeping the existing controls. |
| `cellular-apn-connecting` | After APN submission while its new data connection is being established. Saving a value alone does not count as Connected. |
| `cellular-apn-connected` | APN panel after a fresh modem report confirms an active cellular data connection; show its address when available. |
| `cellular-apn-no-signal` | SIM is detected but there is no cellular service. Explain that the APN stays saved; do not suggest it is wrong solely because coverage is absent. |
| `cellular-apn-not-connected` | Current modem information confirms no active cellular data connection. Suggest checking APN, signal and carrier account without claiming which is at fault. |
| `cellular-apn-no-sim` | Fresh modem information explicitly reports no SIM. Missing/unavailable telemetry must not be interpreted as an absent SIM. |
| `cellular-apn-wifi` | Wi-Fi is in use and a cellular data connection has not been confirmed. Wi-Fi internet access does not prove the APN works. |
| `cellular-apn-checking` | Initial collection or unavailable/stale modem information; do not preserve an old green Connected badge. |

The same status belongs in the Cellular header and APN header, updating while
the page stays open. The APN panel adds a short explanatory line beneath APN and
labels its address **Cellular IP address**. Carrier APN and IP strings in the
mocks are examples, not carrier configuration advice.

No signal is distinct from missing SIM, stale status and a failed data connection
with service present. Zero bars alone do not establish it: an active cellular
data connection stays Connected with its actual weak signal strength. When
service returns, status follows the modem's normal connecting/connected states;
the UI does not clear the APN or add modem resets.
An explicit no-SIM or no-service report takes precedence over Wi-Fi in use, so
Wi-Fi cannot hide a known cellular problem.

Connected describes an active modem data connection. These mocks do not claim
an independent internet reachability test. They add no automatic HTTP probes,
network resets or new driver setup steps.

## Implementation

- Use existing `ListPanel` title/subtitle/header-control, a shared `StatusBadge`, rows and text;
  keep the existing settings footer and the APN panel's Back button.
- Read current modem/device state through an owned, asynchronous status adapter.
  Do not block drawing with D-Bus, AT commands or network checks. Stop page-only
  collection when the relevant settings pages close; add no resident process.
- Keep StarPilot's APN, roaming and Save Data params and apply methods. Recheck
  fresh connection information after a save; do not relabel a pre-save bearer
  Connected merely because the param write succeeded.
- Source SIM, signal and cellular address from modem/mobile connection data.
  Do not use Wi-Fi signal or address as cellular evidence.
- Update settings search, mark new driver text for translation, update catalogs
  and verify pseudo-language layout when the screen changes are implemented.
- Test/render states and comparison entries cover every approved mock. Native
  captures use sample modem data; live SIM/APN acceptance remains a device check.

The adapter and its state conditions are described in
[`docs/cellular-status.md`](../../docs/cellular-status.md). The native screens use
the library's standard row/header geometry and tone palette, as recorded in the
main README's mock differences. New strings use documented English fallbacks
until translated. No approved mock was changed during implementation.

Open [the review page](index.html) for all states. The nine root HTML mocks have
matching screenshots under `design/screenshots/`.
