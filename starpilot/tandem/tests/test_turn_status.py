"""The planner sends bounded, fresh turn status without waiting for the UI."""
import pytest

from openpilot.starpilot.tandem import turn_status as status

LEFT = (True, "turn", "sharpLeft")
RIGHT = (True, "roundabout", "right")


class Socket:
  def __init__(self):
    self.packet = None
    self.sent = 0
    self.failed = False

  def send(self, packet):
    if self.failed:
      raise OSError("publisher unavailable")
    self.sent += 1
    self.packet = packet

  def receive(self, *, non_blocking):
    assert non_blocking
    if self.failed:
      raise OSError("subscriber unavailable")
    packet, self.packet = self.packet, None
    return packet


def test_idle_is_silent_and_turn_changes_and_clears_are_immediate():
  socket = Socket()
  writer = status.Publisher(lambda: socket)
  reader = status.Subscriber(lambda: socket)
  for frame in range(1200):
    writer.update(status.EMPTY_TURN, 100 + frame * 0.05)
  assert socket.sent == 1 and reader.read(160) == status.EMPTY_TURN

  writer.update(LEFT, 160)
  assert socket.sent == 2 and reader.read(160) == LEFT
  writer.update(LEFT, 160.24)
  assert socket.sent == 2
  writer.update(LEFT, 160.25)
  assert socket.sent == 3 and reader.read(160.25) == LEFT
  writer.update(RIGHT, 160.26)
  assert socket.sent == 4 and reader.read(160.26) == RIGHT
  writer.update(status.EMPTY_TURN, 160.27)
  writer.update(status.EMPTY_TURN, 160.28)
  assert socket.sent == 5 and reader.read(160.28) == status.EMPTY_TURN


def test_reader_keeps_latest_fresh_turn_without_blocking():
  socket = Socket()
  writer = status.Publisher(lambda: socket)
  reader = status.Subscriber(lambda: socket)
  writer.update(LEFT, 100)
  writer.update(RIGHT, 100.05)
  assert reader.read(100) == status.EMPTY_TURN  # publisher raced the UI's frame timestamp
  assert reader.read(100.1) == RIGHT
  assert reader.read(101.0) == RIGHT
  assert reader.read(101.06) == status.EMPTY_TURN


@pytest.mark.parametrize("packet", [b"truncated", status.RECORD.pack(100, 2, b"turn", b"left"),
                                    status.RECORD.pack(float("nan"), 1, b"turn", b"left"),
                                    status.RECORD.pack(100, 1, b"\xff", b"left")])
def test_malformed_packet_drops_previous_turn(packet):
  socket = Socket()
  writer = status.Publisher(lambda: socket)
  reader = status.Subscriber(lambda: socket)
  writer.update(LEFT, 100)
  assert reader.read(100) == LEFT
  socket.packet = packet
  assert reader.read(100.05) == status.EMPTY_TURN


def test_overlong_maneuver_clears_the_previous_turn_instead_of_truncating():
  socket = Socket()
  writer = status.Publisher(lambda: socket)
  reader = status.Subscriber(lambda: socket)
  writer.update(LEFT, 100)
  assert reader.read(100) == LEFT
  writer.update((True, "turn", "a" * (status.TEXT_BYTES + 1)), 100.05)
  assert reader.read(100.05) == status.EMPTY_TURN


def test_unavailable_publisher_retries_at_most_once_per_second():
  socket, opens = Socket(), []

  def open_socket():
    opens.append(1)
    if len(opens) == 1:
      raise ImportError("native msgq unavailable")
    return socket

  writer = status.Publisher(open_socket)
  writer.update(LEFT, 100)
  writer.update(LEFT, 100.95)
  assert len(opens) == 1 and socket.sent == 0
  writer.update(LEFT, 101)
  assert len(opens) == 2 and socket.sent == 1
  socket.failed = True
  writer.update(RIGHT, 101.05)
  socket.failed = False
  writer.update(RIGHT, 102.05)
  assert len(opens) == 3 and socket.sent == 2


def test_read_failure_clears_turn_and_reopens_without_blocking():
  socket, opens = Socket(), []

  def open_socket():
    opens.append(1)
    return socket

  writer = status.Publisher(lambda: socket)
  reader = status.Subscriber(open_socket)
  writer.update(LEFT, 100)
  assert reader.read(100) == LEFT
  socket.failed = True
  assert reader.read(100.1) == status.EMPTY_TURN
  socket.failed = False
  writer.update(RIGHT, 101.0)
  assert reader.read(101.0) == status.EMPTY_TURN and len(opens) == 1
  assert reader.read(101.1) == RIGHT and len(opens) == 2
