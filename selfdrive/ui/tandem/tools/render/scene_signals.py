import time
from types import SimpleNamespace
import pyray as rl
from openpilot.selfdrive.ui.onroad.starpilot import turn_signals as TS
from openpilot.selfdrive.ui.tandem.onroad import extras
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState, bar_height, bar_margin
from scene_onroad import scene


class SM(dict):
  def __init__(self, cs):
    super().__init__(carState=cs)
    self.valid = {"carState": True}
    self.alive = {"carState": True}
    self.recv_frame = {"carState": 10}


def main(frame, save, out, tap, gui_app):
  for slug, t in (("frog", 0.3), ("pouncing_cat", 0.5), ("bouncing_ball", 1.4)):
    renderer = TS.TurnSignalRenderer()
    cs = SimpleNamespace(leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False)
    state = SimpleNamespace(starpilot_toggles={"signal_icons": slug}, sm=SM(cs), started=True, started_frame=1)
    base = scene(BarState(True, True, 48, "mph", "Market Street"), ArcState(0.1, 0.1, True), None, speed=44, signal="left")
    def render(base=base, renderer=renderer, state=state):
      base()
      renderer.render(rl.Rectangle(15, 15, 2130, 1050), state, bottom_margin=bar_height() + bar_margin() + extras.SIGNAL_GAP)
    frame(render)
    renderer._started_at = time.monotonic() - t   # a frame partway across
    frame(render)
    save(f"{out}/signal_{slug}.png")
