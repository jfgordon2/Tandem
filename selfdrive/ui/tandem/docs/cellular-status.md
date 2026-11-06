# Cellular status

Cellular and Roaming, APN and IP address show live status while open. The
approved November 6 mocks are in `design/cellular-status-review/`. The settings
model reads `starpilot/tandem/cellular.py`; no upstream file is changed.

## Collection and memory

One worker owns one system D-Bus connection and polls every two seconds. Drawing
reads only an immutable snapshot under a short lock. Hiding both relevant pages
stops the worker and closes its connection; there is no new resident daemon.
Each D-Bus call has a two-second timeout, with cancellation checked between calls.
Rapid page changes and APN saves invalidate in-flight reads with a generation
counter. Missing, failed, future-dated or more-than-eight-second-old observations
cannot preserve Connected.

The adapter is read-only: no AT commands, internet probes, modem resets or
configuration writes. Existing `WifiManager.update_gsm_settings()` still applies
APN, roaming and Save Data through StarPilot. No credentials, SIM identifiers or
D-Bus payloads are logged or persisted by the adapter.

## State conditions

| State | Evidence |
| --- | --- |
| Checking | Initial, initializing, unknown, unavailable or stale modem information. |
| No SIM | A fresh explicit missing-SIM report, rather than missing telemetry. |
| Connected | ModemManager Connected, a connected bearer matching the mobile interface, and NetworkManager's activated GSM connection. Manual APN must match the bearer. Weak signal does not override an active connection. |
| No signal | SIM present, modem enabled/searching, unregistered/searching registration, no identified access technology, and zero or unavailable recent signal. Zero bars alone are insufficient. |
| Not connected | Fresh failed/denied connection or no active mobile data session. This does not diagnose an APN error. |
| Connecting | A mobile activation is in progress or a saved APN is awaiting confirmation for up to 60 seconds. Explicit no-SIM/no-service/failure information takes precedence. |
| Wi-Fi in use | A default Wi-Fi connection is active, with no confirmed cellular session or explicit cellular failure. Wi-Fi alone cannot confirm the APN. |

After saving an APN, old observations are discarded. A manual APN needs a matching
live bearer. Switching to automatic needs applied automatic settings, a new
session identity or a witnessed disconnection followed by reconnection. A save
alone never turns the badge green. The APN stays saved if coverage is absent.

The cellular address comes only from the matching activated GSM connection's
IPv4/IPv6 configuration. Invalid, unspecified, loopback and link-local addresses
are skipped. A connected session without an available address says Not available.
Connected describes the mobile data session, not independently tested internet
reachability. Signal quality is read only when ModemManager marks it recent.

## Verification

`tests/test_cellular_status.py` covers page visibility, APN saving and live UI
bindings. `starpilot/tandem/tests/test_cellular.py` covers D-Bus observations,
mobile versus Wi-Fi evidence, APN confirmation, expiration, IPv6 and worker
cancellation. `tools/render/scene_cellular.py` renders all nine approved states in
English and expanded pseudo-language. Catalog additions are explicitly marked
English fallbacks pending translation.

On the parked device, open Connections > Cellular, then the APN panel. Save the
carrier's correct APN and stay on that page: Connecting should progress to the
current modem state and show the mobile address when Connected. Return to Wi-Fi
and close settings to verify collection stops. In a place with no coverage, No
signal must retain the APN; an active weak-signal session must remain Connected.
Wi-Fi use must not display Wi-Fi's address as cellular. Do not remove a SIM or
change carrier settings just to exercise mock states.

The device was unreachable over SSH during host validation. Native captures use
deterministic sample observations, so real SIM/APN behavior remains to be checked
on the device after this release is installed.

November 6 host validation: 755 UI tests passed (two skipped); the four files
listed in AGENTS.md that require a full build were excluded. The owned backend
suite passed 331 tests, excluding `test_navigation.py`, `test_routing_cereal.py`,
`test_sentry.py` and `test_telemetry.py`, which require build/device dependencies.
Ruff, translation-template, upstream-hook audit and workflow-policy checks passed.
All nine English and nine expanded pseudo-language captures were inspected.
The pseudo report contains only sample Wi-Fi/APN names, with no missed product
strings. On macOS, captures used `TANDEM_CAPTURE_TEXTURE=1` to avoid window
back-buffer capture artifacts.

## API references

The adapter follows ModemManager's [modem interface](https://github.com/linux-mobile-broadband/ModemManager/blob/main/introspection/org.freedesktop.ModemManager1.Modem.xml),
[3GPP registration](https://github.com/linux-mobile-broadband/ModemManager/blob/main/introspection/org.freedesktop.ModemManager1.Modem.Modem3gpp.xml),
[bearer properties](https://github.com/linux-mobile-broadband/ModemManager/blob/main/introspection/org.freedesktop.ModemManager1.Bearer.xml)
and [state/access-technology enums](https://github.com/linux-mobile-broadband/ModemManager/blob/main/include/ModemManager-enums.h),
plus NetworkManager's [active connection interface](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Connection.Active.html).
