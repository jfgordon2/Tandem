"""Names of the existing settings/action favorites used by car buttons and remotes."""
from openpilot.starpilot.common.favorite_slots import load_favorite_slots
from openpilot.selfdrive.ui.tandem.i18n import N_, t_


def favorite_action_names(params) -> list[str]:
  names = []
  for i, slot in enumerate(load_favorite_slots(params)):
    name = t_("Favorite {}", i + 1)
    if not slot.get("enabled") or not slot.get("key"):
      name += N_(" · Not set")
    elif slot.get("label"):
      name += f" · {slot['label']}"
    names.append(name)
  return names
