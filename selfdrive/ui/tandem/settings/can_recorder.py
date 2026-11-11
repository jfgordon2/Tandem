"""A passive diagnostic page built from the shared settings panels and buttons."""
from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Columns, Label, Stack, ValueLine
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonRow, ButtonStyle, Segmented, Tone
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, Text
from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
from openpilot.starpilot.tandem.can_recorder import ACTIVE, CanRecorder, boot_time_ns

if TYPE_CHECKING:
  import pyray as rl
  from openpilot.starpilot.tandem.can_recorder import CanRecorder

PHASES = {"idle": N_("Ready"), "starting": N_("Starting…"), "recording": N_("Recording"),
          "saving": N_("Saving…"), "saved": N_("Saved"), "error": N_("Error"),
          "aborting": N_("Discarding…"), "discarded": N_("Discarded")}


def recording_allowed() -> bool:
  from openpilot.selfdrive.ui.ui_state import ui_state
  from openpilot.starpilot.tandem.bluetooth import stationary_park
  return ui_state.is_offroad() or stationary_park(ui_state.sm)


def duration(ns: int) -> str:
  ms = max(0, ns)//1_000_000
  return f"{ms//60_000:02d}:{(ms//1000)%60:02d}.{ms%1000:03d}"


class CanRecorderPage(Component):
  """Device › Developer › CAN test recorder: start, mark and stop a logged test drive."""
  grow_touch_target = False

  def __init__(self, recorder: CanRecorder | None = None, allowed: Callable[[], bool] = recording_allowed, clock_ns: Callable[[], int] = boot_time_ns) -> None:
    super().__init__()
    self.recorder = recorder if recorder is not None else CanRecorder()
    self._allowed, self._clock_ns = allowed, clock_ns
    self.state = self.recorder.snapshot()
    self._obd = False
    self._input = Segmented([N_("Camera"), N_("OBD")], lambda: int(self._obd), self.set_input, equal=True)
    self._input.set_enabled(lambda: self.state.phase not in ACTIVE)
    self._start = Button(N_("Start logging"), self.start, ButtonStyle.PRIMARY, height=T.px(56), font_size=T.font_px(19), radius=T.px(14))
    self._start.set_enabled(lambda: self.state.phase not in ACTIVE and self.state.reason not in {"delete", "obd_restore"} and self._allowed())
    self._stop = Button(N_("Stop logging"), self.recorder.stop, height=T.px(56), font_size=T.font_px(19), radius=T.px(14))
    self._stop.set_enabled(lambda: self.state.phase in {"starting", "recording"})
    self._abort = Button(N_("Abort"), self.abort, ButtonStyle.DANGER_SOFT,
                         height=T.px(44), font_size=T.font_px(16), radius=T.px(14))
    self._abort.set_enabled(lambda: bool(self.state.session) and self.state.phase != "aborting")
    self._mark_lock = self._marker(N_("Mark lock"), "lock")
    self._mark_unlock = self._marker(N_("Mark unlock"), "unlock")
    controls = ListPanel([Padded(Stack([
      Text(N_("Tap a marker, then press the car's lock control."), size=T.font_px(15), padding=(0, 0)),
      Columns([Label(N_("Input"), size=T.font_px(16), color=T.TEXT_MUTED, weight=T.FONT), self._input], [1, 6]),
      ButtonRow([self._start, self._stop], height=T.px(56), gap=T.px(12)),
      ButtonRow([self._mark_lock, self._mark_unlock], height=T.px(88), gap=T.px(12)),
      Text(lambda: N_("Abort deletes this test. OBD stops after 2 minutes.") if self._obd
           else N_("Stops after 10 minutes. Abort deletes this test."), padding=(0, 0)),
    ], gap=T.px(14)), x=T.px(22), y=T.px(20))], title=N_("Test controls"), dividers=False, header_divider=False, header_control=self._abort)
    self._obd_count = ValueLine(N_("OBD frames"), lambda: f"{self.state.obd_frames:,}")
    self._obd_count.set_visible(lambda: self._obd or self.state.input == "obd")
    status = ListPanel([Padded(Stack([
      ValueLine(N_("Elapsed"), self.elapsed, size=T.font_px(22)),
      ValueLine(N_("CAN frames"), lambda: f"{self.state.frames:,}"),
      self._obd_count,
      ValueLine(N_("Lock markers"), lambda: str(self.state.lock_markers)),
      ValueLine(N_("Unlock markers"), lambda: str(self.state.unlock_markers)),
      Text(self.detail, padding=(0, 0)),
      Text(lambda: t_("Log: {}", self.state.session) if self.state.session else N_("Start logging to create a new test log."),
           size=T.font_px(13), padding=(0, 0)),
      Text(N_("Full and focused logs stay on this device."), padding=(0, 0)),
    ], gap=T.px(10)), x=T.px(22), y=T.px(18))], title=N_("Test status"), dividers=False, header_divider=False,
      header_control=Badge(lambda: PHASES[self.state.phase], lambda: Tone.DANGER if self.state.phase == "error" else Tone.ACCENT))
    self._page = self._child(TitledPage(N_("CAN test recorder"), N_("Device › Developer"), Columns([controls, status], [1.25, 1])))

  def _marker(self, title: str, kind: str) -> Button:
    def mark() -> None:
      self.recorder.mark(kind)
    button = Button(title, mark, ButtonStyle.PRIMARY, height=T.px(88), font_size=T.font_px(22),
                    radius=T.px(14), weight=T.FONT_EXTRABOLD)
    button.set_enabled(lambda: self.state.phase == "recording")
    return button

  def abort(self) -> None:
    self.recorder.abort()

  def start(self) -> None:
    if self._allowed():
      self.recorder.start(obd=self._obd)

  def set_input(self, index: int) -> None:
    if self.state.phase not in ACTIVE:
      self._obd = bool(index)

  def elapsed(self) -> str:
    end = self.state.ended_ns or self._clock_ns()
    return duration(end-self.state.started_ns) if self.state.session else "00:00.000"

  def detail(self) -> str:
    """The page's explanation of the recorder's state: what went wrong, or what to do next."""
    if self.state.phase == "discarded":
      return N_("Test discarded. Start a new test.")
    if self.state.phase == "error":
      if self.state.reason == "delete":
        return N_("Couldn't delete the log. Try Abort again.")
      if self.state.reason == "obd_restore":
        return N_("Couldn't restore the input. Restart the device before another test.")
      if self.state.reason == "obd":
        return N_("OBD needs the RJ45 cable and this Bolt on, in Park.")
      if self.state.reason == "parked":
        return N_("OBD needs the RJ45 cable and this Bolt on, in Park.") if self.state.input == "obd" else N_("Park the car to start a test.")
      return N_("Couldn't save the log. Check storage and try again.")
    if self.state.phase == "saved" and self.state.reason == "parked":
      return N_("Saved: the car is no longer parked.")
    if self.state.phase == "saved" and self.state.reason == "storage":
      return N_("Saved: storage is running low.")
    if self.state.phase == "saved" and self.state.reason in {"time_limit", "frame_limit"}:
      return N_("Saved: the recording limit was reached.")
    if self.state.phase == "saved" and self.state.reason == "obd_guard":
      return N_("Saved: OBD test ended and normal input restored.")
    if self.state.last_kind:
      kind = N_("Lock") if self.state.last_kind == "lock" else N_("Unlock")
      return t_("Last marker: {} at {}", kind, duration(self.state.last_marker_ns-self.state.started_ns))
    if self.state.phase == "recording" and self.state.input == "obd" and self.state.obd_frames == 0:
      return N_("Waiting for OBD traffic. Check the RJ45 cable.")
    if self.state.phase == "recording" and self.state.frames == 0:
      return N_("Waiting for CAN traffic. Some channels sleep with the car off.")
    return N_("No markers yet.") if self._allowed() else N_("Park the car to start a test.")

  def _update_state(self) -> None:
    self.state = self.recorder.snapshot()

  def hide_event(self) -> None:
    self.recorder.stop("screen_closed")
    super().hide_event()

  def _render(self, rect: rl.Rectangle) -> None:
    self._page.render(rect)
