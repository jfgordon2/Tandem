"""Speed & Steering › Navigation (design/stage5-drivingnav.html), on StarPilot 7's navigation owner.

Each row writes StarPilot's own navigation settings through places.StarPilotPlaces: its on/off switch, which service
gives directions, what routes avoid, and where the car's position comes from. Saved places open Where to?. Keys are
pasted in Galaxy (map_keys.py), so this page only says which are there. Release's End Route When Parked has no
StarPilot 7 setting; release's offline routing rows come back with Valhalla (PORTING.md, phase B).
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.blocks import Icon
from openpilot.selfdrive.ui.tandem.controls import Button, Segmented, Switch, ToggleButton, ToggleGroup
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.map_keys import status
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow

DIRECTIONS = [("mapbox", N_("Mapbox"), N_("Turn-by-turn with lane arrows")),
              ("google", N_("Google"), N_("Follows live traffic. No lane arrows."))]
AVOID = [("avoidTolls", N_("Tolls")), ("avoidHighways", N_("Highways")), ("avoidFerries", N_("Ferries"))]
POSITION = [("backup", N_("Phone backup"), N_("The phone fills in when the comma and car have no fix")),
            ("comma", N_("No phone"), N_("Only the comma's and car's GPS")),
            ("phone", N_("Phone first"), N_("The phone whenever it has a recent fix"))]


class NavigationSettings:
  """StarPilot's navigation settings as the page reads and writes them.

  Args:
    places: StarPilot's navigation, shared with Where to?.
  """

  def __init__(self, places: StarPilotPlaces):
    self._places = places

  def _get(self, key: str, default: object = None) -> object:
    return self._places.snapshot().get(key, default)

  @property
  def enabled(self) -> bool:
    return bool(self._get("enabled"))

  def set_enabled(self, on: bool) -> None:
    self._places.configure({"enabled": on})

  def summary(self) -> str:
    """The section's value in the side list."""
    return N_("On") if self.enabled else N_("Off")

  def saved_line(self) -> str:
    """e.g. "Home · Work · 3 favorites", or how to add some."""
    favorites = self._places.favorites()
    labels = [t_("Home")] if any(f["is_home"] for f in favorites) else []
    labels += [t_("Work")] if any(f["is_work"] for f in favorites) else []
    others = sum(1 for f in favorites if not f["is_home"] and not f["is_work"])
    if others:
      labels.append(tn_("{} favorite", "{} favorites", others))
    return " · ".join(labels) if labels else N_("Home, Work and favorites from Where to?")

  def google_ready(self) -> bool:
    return bool(self._get("hasGoogleKey"))

  def directions(self) -> int:
    """Google only while its key is there, as StarPilot routes."""
    return 1 if self._get("routeProvider") == "google" and self.google_ready() else 0

  def set_directions(self, index: int) -> None:
    if index == 0 or self.google_ready():
      self._places.configure({"routeProvider": DIRECTIONS[index][0]})

  def directions_line(self) -> str:
    if not self.google_ready():
      return N_("Mapbox, with lane arrows. Google needs its key.")
    return DIRECTIONS[self.directions()][2]

  def avoids(self, key: str) -> bool:
    return bool(self._get(key))

  def set_avoid(self, key: str, on: bool) -> None:
    self._places.configure({key: on})

  def position(self) -> int:
    source = self._get("gpsSource", "backup")
    return next((i for i, (value, _, _) in enumerate(POSITION) if value == source), 0)

  def set_position(self, index: int) -> None:
    self._places.configure({"gpsSource": POSITION[index][0]})

  def keys(self) -> tuple[str, bool]:
    """The Map Keys line, and whether search and routes can work."""
    return status(bool(self._get("hasKey")), self.google_ready())


def navigation_panel(model: NavigationSettings, open_destinations: Callable[[], None], open_key_help: Callable[[], None]) -> ListPanel:
  """Speed & Steering › Navigation: on or off, saved places, directions, avoidances, position and keys."""
  directions = Segmented([name for _, name, _ in DIRECTIONS], model.directions, model.set_directions)
  avoid = ToggleGroup([ToggleButton(name, partial(model.avoids, key), partial(model.set_avoid, key)) for key, name in AVOID])
  position = Segmented([name for _, name, _ in POSITION], model.position, model.set_position, font_size=T.font_px(15))
  h = T.px(57)   # the mock's 58, less what the shared panel header adds, so all six rows show
  return ListPanel([
    SettingRow(N_("Navigation"), N_("Turn guidance on the driving screen"), Switch(lambda: model.enabled, model.set_enabled), height=h),
    SettingRow(N_("Saved Places"), model.saved_line, on_click=open_destinations, leading=Icon("star"), height=h),
    SettingRow(N_("Directions"), model.directions_line, directions, height=h),
    SettingRow(N_("Avoid"), N_("When planning routes"), avoid, height=h),
    SettingRow(N_("Position"), lambda: POSITION[model.position()][2], position, height=h),
    SettingRow(N_("Map Keys"), lambda: model.keys()[0],
               Button(lambda: N_("How to change") if model.keys()[1] else N_("How to add"), open_key_help),
               subtitle_color=lambda: T.SUCCESS_TEXT if model.keys()[1] else T.WARNING, height=h),
  ], title=N_("Navigation"), subtitle=N_("While a route is active, the car slows for turns on it"))

