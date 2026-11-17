"""The driver's attention for the monitor tile and the driver camera (onroad/state.py awareness), on real StarPilot 7 messages."""
from __future__ import annotations

from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.selfdrive.ui.tandem.onroad.state import awareness


def monitoring(policy: str, vision: int, wheeltouch: int) -> object:
  dm = log.Event.new_message().init("driverMonitoringState")
  dm.activePolicy = policy
  dm.visionPolicyState.awarenessPercent = vision
  dm.wheeltouchPolicyState.awarenessPercent = wheeltouch
  return dm


def test_the_active_policys_awareness_reads_zero_to_one() -> None:
  assert awareness(monitoring("vision", 80, 10)) == 0.8
  assert awareness(monitoring("wheeltouch", 80, 30)) == 0.3
  assert awareness(monitoring("vision", 120, 0)) == 1.0


def test_a_message_without_awareness_reads_as_unknown() -> None:
  assert awareness(SimpleNamespace(activePolicy="vision")) is None
  assert awareness(None) is None
