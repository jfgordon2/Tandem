"""The release Device › General panel and language picker."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.controls import Segmented, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.fonts import face_for
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow
from openpilot.selfdrive.ui.tandem.settings.general_owner import BRIGHTNESS, General
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow


def open_language(model: General, window: SettingsWindow) -> None:
  """Use release's language sheet with the current StarPilot language names."""
  row = model.language()
  if not row.available:
    return
  languages = list(row.choices)

  def pick(index: int) -> None:
    """Save the selected language using the source observed when opening the picker."""
    model.set_language(row, languages[index])
    window.dismiss()

  window.present(Sheet(N_("Language"), OptionList(languages, languages.index(row.value),
                                                 pick, weight=lambda name: face_for(name, T.FONT_SEMIBOLD)),
                       subtitle=N_("For menus and alerts"), on_dismiss=window.dismiss))


class GeneralPanel(ListPanel):
  """Release's five General rows with live state from the current owners."""

  def __init__(self, model: General, window: SettingsWindow) -> None:
    self._model = model
    model.poll()
    units = SettingRow(N_("Units"), N_("Speed and distance everywhere"),
                       Segmented(["mph", "km/h"], lambda: model.metric, model.set_metric))
    temperature = SettingRow(N_("Temperature"), N_("For the weather forecast"),
                             Segmented(["°F", "°C"], lambda: model.temperature, model.set_temperature))
    language = SettingRow(N_("Language"), None, ValueButton(model.language_name, lambda: open_language(model, window)))
    brightness = SettingRow(N_("Screen Brightness"), N_("Auto follows ambient light, day and night"),
                            Segmented([name for name, _, _ in BRIGHTNESS], lambda: model.brightness, model.set_brightness))
    standby = SettingRow(N_("Standby"), N_("Screen sleeps while driving, wakes for alerts"),
                         Switch(lambda: model.standby, model.set_standby))
    units.set_enabled(model.metric_available)
    temperature.set_enabled(model.temperature_available)
    language.set_enabled(lambda: model.language().available)
    brightness.set_enabled(model.brightness_available)
    standby.set_enabled(model.standby_available)
    super().__init__([units, temperature, language, brightness, standby], title=N_("General"))

  def show_event(self) -> None:
    """Load current choices when the section opens."""
    self._model.refresh()
    super().show_event()

  def _update_state(self) -> None:
    """Refresh infrequently while shown without rebuilding the release panel."""
    self._model.poll()
    super()._update_state()
