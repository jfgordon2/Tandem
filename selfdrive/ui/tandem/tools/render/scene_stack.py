from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, Snapshot


def stacked():
  stack = ChipStack()
  stack.update(Snapshot(curve_control=True), 0.0, False)
  stack.update(Snapshot(curve_control=True, weather="Rain", weather_gap=True), 0.4, False)
  stack.update(Snapshot(curve_control=True, weather="Rain", weather_gap=True, limit_changed=True, speed_limit=45), 0.8, False)
  return stack.update(Snapshot(weather="Rain", weather_gap=True, limit_changed=True, speed_limit=45), 2.95, False)   # the curve chip fading


def low_memory():
  """The curve chip, then Low memory arriving after it, nearest the bar (design/memorychip.html)."""
  stack = ChipStack()
  stack.update(Snapshot(curve_control=True), 0.0, False)
  return stack.update(Snapshot(curve_control=True, events={"lowMemory"}, memory_percent=91), 0.4, False)
