"""The parked Home card and its guarded action on StarPilot's software owner."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import html
import re
import time
from typing import Any, Protocol

from openpilot.selfdrive.ui.tandem.i18n import N_


@dataclass(frozen=True)
class InstallTarget:
  """The prepared revision and installed revision the driver saw in the notes."""

  branch: str
  installed_commit: str
  prepared_commit: str


@dataclass(frozen=True)
class HomeSoftware:
  """The read-only software state published to Home."""

  installed: str = ""
  current: bool = False
  version: str = ""
  notes: str = ""
  scheduled: bool = False
  target: InstallTarget | None = None

  @property
  def ready(self) -> bool:
    return self.target is not None


class SoftwareOwner(Protocol):
  """The StarPilot operations used by Home."""

  status: Any

  def snapshot(self, *, include_history: bool = True) -> dict: ...
  def action(self, action: str, payload: object, *, authorized: Callable[[], bool]) -> dict: ...


def notes_text(value: str) -> str:
  """Display updater HTML as plain text and preserve paragraph and list boundaries."""
  text = re.sub(r"<\s*li[^>]*>", "• ", value, flags=re.I)
  text = re.sub(r"<\s*(br|/p|/li|/h[1-6]|/ul|/ol)[^>]*>", "\n", text, flags=re.I)
  lines = [line.strip() for line in html.unescape(re.sub(r"<[^>]+>", "", text)).splitlines()]
  return "\n".join(line for line in lines if line) or N_("No release notes for this version.")


def short_version(value: object) -> str:
  """Use the version from the updater's version / branch / commit / date description."""
  return value.split(" / ", 1)[0].strip() if isinstance(value, str) else ""


def project_software(status: Mapping[str, Any], operations: Mapping[str, Any],
                     description: str = "", notes: bytes = b"") -> HomeSoftware:
  """Show an install action only when StarPilot has qualified a specific update."""
  installed, updater = status["installed"], status["updater"]
  version = short_version(installed.get("version")) or short_version(installed.get("displayVersion"))
  branch, old_commit, new_commit = operations.get("selectedTarget"), installed.get("commit"), operations.get("preparedCommit")
  if (operations.get("canInstall") is True and isinstance(branch, str) and branch and isinstance(old_commit, str) and old_commit
      and isinstance(new_commit, str) and new_commit):
    target = InstallTarget(branch, old_commit, new_commit)
    return HomeSoftware(installed=version, version=short_version(description) or N_("A new version"),
                        notes=notes_text(notes.decode("utf-8", "replace")),
                        scheduled=bool(operations.get("nextRestartAt")), target=target)
  check = (updater.get("fast") or {}).get("check") or {}
  current = (operations.get("updaterAvailable") is True and updater.get("state") == "idle"
             and updater.get("finalizedUpdateReady") is False and updater.get("targetChangeFound") is False
             and updater.get("targetBranch") == installed.get("branch") and check.get("state") != "error"
             and bool(updater.get("lastCheckedAt")) and updater.get("failedCount") == 0
             and not updater.get("osUpdate", {}).get("required"))
  return HomeSoftware(installed=version, current=current)


def qualified_description(operations: Mapping[str, Any], description: object) -> str:
  """Only use notes for the prepared branch and commit the owner qualified."""
  parts = description.split(" / ") if isinstance(description, str) else []
  prepared = operations.get("preparedCommit")
  selected = operations.get("selectedTarget")
  if (len(parts) == 4 and parts[1] == selected and len(parts[2]) == 7 and
      isinstance(prepared, str) and prepared.startswith(parts[2])):
    return str(description)
  return ""


class HomeSoftwareWatch:
  """Poll and submit on one worker, so status checks and verification stay off the drawing thread."""

  REFRESH_S = 10.0

  def __init__(self, make_owner: Callable[[], SoftwareOwner], read: Callable[[str], Any],
               authorized: Callable[[], bool], report: Callable[[Exception], None],
               clock: Callable[[], float] = time.monotonic):
    self._make_owner, self._read, self._authorized, self._report = make_owner, read, authorized, report
    self._clock = clock
    self._owner: SoftwareOwner | None = None
    self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-home-software")
    self._pending: Future[HomeSoftware] | None = None
    self._installing = False
    self._next = 0.0
    self.state = HomeSoftware()

  def _refresh(self, target: InstallTarget | None = None) -> HomeSoftware:
    if self._owner is None:
      self._owner = self._make_owner()
    if target is not None:
      self._owner.action("install", {"action": "install", "branch": target.branch,
                                     "expectedCommit": target.installed_commit, "selectedCommit": target.prepared_commit},
                         authorized=self._authorized)
    operations = self._owner.snapshot(include_history=False)
    status = self._owner.status.snapshot()
    if operations.get("canInstall") is not True:
      return project_software(status, operations)
    description = qualified_description(operations, self._read("UpdaterNewDescription"))
    if not description:
      return project_software(status, {})
    notes = self._read("UpdaterNewReleaseNotes")
    return project_software(status, operations, description, notes if isinstance(notes, bytes) else b"")

  def poll(self) -> HomeSoftware:
    """Return the last completed observation and schedule a refresh when due."""
    if self._pending is not None and self._pending.done():
      try:
        self.state = self._pending.result()
      except Exception as error:
        self._report(error)
        self.state = HomeSoftware(installed=self.state.installed)
      self._pending = None
      self._installing = False
    now = self._clock()
    if self._pending is None and not self._installing and now >= self._next and self._authorized():
      self._pending = self._worker.submit(self._refresh)
      self._next = now + self.REFRESH_S
    return self.state

  def can_restart(self) -> bool:
    return self.state.ready and not self._installing and self._authorized()

  def restart(self, shown: InstallTarget) -> bool:
    """Submit exactly the update shown to the driver and recheck authorization in the owner."""
    if shown != self.state.target or not self.can_restart():
      return False
    self._installing = True
    self._pending = self._worker.submit(self._refresh, shown)
    self._next = self._clock() + self.REFRESH_S
    return True

  def close(self) -> None:
    self._worker.shutdown(wait=False, cancel_futures=True)
