# Cellular connection feedback proposal

Mock review, November 6, 2026. Screen code and existing approved mocks are
unchanged. The owner requested approvals before each UI change; implementation
waits for review of these new mocks.

## Confirmed gap

`settings/network_tab.py` shows hotspot/data controls and APN editing without
live modem status. `Network.edit_apn()` saves the param and calls upstream's
`WifiManager.update_gsm_settings()`. Returning from the keyboard gives no visible
acknowledgement or connection transition. `advanced_panel()` currently reads
`wifi.ipv4_address`, which comes from the active Wi-Fi connection, not the modem.
The parked sidebar independently reads device network state.

## Proposed states

| Mock | When shown |
| --- | --- |
| `cellular-status-connected` | Cellular page, with a current active cellular data connection. Existing hotspot and Save Data rows stay in place. |
| `cellular-apn-connecting` | After APN submission while its new data connection is being established. Saving a value alone does not count as Connected. |
| `cellular-apn-connected` | APN panel after a fresh modem report confirms an active cellular data connection; show its address when available. |
| `cellular-apn-not-connected` | Current modem information confirms no active cellular data connection. Suggest checking APN, signal and carrier account without claiming which is at fault. |
| `cellular-apn-no-sim` | Fresh modem information explicitly reports no SIM. Missing/unavailable telemetry must not be interpreted as an absent SIM. |
| `cellular-apn-wifi` | Wi-Fi is in use and a cellular data connection has not been confirmed. Wi-Fi internet access does not prove the APN works. |
| `cellular-apn-checking` | Initial collection or unavailable/stale modem information; do not preserve an old green Connected badge. |

The same status belongs in the Cellular header and APN header, updating while
the page stays open. The APN panel adds a short explanatory line beneath APN and
labels its address **Cellular IP address**. Carrier APN and IP strings in the
mocks are examples, not carrier configuration advice.

Connected describes an active modem data connection. These mocks do not claim
an independent internet reachability test. They add no automatic HTTP probes,
network resets or new driver setup steps.

## Implementation after approval

- Use existing `ListPanel` title/subtitle/header-control, `Badge`, rows and text;
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
- Add test/render states and comparison entries after approval. Until then these
  screenshots are proposals, not captures of implemented screens.

Open [the review page](index.html) for all states. The seven root HTML mocks have
matching screenshots under `design/screenshots/`.
