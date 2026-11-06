"""Filesystem tests must never remove the device's installed road maps."""
import pytest


@pytest.fixture(autouse=True)
def private_road_maps(tmp_path, monkeypatch):
  monkeypatch.setenv("TANDEM_ROAD_MAPS_DIR", str(tmp_path / "road-maps"))
