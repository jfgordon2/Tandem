"""The driving screen's model chip on StarPilot 7 (onroad/extras.ModelChip): Jetlink's state as release's model chip."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem.onroad.extras import SHOW_S, ModelChip


def test_loading_shows_throughout_and_pulses() -> None:
  chip = ModelChip()
  first = chip.update("connecting", 0.0)
  later = chip.update("ready", 100.0)
  assert first is not None and later is not None and first[0] == later[0] == "loading" and 0.35 <= later[1] <= 1.0


def test_a_change_shows_briefly_then_fades() -> None:
  chip = ModelChip()
  chip.update("ready", 0.0)
  assert chip.update("active", 10.0) == ("active", 1.0)
  assert chip.update("active", 10.0 + SHOW_S + 0.25) == ("active", 0.5)
  assert chip.update("active", 10.0 + SHOW_S + 1.0) is None
  assert chip.update("disconnected", 20.0) == ("fallback_engaged", 1.0)
  assert chip.update("unavailable", 30.0) == ("failed", 1.0)


def test_off_shows_nothing() -> None:
  assert ModelChip().update("off", 0.0) is None
