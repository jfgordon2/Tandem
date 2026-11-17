"""A test of the connection the device is using (Connections › Network Test): download, upload and ping.

It times transfers to Cloudflare's speed test (speed.cloudflare.com, which needs no account or key) on a thread of its own,
and only while a test runs; drawing reads a small immutable snapshot. Each direction moves rounds of growing size until one
takes long enough to trust, so a slow connection moves little data and a fast one is still measured at full speed. The
caller sets how much data a test may use. Nothing is saved: the last result lasts until the UI restarts.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
import http.client
import socket
import ssl
import threading
import time
from typing import Any, Protocol

HOST = "speed.cloudflare.com"
HEADERS = {"User-Agent": "Tandem"}
TIMEOUT = 8.0               # a connection that stalls this long fails the test
# Cloudflare refuses downloads of some sizes (11 to 20 MB and from 100 MB, when this was written), so a download asks only
# for the sizes Cloudflare's own test uses, as many times as the round needs. Uploads of any size are accepted.
DOWNLOAD_SIZES = (25_000_000, 10_000_000, 1_000_000, 100_000)
UPLOAD_MAX = 25_000_000     # a bigger upload round is split
DOWNLOAD_CHUNK = 64 * 1024
UPLOAD_CHUNK = 16 * 1024    # small enough to send within TIMEOUT on a very slow connection
FIRST_DOWNLOAD = 200_000
FIRST_UPLOAD = 100_000
ROUND_SECONDS = 3.0         # each round is sized to take about this long at the speed just measured
ENOUGH_SECONDS = 1.5        # a round that took this long is the answer
PHASE_SECONDS = 10.0        # no round starts after this long in one direction, and a download is cut here
UPLOAD_LIMIT = 30.0         # an upload round still going after this long is given up
LIVE_AFTER = 0.3            # a download's running speed shows once its round has run this long
PINGS = 5


@dataclass(frozen=True)
class Budget:
  """The most data one test may use, in bytes each way."""
  download: int
  upload: int

  @property
  def total(self) -> int:
    return self.download + self.upload


UNMETERED = Budget(200 * 2**20, 100 * 2**20)
METERED = Budget(20 * 2**20, 10 * 2**20)     # cellular, a phone's hotspot, or a connection that isn't known


@dataclass(frozen=True)
class Route:
  """The active NetworkManager connection and its data interface."""
  connection: str
  interface: str
  unmetered: bool


def _bind_interface(sock: socket.socket, interface: str) -> None:
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\0")


def current_route() -> Route | None:
  """Read the active default connection, when it can be pinned to an interface."""
  if not hasattr(socket, "SO_BINDTODEVICE"):
    return None

  from openpilot.starpilot.tandem.cellular import Reader
  from openpilot.system.ui.lib.networkmanager import NM, NM_ACTIVE_CONNECTION_IFACE, NM_DEVICE_IFACE, NM_PATH, NMDeviceState

  try:
    with closing(Reader()) as reader:
      primary = reader.props(NM, NM_PATH, NM).get("PrimaryConnection", "/")
      if primary == "/":
        return None
      active = reader.props(NM, primary, NM_ACTIVE_CONNECTION_IFACE)
      devices = active.get("Devices", ())
      if len(devices) != 1 or not (active.get("Default") or active.get("Default6")):
        return None
      device = reader.props(NM, devices[0], NM_DEVICE_IFACE)
      interface = device.get("IpInterface")
      if not interface or device.get("ActiveConnection") != primary or device.get("State") != NMDeviceState.ACTIVATED:
        return None
      # Older kernels can require privileges for this socket option. Check it before giving the test a large budget.
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        _bind_interface(probe, interface)
      unmetered = active.get("Type") in ("802-11-wireless", "802-3-ethernet") and device.get("Metered") in (2, 4)  # NO or GUESS_NO
      return Route(primary, interface, unmetered)
  except Exception:
    return None  # An unavailable bus or an activation racing this read cannot authorize the larger budget.


class Phase(Enum):
  """Where a test is."""
  IDLE = "idle"
  DOWNLOAD = "download"
  UPLOAD = "upload"
  PING = "ping"
  DONE = "done"
  STOPPED = "stopped"
  FAILED = "failed"


class Problem(Enum):
  """Why a test failed."""
  UNREACHABLE = "unreachable"   # nothing was moved: no connection, or the speed test didn't answer
  DROPPED = "dropped"           # it started, then the connection failed or stalled
  REFUSED = "refused"           # the speed test turned a request down


@dataclass(frozen=True)
class Result:
  """A test so far, or the last one: speeds in bits per second, ping in seconds, and the bytes it has moved."""
  phase: Phase = Phase.IDLE
  download: float | None = None
  upload: float | None = None
  ping: float | None = None
  used: int = 0
  budget: Budget | None = None
  finished: float | None = None   # the time of day it ended, as a timestamp
  problem: Problem | None = None

  @property
  def running(self) -> bool:
    return self.phase in (Phase.DOWNLOAD, Phase.UPLOAD, Phase.PING)


class Stopped(Exception):
  """The test was stopped, or another has started: this one writes nothing more."""


class Refused(ConnectionError):
  """The speed test answered a request with something other than 200."""


@dataclass(frozen=True)
class Sample:
  """What one transfer measured: the bytes its speed is over, the seconds they took, and whether it ran to its end."""
  size: int
  seconds: float
  whole: bool = True


Moved = Callable[[int, float], None]   # the bytes that just moved, and the transfer's seconds so far
Check = Callable[[], None]


class Link(Protocol):
  """The transfers a test times. moved is called as bytes move, and raises Stopped to end the test."""

  def download(self, size: int, until: float, moved: Moved) -> Sample:
    """Receives about size bytes, stopping early (not whole) once the clock passes until."""

  def upload(self, size: int, until: float, moved: Moved) -> Sample:
    """Sends size bytes and waits until the far end has them. Measures nothing when the clock passes until first."""

  def ping(self) -> float:
    """The seconds one round trip to the far end takes."""

  def close(self) -> None:
    """Ends the connection."""


def download_requests(size: int) -> tuple[int, int]:
  """The request size Cloudflare accepts, and how many of them, that come nearest size without passing it."""
  step = next((s for s in DOWNLOAD_SIZES if s <= size), DOWNLOAD_SIZES[-1])
  return step, max(1, size // step)


class Cloudflare:
  """Transfers to Cloudflare's speed test over one HTTPS connection, kept open between requests."""

  def __init__(self, clock: Callable[[], float] = time.monotonic, *, route: Route | None = None, check: Check = lambda: None,
               read_route: Callable[[], Route | None] = current_route) -> None:
    self._clock = clock
    self._route, self._check, self._read_route = route, check, read_route
    self._http = http.client.HTTPSConnection(HOST, timeout=TIMEOUT, context=ssl.create_default_context())
    # Replace HTTPConnection's TCP dialer so HTTPS still handles TLS and hostname verification.
    self._http._create_connection = self._dial  # type: ignore[attr-defined]
    self._buffer = bytearray(DOWNLOAD_CHUNK)
    self._zeros = bytes(UPLOAD_CHUNK)
    self._peer: tuple[socket.AddressFamily, Any] | None = None

  def _before_request(self) -> None:
    self._check()
    if self._route is not None and self._read_route() != self._route:
      raise ConnectionError("The connection changed during the test")
    self._check()

  def _configure_socket(self, sock: socket.socket, timeout: float) -> None:
    sock.settimeout(timeout)
    if self._route is not None:
      _bind_interface(sock, self._route.interface)

  def _dial(self, address: tuple[str, int], timeout: float, source_address: tuple[str, int] | None = None) -> socket.socket:
    self._check()
    error: OSError = ConnectionError("No address for the speed test")
    for family, kind, protocol, _, peer in socket.getaddrinfo(*address, type=socket.SOCK_STREAM):
      self._check()
      sock = socket.socket(family, kind, protocol)
      try:
        self._configure_socket(sock, timeout)
        if source_address is not None:
          sock.bind(source_address)
        self._check()
        sock.connect(peer)
        return sock
      except OSError as exc:
        error = exc
      except BaseException:
        sock.close()
        raise
      sock.close()
    raise error

  def _answer(self) -> http.client.HTTPResponse:
    response = self._http.getresponse()
    if response.status != 200:
      self._http.close()
      raise Refused(f"{HOST} answered {response.status}")
    return response

  def _open(self) -> None:
    """Connects before a transfer is timed, so the timing leaves out the handshake."""
    if self._http.sock is None:
      self._http.connect()
    if self._peer is None:
      self._peer = (self._http.sock.family, self._http.sock.getpeername())

  def download(self, size: int, until: float, moved: Moved) -> Sample:
    """Times the bytes arriving, leaving out the wait for each request's answer."""
    step, count = download_requests(size)
    got, seconds = 0, 0.0
    for _ in range(count):
      if self._clock() >= until:
        return Sample(got, seconds, whole=False)
      self._before_request()
      self._open()
      self._check()
      self._http.request("GET", f"/__down?bytes={step}", headers=HEADERS)
      response = self._answer()
      start, left = self._clock(), step
      while left > 0:
        self._check()
        if self._clock() >= until:
          self._http.close()   # the rest of the body is unread, so the next request opens a new connection
          return Sample(got, seconds + self._clock() - start, whole=False)
        read = response.readinto(memoryview(self._buffer)[:min(left, DOWNLOAD_CHUNK)])
        if not read:
          raise ConnectionError("the download ended early")
        left -= read
        got += read
        moved(read, seconds + self._clock() - start)
      seconds += self._clock() - start
    return Sample(got, seconds)

  def upload(self, size: int, until: float, moved: Moved) -> Sample:
    """Times from the first byte sent to the answer, which comes once the far end has the whole body."""
    seconds, left = 0.0, size
    while left > 0:
      self._before_request()
      self._open()
      self._check()
      start = self._clock()
      want = min(left, UPLOAD_MAX)
      self._http.putrequest("POST", "/__up")
      for name, value in {**HEADERS, "Content-Type": "application/octet-stream", "Content-Length": str(want)}.items():
        self._http.putheader(name, value)
      self._http.endheaders()
      while want > 0:
        self._check()
        if self._clock() >= until:
          self._http.close()
          return Sample(0, 0.0, whole=False)   # bytes handed to the socket aren't bytes delivered
        count = min(want, UPLOAD_CHUNK)
        self._http.send(self._zeros[:count])
        want -= count
        left -= count
        moved(count, seconds + self._clock() - start)
      self._check()
      self._answer().read()
      seconds += self._clock() - start
    return Sample(size, seconds)

  def ping(self) -> float:
    """The time to open a TCP connection to the server the transfers used: one round trip, with the name already looked up."""
    self._before_request()
    if self._peer is None:
      found, _, _, _, found_address = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)[0]
      self._peer = (found, found_address)
    family, address = self._peer
    with socket.socket(family, socket.SOCK_STREAM) as sock:
      self._configure_socket(sock, TIMEOUT)
      self._check()
      start = self._clock()
      sock.connect(address)
      return self._clock() - start

  def close(self) -> None:
    self._http.close()


