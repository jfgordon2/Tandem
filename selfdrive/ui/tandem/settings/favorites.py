"""Names of the existing settings/action favorites used by car buttons and remotes."""
from __future__ import annotations

from typing import TYPE_CHECKING

from openpilot.starpilot.common.favorite_slots import load_favorite_slots
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

if TYPE_CHECKING:
  from openpilot.common.params import Params


def favorite_action_names(params: Params) -> list[str]:
  """The names of StarPilot's favorite slots that have an action, as car buttons and remotes list them."""
  names = []
  for i, slot in enumerate(load_favorite_slots(params)):
    name = t_("Favorite {}", i + 1)
    if not slot.get("enabled") or not slot.get("key"):
      name += N_(" · Not set")
    elif slot.get("label"):
      name += f" · {slot['label']}"
    names.append(name)
  return names
