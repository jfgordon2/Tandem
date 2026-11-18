"""Unattended diagnostics stay on the device; explicit user reports may still be sent.

Tandem's fork-wide policy, independent of the UI switches: StarPilot's crash-reporting SDK (system/sentry.py) sends
exceptions and native crash dumps on its own. sentry_options() adds a filter so those stay on the device, where
StarPilot still writes its crash logs; only an event tagged as a report the driver chose to send passes. Tandem's
Report a Problem goes through StarPilot's separate Bugsink sender (starpilot/tandem/issue_report.py), not the SDK.
"""
from __future__ import annotations

from typing import Any

AUTOMATIC_DIAGNOSTICS_ENABLED = False
MANUAL_REPORT_TYPES = frozenset({"manual_issue_report", "flm_tune_submission"})


def _manual_reports_only(event: dict, hint: dict) -> dict | None:
  return event if (event.get("tags") or {}).get("report_type") in MANUAL_REPORT_TYPES else None


def _no_transactions(event: dict, hint: dict) -> None:
  return None


def sentry_options() -> dict[str, Any]:
  """Extra options for StarPilot's sdk.init; ones it already sets (integrations, sessions, tracing) aren't repeated."""
  if AUTOMATIC_DIAGNOSTICS_ENABLED:
    return {}
  return {"before_send": _manual_reports_only, "before_send_transaction": _no_transactions, "send_client_reports": False}
