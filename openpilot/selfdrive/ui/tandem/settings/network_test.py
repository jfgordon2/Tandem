"""Connections › Network Test (design/connectionstest*.html): the connection's download speed, upload speed and ping.

StarPilot's deviceState says which connection the device is using and whether it's metered, and that sets how much data a
test may use; starpilot/tandem/network_test.py does the measuring. A test runs only while the section is shown.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.blocks import Label
from openpilot.selfdrive.ui.tandem.controls import Button
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.ram import size_text, when_text
from openpilot.starpilot.tandem.network_test import METERED, UNMETERED, Budget, NetworkTest, Phase, Problem, Result


class Via(Enum):
  """What carries the device's connection."""
  NONE = "none"
  WIFI = "wifi"
  CELLULAR = "cellular"
  ETHERNET = "ethernet"


@dataclass(frozen=True)
class Connection:
  """The connection the device is using, as StarPilot reports it."""
  via: Via = Via.NONE
  generation: str = ""    # LTE or 5G, on cellular
  metered: bool = False   # cellular, or Wi-Fi that's a phone's hotspot


GENERATIONS = {"cell2G": "2G", "cell3G": "3G", "cell4G": "LTE", "cell5G": "5G"}
ROWS = [(N_("Download"), N_("Maps, models and updates coming in"), Phase.DOWNLOAD),
        (N_("Upload"), N_("Drive video and logs going out"), Phase.UPLOAD),
        (N_("Ping"), N_("How quickly the internet answers"), Phase.PING)]
PROBLEMS = {Problem.UNREACHABLE: N_("Couldn't reach the speed test. Check the connection and try again."),
            Problem.DROPPED: N_("The connection dropped during the test. Try again."),
            Problem.REFUSED: N_("The speed test turned the request down. Try again later.")}


def device_connection() -> Connection:
  """deviceState's network type and metered flag; no connection until deviceState arrives."""
  from openpilot.selfdrive.ui.ui_state import ui_state
  if not ui_state.sm.valid.get("deviceState", False):
    return Connection()
  state = ui_state.sm["deviceState"]
  kind = str(state.networkType)
  if kind in GENERATIONS:
    return Connection(Via.CELLULAR, GENERATIONS[kind], bool(state.networkMetered))
  via = {"wifi": Via.WIFI, "ethernet": Via.ETHERNET}.get(kind, Via.NONE)
  return Connection(via, metered=bool(state.networkMetered))


def speed_text(bits: float, short: bool = False) -> str:
  """86.4 Mbps, with fewer decimals as the speed grows. short drops one more, for the sidebar's 86 Mbps."""
  mbps = bits / 1e6
  digits = 0 if mbps >= 100 else 1 if mbps >= 10 else 2
  return t_("{} Mbps", f"{mbps:.{max(0, digits - short)}f}")


def ping_text(seconds: float) -> str:
  return t_("{} ms", max(1, round(seconds * 1000)))


def data_text(used: int) -> str:
  return size_text(used) if used >= 2**20 else t_("under 1 MB")


class NetworkTestModel:
  """What the section shows of the tester: the connection it would measure, its button, each row's value and the footnote."""

  def __init__(self, test: NetworkTest, ssid: Callable[[], str | None], connection: Callable[[], Connection] = device_connection) -> None:
    """Makes the section's model.

    Args:
      test: The tester, which keeps the last result.
      ssid: The name of the Wi-Fi network the device is on, if any.
      connection: Reads the connection the device is using.
    """
    self._test, self._ssid, self._connection = test, ssid, connection

  def result(self) -> Result:
    return self._test.result()

  def connection(self) -> str:
    """The header's line: what a test would measure."""
    now = self._connection()
    if now.via is Via.WIFI:
      ssid = self._ssid()
      return t_("{} · {}", N_("Wi-Fi"), ssid) if ssid else N_("Wi-Fi")
    if now.via is Via.CELLULAR:
      return t_("{} · {}", N_("Cellular"), now.generation) if now.generation else N_("Cellular")
    return N_("Ethernet") if now.via is Via.ETHERNET else N_("Not connected")

  def budget(self) -> Budget:
    """The data a test may use: little on cellular, a metered connection, or one StarPilot hasn't reported."""
    now = self._connection()
    return METERED if now.metered or now.via in (Via.NONE, Via.CELLULAR) else UNMETERED

  def press(self) -> None:
    """The header button: stops the running test, or starts one."""
    if self.result().running:
      self._test.stop()
    else:
      self._test.start(self.budget())

  def stop(self) -> None:
    self._test.stop()

  def button(self) -> str:
    result = self.result()
    if result.running:
      return N_("Stop")
    return N_("Start") if result.phase is Phase.IDLE else N_("Test again")

  def measuring(self, phase: Phase) -> bool:
    return self.result().phase is phase

  def value(self, phase: Phase) -> str:
    """A row's value: what's been measured, the download's speed so far while it runs, or nothing yet."""
    result = self.result()
    if phase is Phase.PING:
      return ping_text(result.ping) if result.ping is not None else ""
    speed = result.download if phase is Phase.DOWNLOAD else result.upload
    return speed_text(speed) if speed is not None else ""

  def summary(self) -> str:
    """Beside the section's name: the last download speed."""
    result = self.result()
    if result.running:
      return N_("Testing…")
    return speed_text(result.download, short=True) if result.download is not None else ""

  def footnote(self) -> str:
    """How the last test ended, or the data the next one may use."""
    result = self.result()
    if result.phase is Phase.DONE and result.finished is not None:
      return t_("Tested {} with Cloudflare's speed test. Used {} of data.", when_text(result.finished), data_text(result.used))
    if result.phase is Phase.STOPPED:
      return t_("Stopped early. Used {} of data.", data_text(result.used))
    if result.phase is Phase.FAILED and result.problem is not None:
      return PROBLEMS[result.problem]
    cellular = self._connection().via is Via.CELLULAR
    if result.running and result.budget is not None:
      most = size_text(result.budget.total)
      if cellular:
        return t_("Uses up to {} of cellular data. Leaving this page stops the test.", most)
      return t_("Uses up to {} of data. Leaving this page stops the test.", most)
    most = size_text(self.budget().total)
    if cellular:
      return t_("Uses Cloudflare's speed test and up to {} of cellular data.", most)
    return t_("Uses Cloudflare's speed test and up to {} of data.", most)


def network_test_panel(model: NetworkTestModel) -> ListPanel:
  """Connections › Network Test: Start in the header, then download, upload and ping as each is measured."""
  def measured(title: str, subtitle: str, phase: Phase) -> SettingRow:
    def tint(color: rl.Color) -> Callable[[], rl.Color]:
      return lambda: T.ACCENT_TEXT if model.measuring(phase) else color

    value = Label(lambda: model.value(phase), T.font_px(20), tint(T.TEXT), T.FONT_BOLD, fit=True)
    return SettingRow(title, lambda: N_("Measuring…") if model.measuring(phase) else subtitle, value, subtitle_color=tint(T.TEXT_TERTIARY))

  button = Button(model.button, model.press, height=T.px(42), font_size=T.font_px(15), padding=T.px(16))
  return ListPanel([measured(*spec) for spec in ROWS], title=N_("Network Test"), subtitle=model.connection, header_control=button,
                   footnote=model.footnote, end_divider=True)
