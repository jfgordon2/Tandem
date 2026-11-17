"""Submit driver-requested issue reports through StarPilot's existing Bugsink transport."""
from __future__ import annotations

from collections.abc import Callable


def send_issue(issue: str, discord: str, authorize: Callable[[], bool]) -> bool:
  """Send the form and its RAM summary with the manual issue tag and require delivery confirmation."""
  from openpilot.starpilot.system.starport.bugsink_transport import Sender, device_metadata
  from openpilot.system.sentry import SentryProject

  if not authorize():
    return False
  sender = Sender(SentryProject.SELFDRIVE.value, metadata=device_metadata(), active=authorize,
                  logger="manual_issue_report", client="tandem-report/1", schema_tags={})
  return bool(sender(message=issue, level="error", tags={"report_type": "manual_issue_report"},
                     extra={"discord_user": discord} if discord else {}))
