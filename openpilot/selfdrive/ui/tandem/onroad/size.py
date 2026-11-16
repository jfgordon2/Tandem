"""The driving screen's sizes at Standard or Larger text (Display › Driving Screen › Text Size), and Reduce Motion.

Larger is the onroadlarge* mocks: text, icons and touch targets about 30% larger, in the same places. Onroad code asks
px() and font_px() here, as it draws, instead of tokens', so a change of Text Size takes effect on the next frame.
pick() is for the few places where the larger mocks differ from plain scaling (the speed-limit offer card, narrowed to
end before the speed). The drive screen calls refresh() once a second to follow the settings.
"""
from __future__ import annotations

import time

from openpilot.selfdrive.ui.tandem import tokens as T

LARGER = 1.3
CHECK_S = 1.0

_zoom = 1.0
_reduce_motion = False
_checked = -CHECK_S


def zoom() -> float:
  return _zoom


def larger() -> bool:
  return _zoom > 1.0


def reduce_motion() -> bool:
  return _reduce_motion


def set_text(larger_text: bool, reduce: bool = False) -> None:
  global _zoom, _reduce_motion
  _zoom, _reduce_motion = (LARGER if larger_text else 1.0), reduce


def refresh(now: float | None = None) -> None:
  """Read Text Size and Reduce Motion, at most once a second."""
  global _checked
  now = time.monotonic() if now is None else now
  if now - _checked < CHECK_S:
    return
  _checked = now
  from openpilot.selfdrive.ui.tandem.prefs import LARGER_TEXT, REDUCE_MOTION
  set_text(LARGER_TEXT.get(), REDUCE_MOTION.get())


def px(mock_px: float) -> int:
  """A mock's CSS px in device px, at the current text size."""
  return round(mock_px * T.SCALE * _zoom)


def font_px(mock_px: float) -> int:
  return round(mock_px * T.SCALE * _zoom)


def pick(standard: float, larger_mock: float) -> int:
  """A size in device px from the standard mock, or from the larger mock where it isn't simply scaled."""
  return T.px(larger_mock) if larger() else px(standard)
