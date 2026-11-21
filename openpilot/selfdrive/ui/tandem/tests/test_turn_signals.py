"""Turn Signal's Whimsy animations on StarPilot 7 (onroad/turn_signals.py) and its Display row (settings/display.py):
Tandem's own packs and preference, drawn crossing the road above the bar while a blinker is on."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openpilot.selfdrive.ui.tandem.onroad import turn_signals as TS
from openpilot.selfdrive.ui.tandem.prefs import TURN_SIGNAL
from openpilot.starpilot.ui.raylib import rl


@pytest.fixture(autouse=True)
def prefs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path))


@pytest.mark.parametrize("slug, frames, seconds", [("frog", 6, 0.125), ("pouncing_cat", 6, 0.125), ("bouncing_ball", 40, 0.075),
                                                   ("unicorn_rider", None, 0.06)])
def test_each_whimsy_pack_ships_its_frames_in_order_and_its_timing(slug: str, frames: int | None, seconds: float) -> None:
  paths = TS.pack_frames(slug)
  assert paths and [TS.frame_number(p) for p in paths] == sorted(TS.frame_number(p) for p in paths)
  assert frames is None or len(paths) == frames
  assert TS.pack_timing(slug) == (seconds, "traditional")
  assert (TS.PACK_PATHS[slug] / TS.BLINDSPOT_FRAME).is_file()
  assert TS.pack_frames(TS.STANDARD) == []


class Scene:
  """rl stand-ins: textures named by their file, and every draw recorded."""

  def __init__(self, monkeypatch: pytest.MonkeyPatch):
    self.draws: list[SimpleNamespace] = []
    self.clock = [100.0]
    monkeypatch.setattr(TS.rl, "load_texture", lambda path: SimpleNamespace(id=1, width=200, height=100, path=Path(path)))
    monkeypatch.setattr(TS.rl, "set_texture_filter", lambda *_: None)
    monkeypatch.setattr(TS.rl, "unload_texture", lambda *_: None)
    monkeypatch.setattr(TS.rl, "draw_texture_pro", lambda texture, source, dest, *_: self.draws.append(
      SimpleNamespace(texture=texture, source=source, dest=dest)))
    monkeypatch.setattr(TS.time, "monotonic", lambda: self.clock[0])
    self.renderer = TS.TurnSignalRenderer()

  def frame(self, pack: str, left: bool = False, right: bool = False, blind: bool = False) -> list[SimpleNamespace]:
    self.draws.clear()
    car = SimpleNamespace(leftBlinker=left, rightBlinker=right, leftBlindspot=blind, rightBlindspot=blind)
    self.renderer.render(rl.Rectangle(0, 0, 2160, 1080), pack, car, 5, bottom_margin=200)
    return list(self.draws)


def test_standard_draws_nothing_and_whimsy_waits_for_a_blinker(monkeypatch: pytest.MonkeyPatch) -> None:
  scene = Scene(monkeypatch)
  assert scene.frame(TS.STANDARD, left=True) == []
  assert scene.frame("frog") == []
  drawn = scene.frame("frog", left=True)
  assert len(drawn) == 1 and drawn[0].texture.path.name == "turn_signal_1.png"
  assert drawn[0].dest.y + drawn[0].dest.height == 1080 - 200   # sits above the bar


def test_a_left_turn_crosses_right_to_left_and_a_right_turn_is_mirrored(monkeypatch: pytest.MonkeyPatch) -> None:
  scene = Scene(monkeypatch)
  start = scene.frame("frog", left=True)[0]
  scene.clock[0] += 0.125 * 5   # the last frame
  end = scene.frame("frog", left=True)[0]
  assert start.dest.x > end.dest.x and start.source.width > 0
  scene.clock[0] += 1
  right = scene.frame("frog", right=True)[0]
  assert right.source.width < 0 and right.texture.path.name == "turn_signal_1.png"   # a new signal starts over


def test_a_car_in_the_blind_spot_shows_the_packs_blind_spot_frame(monkeypatch: pytest.MonkeyPatch) -> None:
  scene = Scene(monkeypatch)
  assert scene.frame("frog", left=True, blind=True)[0].texture.path.name == TS.BLINDSPOT_FRAME


def test_no_car_state_or_no_room_draws_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
  scene = Scene(monkeypatch)
  scene.renderer.render(rl.Rectangle(0, 0, 2160, 1080), "frog", None, 5)
  scene.renderer.render(rl.Rectangle(0, 0, 2160, 150), "frog", SimpleNamespace(leftBlinker=True, rightBlinker=False,
                                                                               leftBlindspot=False, rightBlindspot=False), 5, bottom_margin=200)
  assert scene.draws == []


def test_the_display_row_saves_tandems_own_choice() -> None:
  from openpilot.selfdrive.ui.tandem.settings.display import SIGNAL_STYLES, Display
  display: Any = Display.__new__(Display)
  assert display.signal_style == 0 and display.signal_name() == "Standard" and TURN_SIGNAL.get() is None
  display.set_signal_style([slug for _, slug in SIGNAL_STYLES].index("unicorn_rider"))
  assert TURN_SIGNAL.get() == "unicorn_rider" and display.signal_name() == "Unicorn rider"
  assert [slug for _, slug in SIGNAL_STYLES] == ["standard", "frog", "pouncing_cat", "bouncing_ball", "unicorn_rider"]
