import pytest


@pytest.fixture(autouse=True)
def tandem_prefs(tmp_path, monkeypatch):
  """Tandem's marker-file preferences (prefs.py) go to a fresh folder per test, never beside a real params folder."""
  folder = tmp_path / "prefs"
  folder.mkdir()
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(folder))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_ROAD_MAPS_DIR", str(tmp_path / "road-maps"))
  return folder


@pytest.fixture
def turn_channel(monkeypatch):
  """Exercise the turn wire format through a private, latest-message test socket."""
  from openpilot.starpilot.tandem import navigation, turn_status

  class Socket:
    packet = None

    def send(self, packet):
      self.packet = packet

    def receive(self, *, non_blocking):
      assert non_blocking
      packet, self.packet = self.packet, None
      return packet

  socket = Socket()
  publisher = turn_status.Publisher(lambda: socket)
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  monkeypatch.setattr(navigation, "_turn_publisher", publisher)
  monkeypatch.setattr(navigation, "_turn_subscriber", turn_status.Subscriber(lambda: socket))
  return publisher