Transfer = Callable[[int, float, Moved], Sample]


def time_of_day() -> float:
  return datetime.now().timestamp()


def on_thread(work: Callable[[], None]) -> None:
  threading.Thread(target=work, name="tandem-network-test", daemon=True).start()


class NetworkTest:
  """Runs one test at a time in the background, and holds what it has measured for the page to draw."""

  def __init__(self, connect: Callable[[Route | None, Check], Link] | None = None, clock: Callable[[], float] = time.monotonic,
               now: Callable[[], float] = time_of_day, spawn: Callable[[Check], None] = on_thread,
               *, read_route: Callable[[], Route | None] = current_route) -> None:
    """Makes a tester.

    Args:
      connect: Makes the link with the confirmed route and a cancellation check.
      clock: The clock rounds are timed with.
      now: The time of day, for when a test ended.
      spawn: Runs a test's work; a thread of its own unless a test replaces it.
      read_route: Reads the currently active connection from the worker.
    """
    self._connect = connect or (lambda route, check: Cloudflare(clock, route=route, check=check, read_route=read_route))
    self._clock, self._now, self._spawn, self._read_route = clock, now, spawn, read_route
    self._lock = threading.Lock()
    self._result = Result()
    self._working = False
    self._run = 0   # goes up with each start and stop, so a test that was stopped can't write over what followed

  def result(self) -> Result:
    with self._lock:
      return self._result

  def start(self, budget: Budget) -> None:
    """Starts a test on its own thread, unless one is running.

    Args:
      budget: The most data it may use.
    """
    with self._lock:
      if self._working:
        return
      self._working = True
      self._run += 1
      run = self._run
      self._result = Result(Phase.DOWNLOAD, budget=budget)
    try:
      self._spawn(lambda: self.run(run, budget))
    except RuntimeError:
      with self._lock:
        self._working = False
        if run == self._run:
          self._result = replace(self._result, phase=Phase.FAILED, problem=Problem.UNREACHABLE, finished=self._now())

  def stop(self) -> None:
    """Request cancellation at the worker's next I/O check and keep measured results."""
    with self._lock:
      if self._result.running:
        self._run += 1
        self._result = replace(self._result, phase=Phase.STOPPED, finished=self._now())

  def run(self, run: int, budget: Budget) -> None:
    """One whole test on the calling thread: download, upload, then ping.

    Args:
      run: The run start() gave it; it stops once that's no longer the current one.
      budget: The most data it may use.
    """
    def check() -> None:
      with self._lock:
        if run != self._run:
          raise Stopped

    link: Link | None = None
    try:
      check()
      route = self._read_route()
      if route is None or not route.unmetered:
        budget = Budget(min(budget.download, METERED.download), min(budget.upload, METERED.upload))
      self._set(run, budget=budget)
      link = self._connect(route, check)
      download = self._measure(run, check, link.download, FIRST_DOWNLOAD, budget.download, PHASE_SECONDS, live=True)
      self._set(run, phase=Phase.UPLOAD, download=download)
      upload = self._measure(run, check, link.upload, FIRST_UPLOAD, budget.upload, UPLOAD_LIMIT)
      self._set(run, phase=Phase.PING, upload=upload)
      pings = []
      for _ in range(PINGS):
        check()
        pings.append(link.ping())
      self._set(run, phase=Phase.DONE, ping=min(pings), finished=self._now())
    except Stopped:
      pass
    except (OSError, http.client.HTTPException) as error:
      with self._lock:
        if run == self._run:
          problem = Problem.REFUSED if isinstance(error, Refused) else Problem.DROPPED if self._result.used else Problem.UNREACHABLE
          self._result = replace(self._result, phase=Phase.FAILED, problem=problem, finished=self._now())
    finally:
      try:
        if link is not None:
          link.close()
      finally:
        with self._lock:
          self._working = False

  def _set(self, run: int, moved: int = 0, **changes: Any) -> None:
    with self._lock:
      if run != self._run:
        raise Stopped
      self._result = replace(self._result, used=self._result.used + moved, **changes)

  def _measure(self, run: int, check: Check, transfer: Transfer, first: int, budget: int, limit: float, live: bool = False) -> float:
    """Times rounds of growing size until one takes long enough to trust.

    Args:
      run: The test's run.
      check: Raises when the run has been cancelled.
      transfer: The link's download or upload.
      first: The first round's size in bytes.
      budget: The most bytes all rounds may move.
      limit: A round is cut this many seconds after the first began.
      live: Show the speed while a round runs (a download: bytes that arrived are bytes measured).

    Returns:
      The last whole round's speed in bits per second, or a cut download's.

    Raises:
      TimeoutError: Nothing was measured in the time allowed.
    """
    began = self._clock()
    size, spent, in_round = first, 0, 0
    speed: float | None = None

    def moved(count: int, seconds: float) -> None:
      nonlocal spent, in_round
      spent += count
      in_round += count
      self._set(run, count, **({"download": in_round * 8 / seconds} if live and seconds >= LIVE_AFTER else {}))

    while True:
      check()
      in_round = 0
      sample = transfer(min(size, budget - spent), began + limit, moved)
      if sample.size and sample.seconds > 0:
        speed = sample.size * 8 / sample.seconds
      if speed is None:
        raise TimeoutError("too slow to measure")
      # Done once a round ran long enough, time is up, or the budget can't pay for a round as large as the last
      if not sample.whole or sample.seconds >= ENOUGH_SECONDS or self._clock() - began >= PHASE_SECONDS or budget - spent < sample.size:
        return speed
      size = max(sample.size * 2, int(speed / 8 * ROUND_SECONDS))


_shared: NetworkTest | None = None


def shared() -> NetworkTest:
  """The device's one tester, so the last result is still there when the page is opened again."""
  global _shared
  if _shared is None:
    _shared = NetworkTest()
  return _shared
