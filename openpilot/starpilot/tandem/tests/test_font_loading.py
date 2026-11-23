"""Tandem's font deferral (starpilot/tandem/font_loading.py): which Inter faces wait, and the log line when one loads."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem import font_loading


def test_inter_waits_only_for_tandems_big_screens() -> None:
  assert font_loading.defer_inter(True, {})
  assert not font_loading.defer_inter(False, {})
  assert not font_loading.defer_inter(True, {"STARPILOT_UI": "upstream"})
  off = dict.fromkeys(("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR"), "0")
  assert not font_loading.defer_inter(True, off)


def test_a_deferred_face_logs_what_loaded_it_and_still_loads(monkeypatch: pytest.MonkeyPatch) -> None:
  from openpilot.common import swaglog
  logged: list[str] = []
  monkeypatch.setattr(swaglog.cloudlog, "warning", logged.append)
  loaded: list[str] = []
  app = SimpleNamespace(_deferred_faces={"Inter-Medium.ttf": [65]}, _load_face=lambda weight, _: loaded.append(weight))
  font_loading.log_deferred_loads(app)
  app._load_face("Inter-Regular.ttf", [65])   # a face loaded at startup: no log
  assert loaded == ["Inter-Regular.ttf"] and logged == []
  app._load_face("Inter-Medium.ttf", [65])
  assert loaded[-1] == "Inter-Medium.ttf"
  assert len(logged) == 1 and logged[0].startswith("Tandem: deferred font Inter-Medium.ttf loaded by ")
  assert "test_font_loading.py" in logged[0]
