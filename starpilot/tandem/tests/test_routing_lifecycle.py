"""Manager demand, cold preview startup and actual broker idle exit, without device dependencies."""
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import pytest

from openpilot.starpilot.tandem.routing import client, config as C, demand, maps


class Params:
  def get(self, name):
    assert name == "NavDestination"
    return (C.root() / "destination").exists()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  for screen in C.SCREENS:
    monkeypatch.setenv(screen, "1")
  # macOS pytest paths can exceed the Unix socket path limit.
  with tempfile.TemporaryDirectory(prefix="trl-", dir="/tmp") as state:
    monkeypatch.setenv("TANDEM_STATE_DIR", str(Path(state) / "state"))
    yield


def gate(started=True):
  # Resolve the real process_config alias without importing its hardware/cereal
  # dependencies; also check the actual registration uses that predicate.
  source = Path(__file__).resolve().parents[3] / "system/manager/process_config.py"
  tree = ast.parse(source.read_text())
  hook = next(node for node in tree.body if isinstance(node, ast.ImportFrom) and
              node.module == "openpilot.starpilot.tandem.routing.config")
  alias, = hook.names
  process = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                 isinstance(node.func, ast.Name) and node.func.id == "PythonProcess" and
                 node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "tandem_routingd")
  assert process.args[2].id == alias.asname
  return getattr(importlib.import_module(hook.module), alias.name)(started, Params(), None, None)


def test_manager_does_not_start_routing_on_a_drive_without_a_route_or_download():
  assert not gate(started=False)
  assert not gate(started=True)
  assert not C.root().exists() and not C.socket_path().parent.exists()


@pytest.mark.parametrize("phase", [None, "road", "prepare", "download", "install"])
def test_queued_and_active_including_paused_map_jobs_start_the_process(phase):
  C.atomic_json(C.root() / "map-request.json", {"id": "new", "selection": "us_state.IA"})
  if phase:
    C.atomic_json(C.root() / "map-job.json", {"id": "new", "phase": phase, "paused": True})
  assert maps.running() and demand.download_pending() and gate()


@pytest.mark.parametrize("phase", ["ready", "failed", "cancelled"])
def test_completed_jobs_do_not_start_but_a_new_request_does(phase):
  C.atomic_json(C.root() / "map-request.json", {"id": "old"})
  C.atomic_json(C.root() / "map-job.json", {"id": "old", "phase": phase})
  assert not maps.running() and not gate()
  C.atomic_json(C.root() / "map-request.json", {"id": "new"})
  assert gate()


def test_destination_and_preview_wake_work_before_and_during_a_drive(monkeypatch):
  C.atomic_json(C.root() / "destination", {})
  assert gate(started=False) and gate(started=True)
  (C.root() / "destination").unlink()
  assert not gate()
  assert demand.wake() and gate(started=False) and gate(started=True)
  stamp = json.loads((C.socket_path().parent / demand.WAKE.name).read_text())["time"]
  monkeypatch.setattr(time, "monotonic", lambda: stamp + demand.IDLE_SECONDS + .01)
  assert not gate()
  monkeypatch.setattr(time, "monotonic", lambda: stamp - 1)
  assert not gate()  # A clock reset/reboot cannot revive a previous session.


@pytest.mark.parametrize("switch", ["TANDEM_ROUTING", *C.SCREENS])
def test_rollback_wins_over_destination_map_job_and_preview(switch, monkeypatch):
  C.atomic_json(C.root() / "destination", {})
  C.atomic_json(C.root() / "map-request.json", {"id": "new"})
  assert demand.wake()
  monkeypatch.setenv(switch, "0")
  assert not gate() and not demand.wake()
  with pytest.raises(C.RoutingError, match="worker_failed"):
    client.request("route", caller="preview")


@pytest.mark.parametrize("action", ["status", "release"])
def test_status_checks_and_release_do_not_wake_a_stopped_broker(action, monkeypatch):
  monkeypatch.setattr(demand, "wake", lambda: pytest.fail("status/release must not wake the broker"))
  with pytest.raises(C.RoutingError, match="worker_failed"):
    client.request(action)
  assert not gate()


