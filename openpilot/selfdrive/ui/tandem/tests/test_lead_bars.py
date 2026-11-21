"""The lead cars' ground bars on StarPilot 7 (onroad/lead.py, design/leadmarker.html and gaptag.html), drawn by Tandem in
place of StarPilot's red marker."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.onroad import lead as L
from openpilot.starpilot.ui.raylib import rl

ROOT = Path(__file__).resolve().parents[5]


def chevron(x: float, y: float, sz: float) -> list[tuple[float, float]]:
  """StarPilot's marker for a car whose ground point is (x, y), sz tall."""
  return [(x + sz * 1.25, y + sz), (x, y), (x - sz * 1.25, y + sz)]


def test_the_bar_takes_the_markers_place_and_size() -> None:
  rect = L.lead_bar_rect(chevron(500, 400, 40))
  assert rect is not None and rect.x + rect.width / 2 == 500 and rect.width == 100 and rect.y > 400
  far = L.lead_bar_rect(chevron(500, 300, 10))
  assert far is not None and far.width < rect.width
  assert L.lead_bar_rect([]) is None and L.lead_bar_rect(chevron(500, 400, 0)) is None
  assert L.lead_bar_rect(chevron(float("nan"), 400, 40)) is None


@pytest.fixture
def fills(monkeypatch: pytest.MonkeyPatch) -> list[tuple[rl.Rectangle, rl.Color]]:
  drawn: list[tuple[rl.Rectangle, rl.Color]] = []
  monkeypatch.setattr(draw, "fill", lambda rect, color, *_: drawn.append((rect, color)))
  return drawn


def test_white_with_a_dark_outline_amber_when_braking_and_faint_for_other_cars(fills: list) -> None:
  rect = rl.Rectangle(0, 0, 100, 8)
  L.draw_lead_bar(rect, L.LEAD_INK)
  assert len(fills) == 2 and fills[0][0].width > rect.width and fills[1][1].a == L.LEAD_INK.a   # outline, then the bar
  fills.clear()
  L.draw_lead_bar(rect, L.LEAD_BRAKING_INK)
  assert fills[1][1].r == L.LEAD_BRAKING_INK.r
  fills.clear()
  L.draw_lead_bar(rect, L.LEAD_INK, L.LEAD_FAINT, outline=False)
  assert len(fills) == 1 and abs(fills[0][1].a - L.LEAD_INK.a * L.LEAD_FAINT) <= 1   # no outline, 35% opacity


def test_a_new_car_grows_in_from_the_center_and_an_invisible_bar_draws_nothing(fills: list) -> None:
  rect = rl.Rectangle(0, 0, 100, 8)
  L.draw_lead_bar(rect, L.LEAD_INK, scale=0.5, outline=False)
  bar = fills[0][0]
  assert bar.width == 50 and bar.x == 25
  fills.clear()
  L.draw_lead_bar(rect, L.LEAD_INK, opacity=0.0)
  L.draw_lead_bar(rect, L.LEAD_INK, scale=0.0)
  assert fills == []


class Renderer:
  """StarPilot's renderer as the adjacent projection uses it: a straight path and a flat camera."""

  def __init__(self) -> None:
    self._path = SimpleNamespace(raw_points=np.array([[d, 0.0, 0.0] for d in range(0, 100, 5)], dtype=np.float32))
    self._path_offset_z = 1.2
    self._rect = rl.Rectangle(0, 0, 2160, 1080)
    self.projected: list[tuple[float, float, float]] = []

  @staticmethod
  def _get_path_length_idx(xs: np.ndarray, distance: float) -> int:
    return int(np.searchsorted(xs, distance))

  def _map_to_screen(self, x: float, y: float, z: float) -> tuple[float, float] | None:
    self.projected.append((x, y, z))
    return (1080 - y * 100, 600 - x) if x < 90 else None

  def _update_lead_vehicle(self, d_rel: float, v_rel: float, point: tuple[float, float], rect: rl.Rectangle) -> SimpleNamespace:
    return SimpleNamespace(chevron=chevron(point[0], point[1], 30))


def test_a_car_in_the_next_lane_is_projected_as_starpilot_projects_its_leads() -> None:
  renderer = Renderer()
  left = SimpleNamespace(status=True, dRel=30.0, yRel=3.5, vRel=-1.0)
  marker = L.adjacent_chevron(renderer, left)
  assert marker is not None and marker[1] == (1080 + 350, 570)
  assert renderer.projected[-1] == (30.0, -3.5, 1.2)
  assert L.adjacent_chevron(renderer, SimpleNamespace(status=False, dRel=30.0, yRel=0.0, vRel=0.0)) is None
  assert L.adjacent_chevron(renderer, SimpleNamespace(status=True, dRel=95.0, yRel=0.0, vRel=0.0)) is None   # off screen


def test_the_starpilot_renderer_internals_tandem_uses_still_exist() -> None:
  """view.py replaces the renderer's marker drawing and projects adjacent cars with its own helpers."""
  tree = ast.parse((ROOT / "openpilot/selfdrive/ui/onroad/model_renderer.py").read_text())
  methods = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
  assert {"_draw_lead_indicator", "_draw_lead_info", "_get_path_length_idx", "_map_to_screen", "_update_lead_vehicle"} <= methods
  source = (ROOT / "openpilot/selfdrive/ui/onroad/model_renderer.py").read_text()
  assert "self._draw_lead_indicator()" in source and "self._lead_vehicles" in source and "self._path_offset_z" in source
  schema = (ROOT / "openpilot/cereal/custom.capnp").read_text()
  assert "leadLeft @" in schema and "leadRight @" in schema
