"""Real cereal schema checks. Run on the device/full build, without a publisher socket."""
import json
from pathlib import Path
from types import SimpleNamespace

from openpilot.starpilot.navigation.navigationd import Navigationd
from openpilot.starpilot.navigation.route_engine import NavigationRoute
from openpilot.starpilot.tandem.routing.normalize import normalize


def test_pinned_native_lanes_and_instructions_serialize_with_existing_publisher():
  raw = json.loads((Path(__file__).parent / "fixtures/valhalla-iowa-3.9.1.json").read_text())
  route = NavigationRoute.from_mapbox_route(normalize(raw))
  messages = []
  daemon = Navigationd.__new__(Navigationd)
  daemon.pm = SimpleNamespace(send=lambda name, message: messages.append(message))
  with_lanes = 0
  for coordinate in route.geometry:
    daemon._last_position = coordinate
    progress = route.get_progress(coordinate)
    payload = route.build_instruction_payload(progress)
    daemon._publish_nav_instruction(route, progress, True, payload)
    message = messages[-1]
    encoded = message.to_bytes()
    assert encoded and message.valid
    assert message.navInstruction.distanceRemaining >= 0
    with_lanes += bool(message.navInstruction.lanes)
  assert len(messages) == len(route.geometry) and with_lanes > 0
