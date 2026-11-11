"""Managed local broker: one serialized native Actor, prioritized requests and finite deadlines."""
from __future__ import annotations

from dataclasses import dataclass, field
import fcntl
import itertools
import json
import math
import os
from pathlib import Path
import queue
import selectors
import signal
import socketserver
import subprocess
import threading
import time
from typing import Any, IO, cast

from openpilot.starpilot.tandem.routing import config as C, demand, images
from openpilot.starpilot.tandem.routing.bundles import capability, selected
from openpilot.starpilot.tandem.routing.metrics import memory

IDLE_SECONDS = 15


def _pipes(process: subprocess.Popen[bytes]) -> tuple[IO[bytes], IO[bytes]]:
  """The worker's stdin and stdout. Native opens both as pipes, so neither is None."""
  if process.stdin is None or process.stdout is None:
    raise OSError("native worker has no pipes")
  return process.stdin, process.stdout


class Native:
  """The native worker process, started on demand and stopped when idle or when its data changes."""

  def __init__(self) -> None:
    self.process: subprocess.Popen[bytes] | None = None
    self.last_used = 0.0
    self.retry_at = 0.0

  def close(self) -> None:
    """Stops the worker and releases unused graph images."""
    process, self.process = self.process, None
    if process is not None:
      if process.poll() is None:
        process.terminate()
      try:
        process.wait(timeout=1)
      except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)
      stdin, stdout = _pipes(process)
      try:
        stdin.close()
      except OSError:
        pass
      stdout.close()
    images.release_unused()

  def call(self, message: dict) -> dict:
    """Sends a request to the worker, restarting it if it's gone."""
    try:
      if self.process is None or self.process.poll() is not None:
        self.close()
      with images.reader(selected(message)):
        return self._call(message)
    except C.RoutingError as error:
      if error.code in ("data_incompatible", "data_missing", "superseded"):
        self.close()
      return {"status": error.code}
    finally:
      self.last_used = time.monotonic()
      images.release_unused()

  def _call(self, message: dict) -> dict:
    self.last_used = time.monotonic()
    try:
      if self.process is None or self.process.poll() is not None:
        self.close()
        if time.monotonic() < self.retry_at:
          return {"status": "worker_failed"}
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(Path(__file__).resolve().parents[3]), os.getenv("PYTHONPATH", ""))))
        self.process = subprocess.Popen([str(C.runtime_python()), "-u", "-m", "openpilot.starpilot.tandem.routing.native_worker"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
      stdin, stdout = _pipes(self.process)
      pending = memoryview(json.dumps(message, allow_nan=False).encode() + b"\n")
      os.set_blocking(stdin.fileno(), False)
      with selectors.DefaultSelector() as selector:
        selector.register(stdin, selectors.EVENT_WRITE)
        selector.register(stdout, selectors.EVENT_READ)
        end = min(time.monotonic() + C.DEADLINE - 1, message.get("_deadline", float("inf")))
        data = bytearray()
        while time.monotonic() < end:
          events = selector.select(max(0, end - time.monotonic()))
          if not events:
            break
          for key, _ in events:
            if key.fileobj is stdin:
              try:
                pending = pending[os.write(stdin.fileno(), pending):]
              except BlockingIOError:
                continue
              if not pending:
                selector.unregister(stdin)
            else:
              chunk = os.read(stdout.fileno(), 65536)
              if not chunk:
                raise OSError("native worker exited")
              data.extend(chunk)
              if len(data) > C.MAX_MESSAGE:
                raise ValueError("response too large")
              if data.endswith(b"\n"):
                response = json.loads(data)
                if not isinstance(response, dict) or not isinstance(response.get("status"), str):
                  raise ValueError("invalid native envelope")
                if response["status"] in ("data_incompatible", "data_missing", "superseded"):
                  self.close()
                return response
      self.close()
      self.retry_at = time.monotonic() + 2
      return {"status": "timeout"}
    except (OSError, ValueError, subprocess.SubprocessError):
      self.close()
      self.retry_at = time.monotonic() + 2
      return {"status": "worker_failed"}


@dataclass(order=True)
class Job:
  """A queued request. Navigation comes before previews, then first come first served."""
  priority: int
  sequence: int
  message: dict = field(compare=False)
  ready: threading.Event = field(default_factory=threading.Event, compare=False)
  result: dict = field(default_factory=lambda: {"status": "timeout"}, compare=False)
  deadline: float = field(default_factory=lambda: time.monotonic() + C.DEADLINE, compare=False)


class Broker:
  """Runs requests one at a time on the native worker; a newer request from the same caller supersedes an older one."""

  def __init__(self, native: Native | None = None) -> None:
    self.native = native or Native()
    self.jobs: queue.PriorityQueue[Job] = queue.PriorityQueue(maxsize=3)
    self.sequence = itertools.count()
    self.latest: dict[str, int] = {}
    self.lock = threading.Lock()
    self.stop = threading.Event()
    self.thread = threading.Thread(target=self.run, daemon=True)
    self.thread.start()

  def submit(self, message: dict) -> dict:
    """Queues a request and waits for its result, or busy, superseded or invalid_request."""
    caller = message.get("caller")
    if caller not in ("preview", "navigation", "benchmark"):
      return {"status": "invalid_request"}
    job = Job(1 if caller == "preview" else 0, next(self.sequence), message)
    deadline = message.get("_deadline", job.deadline)
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
      return {"status": "invalid_request"}
    job.deadline = min(job.deadline, deadline)
    with self.lock:
      self.latest[caller] = job.sequence
    try:
      self.jobs.put_nowait(job)
    except queue.Full:
      return {"status": "busy"}
    job.ready.wait(max(0, job.deadline - time.monotonic()))
    with self.lock:
      if self.latest.get(caller) != job.sequence:
        return {"status": "superseded"}
    return job.result

  def run(self) -> None:
    """Serves queued requests until stopped, releasing the idle worker."""
    while not self.stop.is_set():
      try:
        job = self.jobs.get(timeout=1)
      except queue.Empty:
        if time.monotonic() - self.native.last_used > IDLE_SECONDS:
          # Guidance owns the completed route; an idle Actor is only a reroute
          # cache. Cheap verified startup lets us release it during active trips.
          self.native.close()
        continue
      with self.lock:
        current = self.latest.get(job.message["caller"]) == job.sequence
      if not current or time.monotonic() > job.deadline:
        job.result = {"status": "superseded"}
      else:
        state = capability()
        if state["status"] != "ready":
          job.result = state
        elif job.message.get("bundle") is None and state["generation"] != job.message.get("generation"):
          job.result = {"status": "superseded"}
        else:
          try:
            if job.message.get("bundle") is not None and selected(job.message).generation != job.message.get("generation"):
              raise C.RoutingError("superseded")
            job.result = self.native.call({**job.message, "_deadline": job.deadline - .1})
          except C.RoutingError as error:
            job.result = {"status": error.code}
      job.ready.set()
      self.jobs.task_done()
    self.native.close()

  def close(self) -> None:
    self.stop.set()
    self.thread.join(C.DEADLINE + 2)


class Server(socketserver.ThreadingUnixStreamServer):
  """The broker's Unix socket server, with a few request slots."""
  daemon_threads = True
  request_queue_size = 4

  def __init__(self, address: str, broker: Broker) -> None:
    self.broker = broker
    self.slots = threading.BoundedSemaphore(4)
    super().__init__(address, Handler)

  def process_request(self, request: Any, address: Any) -> None:
    """Handles a request on a thread when a slot is free; drops the connection otherwise."""
    if not self.slots.acquire(blocking=False):
      self.shutdown_request(request)
      return
    try:
      super().process_request(request, address)
    except Exception:
      self.slots.release()
      raise

  def process_request_thread(self, request: Any, address: Any) -> None:
    try:
      super().process_request_thread(request, address)
    finally:
      self.slots.release()


class Handler(socketserver.StreamRequestHandler):
  """One request on the socket: a JSON line in, a JSON line out."""

  def handle(self) -> None:
    """Reads one request line, answers status itself or submits a route to the broker, and writes the reply line."""
    self.connection.settimeout(C.DEADLINE + 1)
    message = {}
    try:
      raw = self.rfile.readline(C.MAX_MESSAGE + 1)
      if len(raw) > C.MAX_MESSAGE or not raw.endswith(b"\n"):
        raise ValueError("size")
      message = json.loads(raw)
      if not isinstance(message, dict) or message.get("protocol") != C.PROTOCOL:
        message = {}
        raise ValueError("protocol")
      if message.get("action") == "status":
        result = capability()
      elif message.get("action") == "route":
        demand.wake()
        result = cast(Server, self.server).broker.submit(message)
        demand.wake()
      elif message.get("action") == "release":
        # A serialized release job is unnecessary: idle release happens within a second offroad.
        cast(Server, self.server).broker.native.last_used = 0
        result = {"status": "ok"}
      else:
        raise ValueError("action")
    except (ValueError, TypeError, OSError):
      result = {"status": "invalid_request"}
    try:
      self.wfile.write(json.dumps({**result, **{"broker_" + key: value for key, value in memory().items()}, "protocol": C.PROTOCOL,
                                  "id": message.get("id")}, allow_nan=False).encode() + b"\n")
    except OSError:
      pass


def main() -> None:
  """The routing broker process: serves requests on its socket and runs map jobs while should_run says (the idle grace after a trip or download)."""
  if not C.enabled():
    return
  from openpilot.common.params import Params
  params = Params()
  path = C.socket_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  with (path.parent / "routing.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path.unlink(missing_ok=True)
    broker = Broker()
    from openpilot.starpilot.tandem.routing.maps import run as run_maps
    maps_stop = threading.Event()
    maps_thread = threading.Thread(target=run_maps, args=(maps_stop,), daemon=True)
    maps_thread.start()
    try:
      with Server(str(path), broker) as server:
        path.chmod(0o600)
        demand.wake()
        stopping = threading.Event()
        def stop(*_: object) -> None:
          stopping.set()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        server.timeout = .2
        refresh_at = 0.0
        while not stopping.is_set() and C.should_run(params=params):
          # Keep the idle grace after a trip/download, without a resident
          # process or filesystem write on an otherwise unused drive.
          if time.monotonic() >= refresh_at and demand.needed(params):
            demand.wake()
            refresh_at = time.monotonic() + 5
          server.handle_request()
    finally:
      maps_stop.set()
      maps_thread.join(21)
      broker.close()
      path.unlink(missing_ok=True)


if __name__ == "__main__":
  main()
