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
