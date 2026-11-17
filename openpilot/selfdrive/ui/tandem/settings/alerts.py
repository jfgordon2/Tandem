"""Alerts: one volume preset for every sound, levels per group, and the optional chimes.

StarPilot 7's Sounds owner keeps the levels and chimes, changed only while parked; each level is a number or Auto.
Samples play through StarPilot's alert preview, which plays them only while parked too.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from functools import partial
from typing import TYPE_CHECKING
from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Card, Columns, Label, Stack, ValueLine
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Slider, Switch
from openpilot.selfdrive.ui.tandem.layout import FILL, column, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows
from openpilot.selfdrive.ui.tandem.prefs import WEATHER_CHIME
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

AUTO = 101          # StarPilot's "Auto": the level follows cabin noise
SAFETY_FLOOR = 25   # StarPilot never plays take-control warnings below this


@dataclass(frozen=True)
class VolumeGroup:
  """Sounds that share one volume (e.g. engage and disengage chimes), with its quiet, standard and loud levels."""
  name: str
  subtitle: str
  keys: tuple[str, ...]
  levels: tuple[int, int, int]   # Quiet (25% for every group, the safety floor), Normal (safety warnings louder), Loud
  safety: bool = False


GROUPS = [
  VolumeGroup(N_("Engage and disengage chimes"), N_("When openpilot turns on or off"), ("EngageVolume", "DisengageVolume"), (25, 35, 85)),
  VolumeGroup(N_("Prompts and reminders"), N_("Gentle nudges, like when openpilot can't turn on"), ("PromptVolume", "RefuseVolume"),
              (25, 45, 90)),
  VolumeGroup(N_("Driver attention"), N_("The chime that asks you to look at the road"), ("PromptDistractedVolume", "WarningSoftVolume"),
              (25, 60, 100), safety=True),
  VolumeGroup(N_("Take control warnings"), N_("When you need to steer or brake now"), ("WarningImmediateVolume",), (25, 80, 100), safety=True),
]
PRESETS = [N_("Auto"), N_("Quiet"), N_("Normal"), N_("Loud")]
CUSTOM = -1
CHIMES = [
  (N_("Green Light"), N_("When the light turns green and you are stopped"), "GreenLightAlert"),
  (N_("Lead Departure"), N_("When the car ahead pulls away"), "LeadDepartingAlert"),
  (N_("Loud Blind Spot"), N_("Signalling into an occupied lane, even when paused"), "LoudBlindspotAlert"),
  (N_("Weather heads-up"), N_("Once, when rain, snow or storms are coming"), "WeatherChime"),
]
# Chimes that are Tandem's own, kept as marker files (prefs.py) rather than params the device's prebuilt registry lacks.
OWN_CHIMES = {"WeatherChime": WEATHER_CHIME}
# StarPilot keeps the blind spot chime in two settings: while steering, and while steering is off or paused. Ours is both.
LINKED_CHIMES = {"LoudBlindspotAlert": ("LoudBlindspotAlert", "LoudBlindspotAlertWhenDisengaged")}
SOUNDS = "sounds"


class Alerts:
  """Alerts & Sounds: the volume preset, each group's level, and which chimes play, on StarPilot's Sounds owner."""

  def __init__(self, rows: Rows, play: Callable[[str], None] | None = None):
    self._rows = rows
    self._play = play

  def editable(self) -> bool:
    """StarPilot changes sounds only while parked."""
    return self._rows(SOUNDS).available(GROUPS[0].keys[0])

  def level(self, group: VolumeGroup) -> int:
    value = self._rows(SOUNDS).value(group.keys[0], "Auto")
    try:
      return AUTO if value == "Auto" else int(float(value))
    except ValueError:
      return AUTO

  def _write(self, levels: dict[str, int]) -> None:
    rows = self._rows(SOUNDS)
    for key, level in levels.items():
      rows.set(key, "Auto" if level == AUTO else str(level))

  @property
  def preset(self) -> int:
    """Index into PRESETS, or CUSTOM when the levels match none of them."""
    levels = [self.level(g) for g in GROUPS]
    if all(level == AUTO for level in levels):
      return 0
    for i in range(3):
      if levels == [g.levels[i] for g in GROUPS]:
        return i + 1
    return CUSTOM

  def set_preset(self, index: int) -> None:
    levels: dict[str, int] = {}
    for group in GROUPS:
      levels |= dict.fromkeys(group.keys, AUTO if index == 0 else group.levels[index - 1])
    self._write(levels)

  def set_level(self, group: VolumeGroup, level: float) -> None:
    """Changing one group makes the preset Custom. Groups still on Auto take their Normal level, as a preset would."""
    levels = {k: g.levels[1] for g in GROUPS if g != group and self.level(g) == AUTO for k in g.keys}
    level = max(int(level), SAFETY_FLOOR) if group.safety else int(level)
    self._write(levels | dict.fromkeys(group.keys, level))

  def level_label(self, group: VolumeGroup) -> str:
    level = self.level(group)
    return N_("Auto") if level == AUTO else f"{level}%"

  def play(self, group: VolumeGroup) -> None:
    if self._play is not None:
      self._play(group.keys[0])

  def summary(self) -> str:
    return N_("Custom volume") if self.preset == CUSTOM else t_("{} volume", PRESETS[self.preset])

  def chimes_summary(self) -> str:
    on = [name for name, _, key in CHIMES if self.chime(key)]
    return ", ".join(on).capitalize() if on else N_("No extra chimes")

  def chime(self, key: str) -> bool:
    return OWN_CHIMES[key].get() if key in OWN_CHIMES else self._rows(SOUNDS).on(key)

  def chime_editable(self, key: str) -> bool:
    return key in OWN_CHIMES or self._rows(SOUNDS).available(key)

  def set_chime(self, key: str, on: bool) -> None:
    if key in OWN_CHIMES:
      OWN_CHIMES[key].set(on)
      return
    rows = self._rows(SOUNDS)
    for linked in LINKED_CHIMES.get(key, (key,)):
      rows.set_on(linked, on)


class VolumeEditor(Component):
  """Big value and Play sample, then the slider with the presets marked and the safety floor hatched."""
  grow_touch_target = False

  def __init__(self, model: Alerts, group: VolumeGroup):
    super().__init__()
    self._model = model
    self._group = group
    self._play = self._child(Button(N_("Play sample"), lambda: model.play(group), height=T.px(64), font_size=T.font_px(17),
                                    radius=T.px(18), weight=T.FONT_BOLD, padding=T.px(22),
                                    glyph=lambda r, c, s: draw.icon(r, "play_filled", T.ACCENT_TEXT, T.px(22))))
    self._slider = self._child(Slider(lambda: self._value(), lambda v: model.set_level(group, v), 0, 100, step=5,
                                      floor=SAFETY_FLOOR if group.safety else None, height=T.px(64),
                                      floor_label=t_("Minimum {}% for safety alerts", SAFETY_FLOOR) if group.safety else None,
                                      marks=[(group.levels[0], N_("Quiet")), (group.levels[1], N_("Normal")), (group.levels[2], N_("Loud"))]))
    self._reset = self._child(Button(N_("Reset to Normal"), lambda: model.set_level(group, group.levels[1]), ButtonStyle.GHOST,
                                       weight=T.FONT_BOLD))

  def _value(self) -> float:
    level = self._model.level(self._group)
    return self._group.levels[1] if level == AUTO else level

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(92) + self._slider.preferred_height(max_width) + T.px(60) + T.px(32)

  def _render(self, rect: rl.Rectangle) -> None:
    """The value with Play sample and a note beside it, the slider, then a note and Reset to Normal on one row."""
    top, slider, notes = column(rect, [T.px(92), self._slider.preferred_height(rect.width), T.px(48)], T.px(16))
    value, play, note = row(top, [T.px(200), self._play.preferred_size(rect.width)[0], FILL], T.px(28))
    level = self._model.level(self._group)
    number, unit = (N_("Auto"), "") if level == AUTO else (f"{level}", "%")
    w = draw.text(value, number, T.font_px(72), T.TEXT, T.FONT_EXTRABOLD)
    if unit:
      big, small = draw.line_height(T.font_px(72)), draw.line_height(T.font_px(26))
      unit_rect = rl.Rectangle(value.x + w + T.px(6), value.y + (value.height + big) / 2 - small - T.px(8), T.px(40), small)
      draw.text(unit_rect, unit, T.font_px(26), T.TEXT_SECONDARY, T.FONT_BOLD)
    self._play.render(rl.Rectangle(play.x, play.y + (play.height - T.px(64)) / 2, play.width, T.px(64)))
    draw.text(note, N_("Plays through your car speakers if they're connected."), T.font_px(15), T.TEXT_TERTIARY)
    self._slider.render(slider)
    reset_w, _ = self._reset.preferred_size(rect.width)
    text, reset = row(notes, [FILL, reset_w], T.px(10))
    draw.text(text, N_("Changing a level sets the Alert Volume preset to Custom."), T.SIZE_SUBTITLE, T.TEXT_MUTED)
    self._reset.render(rl.Rectangle(reset.x, reset.y + (reset.height - T.px(44)) / 2, reset.width, T.px(44)))


def alerts_page(model: Alerts, window: SettingsWindow) -> Widget:
  """Volume on the left (presets, then each group's level), chimes on the right."""
  def editor(group: VolumeGroup) -> Callable[[], None]:
    return lambda: window.present(Sheet(group.name, VolumeEditor(model, group), subtitle=group.subtitle,
                                        actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  def note() -> str:
    if not model.editable():
      return N_("Park to change alert volumes.")
    if model.preset == 0:
      return N_("Auto follows cabin noise. Tap a level to set it yourself.")
    return N_("Custom levels. Pick a preset to reset them.") if model.preset == CUSTOM else N_("Tap a level to fine-tune it.")

  volume_rows = [ValueLine(g.name, partial(model.level_label, g), editor(g), T.font_px(17), height=T.px(48)) for g in GROUPS]
  volume = Card([
    Label(N_("Volume"), T.font_px(20)),
    presets := Segmented(PRESETS, lambda: model.preset, model.set_preset, height=T.px(64), font_size=T.font_px(18), equal=True),
    # Each group is a finger-sized tile that opens its level editor.
    Stack(volume_rows, gap=T.px(6)),
    Label(note, T.SIZE_SUBTITLE, T.TEXT_MUTED, T.FONT),
  ], gap=T.px(12))
  chime_rows = [SettingRow(title, subtitle, Switch(partial(model.chime, key), partial(model.set_chime, key))) for title, subtitle, key in CHIMES]
  for chime_row, (_, _, key) in zip(chime_rows, CHIMES, strict=True):
    chime_row.set_enabled(partial(model.chime_editable, key))
  presets.set_enabled(model.editable)
  for line in volume_rows:
    line.set_enabled(model.editable)
  chimes = ListPanel(chime_rows, title=N_("Chimes"), title_size=T.font_px(20), header_divider=False)
  return TitledPage(N_("Alerts"), N_("One volume for everything. Safety warnings never go below 25%."), Columns([volume, chimes]))


def sound_player(parked: Callable[[], bool]) -> Callable[[str], None]:
  """Plays a sample through StarPilot's alert preview, off the drawing thread; it plays only while parked, one at a time.

  Args:
    parked: Whether StarPilot confirms the car is parked.
  """
  from openpilot.starpilot.audio.preview import AlertPreview, AlertPreviewError
  preview = AlertPreview(parked=parked)

  def play(key: str) -> None:
    def run() -> None:
      try:
        preview.play({"key": key})
      except AlertPreviewError:
        pass   # not parked, or a sample is already playing
    threading.Thread(target=run, name="tandem-alert-sample", daemon=True).start()
  return play
