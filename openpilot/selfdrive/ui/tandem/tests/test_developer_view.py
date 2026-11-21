"""Developer View's strip (onroad/developer.py) in other languages: labels translated, a gap before each value, and long
labels shortened before the numbers are."""
from __future__ import annotations

import pytest

from openpilot.selfdrive.ui.tandem import draw, i18n
from openpilot.selfdrive.ui.tandem.onroad import developer as D
from openpilot.starpilot.ui.raylib import rl


def test_strip_translates_labels_and_keeps_a_gap_before_values(monkeypatch: pytest.MonkeyPatch) -> None:
  labels = []
  monkeypatch.setattr(draw, "fill", lambda *args: None)
  monkeypatch.setattr(draw, "text_width", lambda *args: 20)
  monkeypatch.setattr(draw, "fit", lambda value, *args: value)
  monkeypatch.setattr(draw, "text", lambda rect, value, *args: labels.append((rect, value)))
  for code, expected in (("es", ["acel.", "objetivo", "dirección"]), ("ar", ["تسارع", "مطلوب", "توجيه"])):
    monkeypatch.setattr(i18n, "_language", lambda c=code: c)
    labels.clear()
    D.draw_strip(rl.Rectangle(0, 0, 1200, D.strip_h()), D.DevData(strip=("accel", "want", "steer")))
    assert [value for _, value in labels[::2]] == expected
    for (label, _), (value, _) in zip(labels[::2], labels[1::2], strict=True):
      assert value.x > label.x + label.width


def test_long_translated_strip_labels_fit_without_shortening_the_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(D, "translate", lambda value: "long translated metric label" * 20)
  monkeypatch.setattr(draw, "fill", lambda *args: None)
  monkeypatch.setattr(draw, "text_width", lambda value, *args: len(value))
  monkeypatch.setattr(draw, "fit", lambda value, size, weight, width: value[:int(width)])
  drawn = []
  monkeypatch.setattr(draw, "text", lambda rect, value, *args: drawn.append((rect, value)))
  rect = rl.Rectangle(0, 0, 1200, D.strip_h())
  data = D.DevData()
  D.draw_strip(rect, data)
  cells = D.row(D.inset(rect, x=D.T.px(20)), [D.FILL] * len(data.strip), D.T.px(12))
  for (label, _), (value, text), cell, (_, expected) in zip(drawn[::2], drawn[1::2], cells, data.strip_values(), strict=True):
    assert label.x >= cell.x and value.x + value.width <= cell.x + cell.width
    assert text == expected
