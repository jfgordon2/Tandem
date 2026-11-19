"""Install a pinned binary wheel into a dedicated environment, including pip-less AGNOS."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import urllib.request
import venv
import zipfile
import hashlib
import time

from openpilot.starpilot.tandem.routing import config as C


def checked_run(command, cancelled=lambda: False, timeout=300):
  """Stop installation when cancelled or when the car starts a route or drive."""
  with subprocess.Popen(command) as process:
    deadline = time.monotonic() + timeout
    try:
      while process.poll() is None:
        if cancelled():
          raise C.RoutingError("cancelled")
        C.require_parked()
        if time.monotonic() >= deadline:
          raise C.RoutingError("timeout")
        time.sleep(.1)
      if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)
    finally:
      if process.poll() is None:
        process.terminate()
        try:
          process.wait(timeout=3)
        except subprocess.TimeoutExpired:
          process.kill()
          process.wait(timeout=3)


def prepare(cancelled=lambda: False) -> Path:
  C.require_parked()
  python = C.runtime_python()
  if C.runtime_ready():
    return python
  folder = python.parent.parent
  venv.EnvBuilder(with_pip=False).create(folder)
  # Ubuntu may ship venv without ensurepip. Bootstrap only into this new environment.
  with urllib.request.urlopen("https://pypi.org/pypi/pip/25.3/json", timeout=30) as response:
    release = json.load(response)
  wheel = next(item for item in release["urls"] if item["filename"].endswith("py3-none-any.whl"))
  wheel_path = folder / wheel["filename"]
  with urllib.request.urlopen(wheel["url"], timeout=60) as response:
    data = response.read(8 * 1024**2)
  if hashlib.sha256(data).hexdigest() != wheel["digests"]["sha256"]:
    raise C.RoutingError("data_incompatible")
  wheel_path.write_bytes(data)
  site = Path(subprocess.check_output([str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip())
  with zipfile.ZipFile(wheel_path) as archive:
    for name in archive.namelist():
      if name.startswith("/") or ".." in Path(name).parts:
        raise C.RoutingError("data_incompatible")
    archive.extractall(site)
  report = folder / "pip-report.json"
  checked_run([str(python), "-m", "pip", "install", "--only-binary=:all:", "--report", str(report),
               f"pyvalhalla=={C.VERSION}"], cancelled)
  checked_run([str(python), "-c", "import valhalla; print('Valhalla import OK')"], cancelled, timeout=30)
  C.require_parked()
  if cancelled():
    raise C.RoutingError("cancelled")
  C.atomic_json(folder / "receipt.json", {"version": C.VERSION, "bootstrap": {"filename": wheel["filename"],
                "sha256": wheel["digests"]["sha256"]}, "packages": json.loads(report.read_text())})
  return python


if __name__ == "__main__":
  print(prepare())
