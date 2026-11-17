"""Release's Device › General settings, backed by native owners and isolated Params files."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.settings.general_owner import General
from openpilot.starpilot.galaxy.localization_settings import LocalizationSettingsOwner
from openpilot.starpilot.ui.display_owner import DisplayOwner
from openpilot.starpilot.ui.display_preferences import BRIGHTNESS, MASTER, SCREEN_OFF, read_preferences


class FileParams:
  """Use real saved-source reads and writes without the host's native Params library."""

  def __init__(self, root: Path) -> None:
    self.directory = root / "d"
    self.directory.mkdir()
    self.fail = ""

  def get_param_path(self, key: str) -> str:
    """Return an isolated path for the key."""
    return str(self.directory / key)

  def put(self, key: str, value: str | int, *, block: bool = False) -> None:
    """Persist a stand-in Params value, or simulate a write failure."""
    if key == self.fail:
      raise RuntimeError("write failed")
    Path(self.get_param_path(key)).write_text(str(value))

  def put_bool(self, key: str, value: bool, *, block: bool = False) -> None:
    """Persist native bool bytes."""
    self.put(key, int(value), block=block)

  def get_bool(self, key: str) -> bool:
    """Read a boolean for the native localization owner."""
    path = Path(self.get_param_path(key))
    return path.exists() and path.read_bytes() == b"1"


class Rig:
  """General with the real StarPilot owners and a disposable Params directory."""

  def __init__(self, root: Path) -> None:
    self.params = FileParams(root)
    self.parked = True
    self.local = True
    self.language_reload = Mock()
    self.model = General(LocalizationSettingsOwner(self.params, lambda: self.local, lambda: self.parked),
                         DisplayOwner(self.params, lambda: self.parked and self.local, gpu_capable=False),
                         lambda: self.local, self.language_reload)
    self.model.refresh()


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
  """Return an isolated General model."""
  return Rig(tmp_path)


def test_general_brightness_and_standby(rig: Rig) -> None:
  """Apply release's preset levels and use native screen-off independently."""
  params, general = rig.params, rig.model
  assert general.brightness == 1
  general.set_standby(True)
  assert params.get_bool(SCREEN_OFF) and general.standby and not params.get_bool(MASTER)

  params.put("ScreenTimeout", 35)
  general.refresh()
  general.set_brightness(0)
  saved = read_preferences(params, large=True)
  assert (saved.parked_brightness, saved.driving_brightness, saved.parked_timeout) == (40, 30, 35)
  assert general.brightness == 0
  general.set_brightness(2)
  saved = read_preferences(params, large=True)
  assert (saved.parked_brightness, saved.driving_brightness) == (100, 100)
  assert general.brightness == 2

  params.put(BRIGHTNESS[1], 95)
  general.refresh()
  assert general.brightness == -1
  general.set_brightness(1)
  assert general.brightness == 1 and general.standby


@pytest.mark.parametrize("custom", [False, True])
def test_failed_brightness_pair_restores_effective_settings(rig: Rig, custom: bool) -> None:
  """A failed driving-brightness write rolls back the parked brightness and any new opt-in."""
  params, general = rig.params, rig.model
  params.put_bool(MASTER, custom)
  params.put(BRIGHTNESS[0], 80)
  params.put(BRIGHTNESS[1], 60)
  general.refresh()
  before = read_preferences(params, large=True)
  params.fail = BRIGHTNESS[1]
  general.set_brightness(0)
  assert read_preferences(params, large=True) == before
  assert Path(params.get_param_path(BRIGHTNESS[0])).read_bytes() == b"80"


def test_stale_brightness_keeps_concurrent_choice(rig: Rig) -> None:
  """Do not overwrite a setting changed by another client after the panel read it."""
  params, general = rig.params, rig.model
  params.put_bool(MASTER, True)
  general.refresh()
  params.put(BRIGHTNESS[1], 70)
  general.set_brightness(0)
  saved = read_preferences(params, large=True)
  assert (saved.parked_brightness, saved.driving_brightness) == (101, 70)


def test_language_shows_its_name_after_a_restart(rig: Rig) -> None:
  """Old prefixed codes still display their native name in the release language button."""
  params, general = rig.params, rig.model
  for code in ("de", "main_de"):
    params.put("LanguageSetting", code)
    general.refresh()
    assert general.language_name() == "Deutsch"
  assert "Tiếng Việt" in general.language().choices
  assert general.set_language(general.language(), "Español")
  assert general.language_name() == "Español"
  rig.language_reload.assert_called_once_with()


def test_language_sheet_requires_the_saved_source_and_parking(rig: Rig) -> None:
  """A change from the sheet cannot override a newer language or write after moving."""
  params, general = rig.params, rig.model
  opening_row = general.language()
  params.put("LanguageSetting", "de")
  assert not general.set_language(opening_row, "Español")
  assert general.language_name() == "Deutsch"
  rig.parked = False
  assert not general.set_language(general.language(), "Español")
  rig.language_reload.assert_not_called()
  general.set_brightness(0)
  general.set_standby(True)
  assert not params.get_bool(MASTER) and not params.get_bool(SCREEN_OFF)


def test_units_preserve_offsets_and_temperature_override(rig: Rig) -> None:
  """Changing Units keeps the physical SLC schedule and Temperature follows until overridden."""
  params, general = rig.params, rig.model
  params.put("SLCOffsetSchedule", '{"boundsMps":[1],"offsetsMps":[2]}')
  offsets = Path(params.get_param_path("SLCOffsetSchedule")).read_bytes()
  assert general.metric == 0 and general.temperature == 0
  general.set_metric(1)
  assert general.metric == 1 and general.temperature == 1 and params.get_bool("IsMetric")
  assert Path(params.get_param_path("SLCOffsetSchedule")).read_bytes() == offsets
  general.set_temperature(0)
  assert general.metric == 1 and general.temperature == 0
  rig.local = False
  general.set_temperature(1)
  general.set_metric(0)
  assert general.metric == 1 and general.temperature == 0


def test_release_rows_and_language_sheet(rig: Rig) -> None:
  """Keep release's five rows, in order, with its language sheet over the window."""
  from openpilot.selfdrive.ui.tandem.settings.general import GeneralPanel, open_language
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab

  window = SettingsWindow({Tab.DEVICE: lambda: GeneralPanel(rig.model, window)}, initial=Tab.DEVICE)
  panel = window.top
  assert isinstance(panel, GeneralPanel)
  assert [row._title for row in panel.items] == ["Units", "Temperature", "Language", "Screen Brightness", "Standby"]
  assert panel.items[-1]._subtitle == "Screen sleeps while driving, wakes for alerts"
  open_language(rig.model, window)
  sheet = window._overlay
  assert sheet._title == "Language"
  sheet._body._on_change(1)
  assert rig.model.language_name() == "Deutsch" and window._overlay is None
