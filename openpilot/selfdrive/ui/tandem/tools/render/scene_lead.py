"""The lead car's tag (design/gaptag.html) and its ground bars (leadmarker.html), over a stand-in road: following,
braking, stopped, unsure, detailed and acquiring, then the bar shown with Lead Car Tag off and the faint bars for other
cars. Release's scene_lead.py on StarPilot 7's scene helpers."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.onroad.developer import draw_lead_tag
from openpilot.selfdrive.ui.tandem.onroad.lead import (LEAD_BRAKING_INK, LEAD_FAINT, LEAD_INK, GapTracker, LeadSample, draw_lead_bar,
                                                       lead_anchor, lead_bar_rect)
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay
from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
from openpilot.starpilot.ui.raylib import rl
from scene_onroad_port import mock_road

RECT = rl.Rectangle(0, 0, 2160, 1080)


def chevron(x: float, y: float, d_rel: float) -> list[tuple[float, float]]:
  """StarPilot's marker for a lead at screen point (x, y), d_rel meters ahead (ModelRenderer._update_lead_vehicle)."""
  sz = min(max((25 * 30) / (d_rel / 3 + 30), 15.0), 30.0) * 2.35
  return [(x + sz * 1.25, y + sz), (x, y), (x - sz * 1.25, y + sz)]


def car(x: float, y: float, w: float) -> None:
  body = rl.Rectangle(x - w / 2, y - w * 0.55, w, w * 0.55)
  draw.fill(body, rl.Color(0x2A, 0x31, 0x38, 255), w * 0.12)
  draw.fill(rl.Rectangle(body.x + w * 0.12, body.y + w * 0.08, w * 0.76, w * 0.15), rl.Color(0x3B, 0x44, 0x4E, 255), 6)
  for lx in (body.x + w * 0.06, body.x + w * 0.78):
    draw.fill(rl.Rectangle(lx, body.y + w * 0.38, w * 0.16, w * 0.08), rl.Color(0xC2, 0x41, 0x4B, 255), 3)


def lead_scene(braking: bool = False, adjacent: bool = False, *, tag: bool = True, speed: float = 20.0, distance: float = 32.0,
               metric: bool = False, confident: bool = True, details: bool = False, elapsed: float = 0.25) -> Callable[[], None]:
  """One driving frame with a lead car, drawn as onroad/view.py draws it."""
  chip = chip_for(Snapshot(slowing_for_lead=True, speed=12.0, accel=-1.0)) if braking else None
  unit = "km/h" if metric else "mph"
  sample_display = DriveDisplay(BarState(engaged=True, set_speed=48, unit=unit, street="Market Street"),
                                round(speed * (CV.MS_TO_KPH if metric else CV.MS_TO_MPH)), monitor=1.0, arc=ArcState(0.1, 0.1, True),
                                chips=((chip, 1.0),) if chip is not None else ())
  noop = lambda *args: None  # noqa: E731
  overlay = OnroadOverlay(lambda: sample_display, noop, noop, noop, noop, clock=lambda: .5)
  tracker = GapTracker()
  sample = LeadSample(distance, speed, -2.0, metric=metric, confident=confident)
  tracker.update(sample, 0.0)
  state = tracker.update(sample, elapsed)

  def render() -> None:
    mock_road(RECT)
    x, y = 1080, 560
    car(x, y, 120)
    marker = chevron(x, y, distance)
    if tag:
      anchor = lead_anchor(marker)
      assert state is not None and anchor is not None
      draw_lead_tag(anchor.x, anchor.y, state.lead, compact=not details, value=state.label, anchored=True, braking=braking,
                    opacity=state.opacity, progress=state.progress, bounds=rl.Rectangle(15, 15, 2130, 1050))
    else:
      bar = lead_bar_rect(marker)
      if bar is not None and state is not None:
        draw_lead_bar(bar, LEAD_BRAKING_INK if braking else LEAD_INK, state.opacity, state.progress)
    if adjacent:
      car(760, 600, 110)
      faint = lead_bar_rect(chevron(760, 600, 26))
      if faint is not None:
        draw_lead_bar(faint, LEAD_INK, LEAD_FAINT, outline=False)
    overlay.render(RECT)
  return render


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  shots = [
    ("lead_following", lead_scene(adjacent=True)), ("lead_braking", lead_scene(True)),
    ("gap_stopped", lead_scene(speed=0.0, distance=8.0, metric=True)), ("gap_stopped_imperial", lead_scene(speed=0.0, distance=8.0)),
    ("gap_uncertain", lead_scene(confident=False)), ("gap_developer", lead_scene(details=True)),
    ("gap_acquire_40", lead_scene(elapsed=0.04)), ("gap_acquire_120", lead_scene(elapsed=0.12)),
    ("gap_acquire_250", lead_scene(elapsed=0.25)),
    # Lead Car Tag off (leadmarker.html): the ground bar alone.
    ("leadmarker_following", lead_scene(tag=False, adjacent=True)), ("leadmarker_braking", lead_scene(True, tag=False)),
    ("leadmarker_unsure", lead_scene(tag=False, confident=False)), ("leadmarker_new", lead_scene(tag=False, elapsed=0.1)),
  ]
  for name, render in shots:
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
