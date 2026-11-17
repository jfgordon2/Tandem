"""Render Developer View (panel, strip and detailed lead tag) and the plain lead tag over the stand-in road."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.onroad import developer
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState, bar_height, bar_margin
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, road_rect
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay
from openpilot.selfdrive.ui.tandem.tools.render.scene_onroad_port import mock_road
from openpilot.starpilot.ui.raylib import rl

LEAD = developer.Lead("38 m", "1.4 s", "−2 mph", True, "radar")
DATA = developer.DevData(LEAD, cpu=0.42, cpu_temp="61°C", gpu=0.18, ram=0.39, ram_text="3.1 GB", fps="20", curve="idle",
                         limit_source="map data", metrics=(("ACCEL", "0.31 m/s²"), ("LEARNED DELAY", "0.18000"),
                                                           ("LEARNED FRICTION", "0.12000"), ("STEER RATIO", "15.30000")),
                         accel="+0.31", want="+0.42", lat="1.2 m/s²", delay="0.18 s", steer="−4°")


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Developer View on, then the everyday gap tag."""
  sample = DriveDisplay(BarState(engaged=True, set_speed=63, street="County Road F31"), 62, posted="60", monitor=1.0,
                        arc=ArcState(0.29, 0.0, True))
  full = rl.Rectangle(0, 0, 2160, 1080)
  for name, dev in (("onroaddev", True), ("gaptag", False)):
    rect = rl.Rectangle(0, 0, full.width - developer.WIDTH, full.height) if dev else full
    overlay = OnroadOverlay(lambda: sample, lambda: None, lambda _: None, lambda: None, lambda *_: None)

    def render(rect: rl.Rectangle = rect, overlay: OnroadOverlay = overlay, dev: bool = dev) -> None:
      rl.clear_background(rl.BLACK)
      mock_road(rect)
      inner = road_rect(rect)
      floor = inner.y + inner.height - bar_margin() - bar_height() - developer.strip_gap()
      if dev:
        developer.draw_panel(rl.Rectangle(rect.width, 0, developer.WIDTH, full.height), DATA)
        floor -= developer.strip_h() + developer.strip_gap()
      x = inner.x + inner.width * 0.5
      developer.draw_lead_tag(x, inner.y + inner.height * 0.52, LEAD, compact=not dev, value="1.4 s", anchored=True, bounds=inner, floor=floor)
      overlay.render(rect)
      if dev:
        bottom = inner.y + inner.height - bar_margin() - bar_height() - developer.strip_gap()
        developer.draw_strip(rl.Rectangle(inner.x, bottom - developer.strip_h(), inner.width, developer.strip_h()), DATA)
    frame(render)
    frame(render)
    save(f"{out}/{name}.png")
