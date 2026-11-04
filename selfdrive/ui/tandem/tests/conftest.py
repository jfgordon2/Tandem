import pytest


@pytest.fixture(autouse=True)
def tandem_prefs(tmp_path, monkeypatch):
  """Tandem's marker-file preferences (prefs.py) go to a fresh folder per test, never beside a real params folder."""
  folder = tmp_path / "prefs"
  folder.mkdir()
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(folder))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  return folder
