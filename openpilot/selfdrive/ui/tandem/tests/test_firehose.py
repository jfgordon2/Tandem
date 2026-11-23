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


def test_a_real_capnp_network_enum_reads_without_crashing(tmp_path) -> None:
  """deviceState.networkType is a capnp enum on the device, which int() rejects; opening Firehose crashed on it."""
  import capnp
  schema = tmp_path / "device.capnp"
  schema.write_text("@0xd4a4f0a1c0ffee01;\nstruct DeviceState { networkType @0 :Net; networkMetered @1 :Bool;\n"
                    "  enum Net { none @0; wifi @1; cell4G @2; } }\n")
  message = capnp.load(str(schema)).DeviceState.new_message()
  message.networkType = "wifi"
  assert F.state_active(message)
  message.networkMetered = True
  assert not F.state_active(message)
  message.networkType, message.networkMetered = "none", False
  assert not F.state_active(message)
