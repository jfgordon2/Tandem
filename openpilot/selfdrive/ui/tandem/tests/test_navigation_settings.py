"""Speed & Steering › Navigation (settings/navigation.py) over StarPilot 7's real navigation owner in a temporary folder."""
from __future__ import annotations

from pathlib import Path

from openpilot.starpilot.navigation.owner import NavigationOwner
from openpilot.selfdrive.ui.tandem.settings.navigation import NavigationSettings
from openpilot.selfdrive.ui.tandem.tests.test_places import OFFICE, PARK, make_owner, places


def settings(tmp_path: Path) -> tuple[NavigationSettings, NavigationOwner]:
  owner = make_owner(tmp_path)
  return NavigationSettings(places(owner)), owner


def test_the_switch_avoidances_and_position_write_starpilots_settings(tmp_path: Path) -> None:
  model, owner = settings(tmp_path)
  assert not model.enabled and model.summary() == "Off"
  model.set_enabled(True)
  model.set_avoid("avoidFerries", True)
  model.set_position(2)
  snap = owner.snapshot()
  assert snap["enabled"] and snap["avoidFerries"] and not snap["avoidTolls"] and snap["gpsSource"] == "phone"
  assert model.summary() == "On" and model.avoids("avoidFerries") and model.position() == 2


def test_google_directions_need_its_key(tmp_path: Path) -> None:
  model, owner = settings(tmp_path)
  model.set_directions(1)
  assert owner.snapshot()["routeProvider"] == "mapbox" and model.directions() == 0
  assert model.directions_line() == "Mapbox, with lane arrows. Google needs its key."
  owner.configure({"googleKey": "A" * 39}, owner.snapshot()["revision"], True)
  model.set_directions(1)
  assert owner.snapshot()["routeProvider"] == "google" and model.directions() == 1
  assert model.directions_line() == "Follows live traffic. No lane arrows."


def test_keys_and_saved_places_lines(tmp_path: Path) -> None:
  model, owner = settings(tmp_path)
  assert model.keys() == ("Not added · needed for place search and routes", False)
  assert model.saved_line() == "Home, Work and favorites from Where to?"
  owner.configure({"token": "pk.test"}, owner.snapshot()["revision"], True)
  owner.favorite(OFFICE, owner.snapshot()["revision"], True, label="work")
  owner.favorite(PARK, owner.snapshot()["revision"], True)
  assert model.keys() == ("Mapbox added · Google optional", True)
  assert model.saved_line() == "Work · 1 favorite"
