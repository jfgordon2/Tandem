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


def test_the_street_stays_steady_between_mapds_messages() -> None:
  """It blinked off whenever mapd's next message was over 100 ms away; now it holds as StarPilot's map holds its name."""
  from openpilot.selfdrive.ui.tandem.onroad.streets import StreetName
  street = StreetName()
  assert street.update("Main St", 0.0) == "Main St"
  assert all(street.update(None, t / 10) == "Main St" for t in range(1, 29))   # quiet frames: still there
  assert street.update(None, 3.2) == ""                                       # nothing from mapd for over 3 s


def test_a_new_or_missing_street_must_hold_before_it_shows() -> None:
  from openpilot.selfdrive.ui.tandem.onroad.streets import StreetName
  street = StreetName()
  street.update("Main St", 0.0)
  assert street.update("", 0.5) == "Main St"           # one empty reading doesn't blank it
  assert street.update("Main St", 0.6) == "Main St"
  assert street.update("Oak Ave", 1.0) == "Main St"    # a junction's other road, briefly
  assert street.update("Main St", 1.2) == "Main St"
  assert street.update("Oak Ave", 2.0) == "Main St"
  assert street.update("Oak Ave", 3.6) == "Oak Ave"    # turned: it held 1.6 s
