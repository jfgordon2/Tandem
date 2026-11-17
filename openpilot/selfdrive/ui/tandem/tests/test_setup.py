"""First-run setup (setup.py): the Essentials defaults, then the driver's three answers, on StarPilot's settings rows."""
from __future__ import annotations

from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem import prefs
from openpilot.selfdrive.ui.tandem.setup import QUESTIONS, Setup
from openpilot.selfdrive.ui.tandem.tests.test_defaults import BatchStore
from openpilot.selfdrive.ui.tandem.tests.test_display_alerts_port import FakeRoad
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner, page
from openpilot.selfdrive.ui.tandem.tools.render.scene_driving import example_owner


@pytest.fixture
def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Owner:
  monkeypatch.setattr(prefs, "prefs_dir", lambda: tmp_path)
  return example_owner()


def test_answers_apply_after_the_defaults_and_auto_lane_changes_ask_after_setup_closes(owner: Owner) -> None:
  events: list[str] = []
  store = BatchStore()

  def confirm(title: str, message: str, label: str, action) -> None:
    events.append("asked")
    action()
  setup = Setup(store, owner.rows, FakeRoad(), lambda: events.append("closed"), confirm)  # type: ignore[arg-type]
  setup.pick(2)        # Sport
  setup.next()
  setup.pick(1)        # Show
  setup.next()
  setup.pick(1)        # Auto
  setup.next()         # Start driving
  assert events == ["closed", "asked"]
  assert store.values["LongitudinalPersonality"] == 0 and page(owner, "slc")["SpeedLimitController"] == "Off"
  assert page(owner, "slc")["ShowSpeedLimits"] == "On" and page(owner, "lane_change")["lane_change:auto"] == "On"


def test_use_defaults_skips_the_answers(owner: Owner) -> None:
  closed: list[bool] = []
  setup = Setup(BatchStore(), owner.rows, FakeRoad(), lambda: closed.append(True))  # type: ignore[arg-type]
  setup.pick(0)
  setup.finish(use_answers=False)
  assert closed and page(owner, "slc")["SpeedLimitController"] == "On" and page(owner, "lane_change")["lane_change:auto"] == "Off"
  assert [q.default for q in QUESTIONS] == [1, 2, 0]