def test_cold_start_wait_is_bounded_and_invalid_requests_do_not_wake():
  start = time.monotonic()
  with pytest.raises(C.RoutingError, match="timeout"):
    client.request("route", timeout=.1, caller="preview")
  assert time.monotonic() - start < 1
  (C.socket_path().parent / demand.WAKE.name).unlink()
  with pytest.raises(C.RoutingError, match="worker_failed"):
    client.request("route", invalid=float("nan"))
  assert not gate()


# Exercise the real main loop, signal handlers, socket protocol and Broker.
# Only device Params/map scheduling and native Valhalla execution are stand-ins.
CHILD = """
import sys, time
from types import SimpleNamespace
from openpilot.starpilot.tandem.routing import config as C, demand, maps, routingd
class Params:
  def get(self, name):
    return (C.root() / 'destination').exists()
class Native:
  last_used = 0
  def close(self):
    pass
  def call(self, message):
    time.sleep(.05)
    return {'status': 'ok', 'generation': 'test', 'route': {'test': True}}
sys.modules['openpilot.common.params'] = SimpleNamespace(Params=Params)
demand.IDLE_SECONDS = 1
maps.run = lambda stop: stop.wait()
routingd.Native = Native
routingd.capability = lambda: {'status': 'ready', 'generation': 'test'}
routingd.main()
"""


@pytest.fixture
def broker_process():
  processes = []
  def start():
    process = subprocess.Popen([sys.executable, "-c", CHILD], env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(process)
    return process
  yield start
  for process in processes:
    if process.poll() is None:
      process.terminate()
    try:
      process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
      process.communicate(timeout=5)


def until(predicate, timeout=5):
  end = time.monotonic() + timeout
  while not predicate():
    assert time.monotonic() < end, "condition did not become true"
    time.sleep(.01)


def test_preview_wakes_a_stopped_broker_then_it_exits_and_can_restart(broker_process, monkeypatch):
  monkeypatch.setattr(demand, "IDLE_SECONDS", 1)
  assert not gate()
  for _ in range(2):
    with ThreadPoolExecutor() as pool:
      future = pool.submit(client.request, "route", caller="preview", generation="test", timeout=5)
      until(lambda: gate(started=False))
      # This is the manager's next tick, after the preview has signaled demand.
      process = broker_process()
      result = future.result(timeout=6)
      assert result["status"] == "ok" and result["route"] == {"test": True}
      assert not (C.root() / "destination").exists()
    output, error = process.communicate(timeout=5)
    assert process.returncode == 0, (output, error)
    assert not C.socket_path().exists() and not gate()


@pytest.mark.parametrize("kind", ["destination", "map"])
def test_pending_work_keeps_broker_alive_until_finished(kind, broker_process, monkeypatch):
  monkeypatch.setattr(demand, "IDLE_SECONDS", 1)
  if kind == "destination":
    C.atomic_json(C.root() / "destination", {})
  else:
    C.atomic_json(C.root() / "map-request.json", {"id": "new"})
    C.atomic_json(C.root() / "map-job.json", {"id": "new", "phase": "download", "paused": True})
  assert gate()
  process = broker_process()
  until(lambda: C.socket_path().exists())
  time.sleep(1.2)
  assert process.poll() is None and gate()
  if kind == "destination":
    (C.root() / "destination").unlink()
  else:
    C.atomic_json(C.root() / "map-job.json", {"id": "new", "phase": "ready"})
  output, error = process.communicate(timeout=5)
  assert process.returncode == 0, (output, error)
  assert not gate()


def test_manager_demand_check_does_not_load_the_map_installer_or_worker():
  result = subprocess.run([sys.executable, "-c", """
import sys
from types import SimpleNamespace
from openpilot.starpilot.tandem.routing.config import should_run
assert not should_run(True, SimpleNamespace(get=lambda _: None), None, None)
for module in ('maps', 'routingd', 'native_worker', 'datasets', 'catalog', 'downloads', 'images'):
  assert 'openpilot.starpilot.tandem.routing.' + module not in sys.modules, module
"""], capture_output=True, timeout=5)
  assert result.returncode == 0, result.stderr
