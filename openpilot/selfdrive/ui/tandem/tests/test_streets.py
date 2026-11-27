import pytest

from openpilot.selfdrive.ui.tandem.onroad.streets import short_street, short_streets_in


@pytest.mark.parametrize("name, short", [
  ("North Main Street", "N Main St"),
  ("Southwest Broadway", "SW Broadway"),
  ("Martin Luther King Junior Boulevard Northwest", "Martin Luther King Junior Blvd NW"),
  ("Park Avenue South", "Park Ave S"),
  ("East 14th Street", "E 14th St"),
  ("Pacific Coast Highway", "Pacific Coast Hwy"),
  ("North Avenue", "North Ave"),                 # the direction is the name
  ("East Street", "East St"),
  ("Northwest Blvd", "Northwest Blvd"),           # already short: Northwest is still the name
  ("North St.", "North St."),
  ("West Ave South", "West Ave S"),
  ("North Way", "North Way"),
  ("Avenue of the Americas", "Avenue of the Americas"),   # the type isn't last
  ("Broadway", "Broadway"),
  ("Interstate 5", "Interstate 5"),
  ("", ""),
])
def test_directions_and_types_are_shortened(name, short):
  assert short_street(name) == short


@pytest.mark.parametrize("text, short", [
  ("North Main Street", "N Main St"),
  ("Turn right onto North Main Street", "Turn right onto N Main St"),
  ("Keep left toward Pacific Coast Highway / West 5th Avenue", "Keep left toward Pacific Coast Hwy / W 5th Ave"),
  ("Exit 12 to East Street, Southwest Broadway", "Exit 12 to East St, SW Broadway"),
  ("Continue on I-80 West", "Continue on I-80 West"),
  ("Arrive at your destination", "Arrive at your destination"),
])
def test_streets_in_route_instructions(text, short):
  assert short_streets_in(text) == short


def test_the_street_stays_through_mapds_invalid_stretches() -> None:
  """mapd's shadow output is invalid and nameless for seconds between valid moments; the street stayed only while it was
  named, so it was on for a few seconds and off for a few."""
  from openpilot.selfdrive.ui.tandem.onroad.streets import StreetName
  street = StreetName()
  assert street.update("Grant St", 0.0) == "Grant St"
  assert all(street.update("", t / 20) == "Grant St" for t in range(1, 200))   # 10 s of invalid, nameless messages
  assert street.update("Grant St", 10.0) == "Grant St"
  assert street.update(None, 24.9) == "Grant St"
  assert street.update("", 25.1) == ""                                          # 15 s without a name: none shown


def test_a_new_street_must_hold_before_it_shows() -> None:
  from openpilot.selfdrive.ui.tandem.onroad.streets import StreetName
  street = StreetName()
  street.update("Main St", 0.0)
  assert street.update("Oak Ave", 1.0) == "Main St"    # a junction's other road, briefly
  assert street.update("Main St", 1.2) == "Main St"
  assert street.update("Oak Ave", 2.0) == "Main St"
  assert street.update("", 2.5) == "Main St"
  assert street.update("Oak Ave", 3.6) == "Oak Ave"    # turned: named for 1.6 s
