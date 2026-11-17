"""Power-user bundles: one switch each, and each switch sets a fixed group of StarPilot's display settings.

A bundle owns its settings while it is on. Turning it off sets the off values, which are the Essentials defaults.
StarPilot 7 keeps these settings in its Appearance owner, which changes them only while parked.

Tuner Mode isn't a bundle any more: StarPilot 7 has no tuning level, so it's Tandem's own preference (prefs.TUNER_MODE),
which shows Tandem's fine-tuning screens.
"""
from __future__ import annotations

from dataclasses import dataclass

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows

APPEARANCE = "appearance"


@dataclass(frozen=True)
class Item:
  """One setting a bundle sets: its name, StarPilot's row key, and its value with the bundle on and off."""
  name: str
  key: str
  on: str
  off: str


@dataclass(frozen=True)
class Bundle:
  """A named group of settings turned on and off together (e.g. Developer View). Its first item says whether it is on."""
  name: str
  description: str
  items: tuple[Item, ...]

  def is_on(self, rows: Rows) -> bool:
    first = self.items[0]
    return rows(APPEARANCE).value(first.key) == first.on

  def editable(self, rows: Rows) -> bool:
    return rows(APPEARANCE).available(self.items[0].key)

  def set(self, rows: Rows, on: bool) -> None:
    """Sets each item in order turning on and in reverse turning off, since a later item can need an earlier one on."""
    page = rows(APPEARANCE)
    for item in self.items if on else reversed(self.items):
      page.set(item.key, item.on if on else item.off)


DEVELOPER_VIEW = Bundle(
  N_("Developer View"), N_("Side panel with live system and controls data"),
  (Item(N_("Developer sidebar"), "DeveloperSidebar", "On", "Off"),))

LEAD_INSIGHTS = Bundle(
  N_("Lead Insights"), N_("Distance to the car ahead, and the pedals on screen"),
  (Item(N_("Lead indicator"), "HideLeadMarker", "On", "Off"),        # StarPilot shows Lead Info only with its indicator on
   Item(N_("Lead distance"), "LeadInfo", "Distance", "Off"),
   Item(N_("Gas and brake"), "ShowBrakeStatus", "On", "Off")))

BUNDLES = [DEVELOPER_VIEW, LEAD_INSIGHTS]
