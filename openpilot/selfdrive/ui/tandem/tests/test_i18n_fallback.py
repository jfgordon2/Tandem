"""Tandem's lookup falls back to StarPilot's own catalog for StarPilot's row labels (i18n.translate)."""
from __future__ import annotations

import pytest

from openpilot.selfdrive.ui.tandem import i18n
from openpilot.system.ui.lib import multilang as upstream


def test_tandem_first_then_starpilots_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(i18n, "_catalog", lambda: i18n.Catalog({"Offline Maps": "Offline-Karten"}, "de"))
  monkeypatch.setattr(upstream.multilang, "tr", lambda text: {"Minimum lane-change speed": "Mindestgeschwindigkeit"}.get(text, text))
  assert i18n.translate("Offline Maps") == "Offline-Karten"
  assert i18n.translate("Minimum lane-change speed") == "Mindestgeschwindigkeit"
  assert i18n.translate("Unknown text") == "Unknown text"


def test_english_never_asks_starpilot(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setattr(i18n, "_catalog", lambda: None)
  monkeypatch.setattr(upstream.multilang, "tr", lambda text: pytest.fail("English needs no lookup"))
  assert i18n.translate("Minimum lane-change speed") == "Minimum lane-change speed"
