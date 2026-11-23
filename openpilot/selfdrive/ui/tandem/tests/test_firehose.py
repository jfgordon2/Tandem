"""Device › Firehose (settings/firehose.py, design/firehose.html): StarPilot's status rule and the page's content."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem.rows import SectionHeader
from openpilot.selfdrive.ui.tandem.settings import firehose as F


def test_active_only_when_connected_without_a_data_limit() -> None:
  assert F.active(1, metered=False)        # Wi-Fi
  assert not F.active(1, metered=True)     # a metered network
  assert not F.active(0, metered=False)    # no connection


def test_the_page_has_the_status_tips_and_starpilots_four_questions() -> None:
  panel = F.firehose_panel(lambda: True)
  items = panel.items
  assert isinstance(items[0]._content, F.FirehoseStatus)   # the status card leads
  headers = [item._label for item in items if isinstance(item, SectionHeader)]
  assert headers == ["GET THE MOST FROM IT", "QUESTIONS"]
  answers = [item for item in items if isinstance(item, F.Answer)]
  assert [a._question for a in answers] == [q for q, _ in F.QUESTIONS] and len(answers) == 5
  assert answers[0]._question == "Can I turn it off?"   # there's no switch, and the page says so first
  assert [a._last for a in answers] == [False, False, False, False, True]   # no divider under the last
