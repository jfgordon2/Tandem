"""Latest turn status for the UI, sent on an owned raw msgq endpoint."""
from __future__ import annotations

from collections.abc import Callable
import math
from struct import Struct
from typing import Protocol

ENDPOINT = "tandemNavTurnV1"
QUEUE_BYTES = 4096
HEARTBEAT = 0.25
MAX_AGE = 1.0
RETRY_AFTER = 1.0
TEXT_BYTES = 32
RECORD = Struct(f"<dB{TEXT_BYTES}s{TEXT_BYTES}s")

Turn = tuple[bool, str, str]
EMPTY_TURN: Turn = (False, "", "")


class _PublisherSocket(Protocol):
  """The byte sender exposed by the native msgq socket."""

  def send(self, data: bytes, /) -> None: ...


class _SubscriberSocket(Protocol):
  """The byte receiver exposed by the native msgq socket."""

  def receive(self, *, non_blocking: bool) -> bytes | None: ...


def _open_publisher() -> _PublisherSocket:
  import msgq
  socket: _PublisherSocket = msgq.pub_sock(ENDPOINT, segment_size=QUEUE_BYTES)
  return socket


def _open_subscriber() -> _SubscriberSocket:
  import msgq
  socket: _SubscriberSocket = msgq.sub_sock(ENDPOINT, conflate=True, segment_size=QUEUE_BYTES)
  return socket


def _pack(now: float, turn: Turn) -> bytes:
  """Encodes a turn, clearing it when its text cannot fit the record."""
  active, maneuver, modifier = turn
  if active:
    try:
      maneuver_bytes, modifier_bytes = maneuver.encode("utf-8"), modifier.encode("utf-8")
      if len(maneuver_bytes) <= TEXT_BYTES and len(modifier_bytes) <= TEXT_BYTES:
        return RECORD.pack(now, 1, maneuver_bytes, modifier_bytes)
    except UnicodeEncodeError:
      pass
  return RECORD.pack(now, 0, b"", b"")


def _unpack(data: bytes) -> tuple[float, Turn] | None:
  """Decodes a record or returns None when the packet is malformed."""
  if len(data) != RECORD.size:
    return None
  stamp, active, maneuver, modifier = RECORD.unpack(data)
  if not math.isfinite(stamp) or stamp < 0 or active not in (0, 1):
    return None
  if not active:
    return stamp, EMPTY_TURN
  try:
    return stamp, (True, maneuver.rstrip(b"\0").decode("utf-8"), modifier.rstrip(b"\0").decode("utf-8"))
  except UnicodeDecodeError:
    return None


class Publisher:
  """Send changes immediately and refresh active turns for readers that join later."""

  def __init__(self, open_socket: Callable[[], _PublisherSocket] = _open_publisher) -> None:
    self._open_socket = open_socket
    self._socket: _PublisherSocket | None = None
    self._last_turn: Turn | None = None
    self._sent_at = 0.0
    self._retry_at = 0.0

  def update(self, turn: Turn, now: float) -> None:
    """Sends a changed or due turn with its monotonic timestamp."""
    if turn == self._last_turn and (not turn[0] or now - self._sent_at < HEARTBEAT):
      return
    if now < self._retry_at:
      return
    data = _pack(now, turn)
    try:
      if self._socket is None:
        self._socket = self._open_socket()
      self._socket.send(data)
    except Exception:
      # An optional status message must never interrupt the planner.
      self._socket = None
      self._last_turn = None
      self._retry_at = now + RETRY_AFTER
      return
    self._last_turn, self._sent_at = turn, now


class Subscriber:
  """Read the latest packet without waiting and retain it only while fresh."""

  def __init__(self, open_socket: Callable[[], _SubscriberSocket] = _open_subscriber) -> None:
    self._open_socket = open_socket
    self._socket: _SubscriberSocket | None = None
    self._latest: tuple[float, Turn] | None = None
    self._retry_at = 0.0

  def read(self, now: float) -> Turn:
    """Returns the latest turn that is fresh at the given monotonic time."""
    if now < self._retry_at:
      return EMPTY_TURN
    try:
      if self._socket is None:
        self._socket = self._open_socket()
      packet = self._socket.receive(non_blocking=True)
    except Exception:
      self._socket = self._latest = None
      self._retry_at = now + RETRY_AFTER
      return EMPTY_TURN
    if packet is not None:
      self._latest = _unpack(packet)
    if self._latest is not None:
      stamp, turn = self._latest
      # The sender can publish after the UI sampled its frame time. Keep that packet
      # for the next frame, but never use it before its timestamp.
      if 0 <= now - stamp <= MAX_AGE:
        return turn
    return EMPTY_TURN
