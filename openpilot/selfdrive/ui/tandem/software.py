"""StarPilot's software state, read once for Home and the Software tab, and the actions both send through it.

One SoftwareWatch (shared_software) reads StarPilot 7's software owner (SoftwareOperations) on a worker thread, so status
checks and git reads stay off the drawing thread, and serializes every action. Home shows its HomeSoftware projection; the
Software tab shows the rest. Each action carries the revision the driver saw, and the owner rechecks parked state itself.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
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
  """The StarPilot software operations Tandem uses (SoftwareOperations)."""

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
  # StarPilot's version (7.0), as its own screens show it, not openpilot's base version underneath (starpilot/ui/brand.py)
  version = short_version(installed.get("displayVersion")) or short_version(installed.get("version"))
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


class Stage(Enum):
  """States of the installed version card."""

  READING = auto()
  UNAVAILABLE = auto()
  PARK = auto()
  DISABLED = auto()
  CHECKING = auto()
  DOWNLOADING = auto()
  PREPARING = auto()
  RESTARTING = auto()
  DOWNLOAD_FAILED = auto()
  CHECK_FAILED = auto()
  AVAILABLE = auto()
  READY = auto()
  CURRENT = auto()
  IDLE = auto()


@dataclass(frozen=True)
class InstallPreference:
  """The schedule and revision shown when automatic installation is edited. Never saved: off, at the owner's default
  schedule, with no revision to expect."""

  enabled: bool
  schedule: str
  zone: str
  revision: str | None


@dataclass(frozen=True)
class SoftwareState:
  """The verified software information published to the panel."""

  stage: Stage = Stage.READING
  home: HomeSoftware = field(default_factory=HomeSoftware)
  branch: str = ""
  installed_notes: str = ""
  last_checked: str = ""
  next_restart: str = ""
  percent: int | None = None
  downloads: bool | None = None
  installs: InstallPreference | None = None
  can_check: bool = False
  can_download: bool = False
  can_configure: bool = False


def update_stage(updater: Mapping[str, Any], operations: Mapping[str, Any], home: HomeSoftware) -> Stage:
  """Distinguish a new revision, its download, finalization and a qualified install."""
  request = operations.get("request") or {}
  check = (updater.get("fast") or {}).get("check") or {}
  state = updater.get("state")
  reason = operations.get("reason")
  if reason == "Reboot is pending":
    return Stage.RESTARTING
  if operations.get("parked") is not True:
    return Stage.PARK
  if reason == "Updates are disabled":
    return Stage.DISABLED
  if operations.get("updaterAvailable") is not True:
    return Stage.UNAVAILABLE
  if state == "finalizing update...":
    return Stage.PREPARING
  if state in ("downloading...", "updating...") or request.get("state") == "pending" and request.get("action") == "download":
    return Stage.DOWNLOADING
  if state == "checking..." or check.get("state") == "checking" or request.get("state") == "pending" and request.get("action") == "check":
    return Stage.CHECKING
  if home.ready:
    return Stage.READY
  if request.get("state") == "failed" and request.get("action") == "download":
    return Stage.DOWNLOAD_FAILED
  if check.get("state") == "error" or request.get("state") == "failed" or (updater.get("failedCount") or 0) > 0:
    return Stage.CHECK_FAILED
  if (updater.get("targetChangeFound") is True and updater.get("finalizedUpdateReady") is not True and
      operations.get("selectedTarget") == updater.get("targetBranch")):
    return Stage.AVAILABLE
  return Stage.CURRENT if home.current else Stage.IDLE


def project(status: Mapping[str, Any], operations: Mapping[str, Any], read: Callable[[str], Any]) -> SoftwareState:
  """Expose actual progress and retain the exact revisions required for later writes."""
  description, notes = "", b""
  if operations.get("canInstall") is True:
    description = qualified_description(operations, read("UpdaterNewDescription"))
    if description:
      notes = read("UpdaterNewReleaseNotes")
  home = project_software(status, operations if description else {**operations, "canInstall": False},
                          description, notes if isinstance(notes, bytes) else b"")
  updater = status["updater"]
  stage = update_stage(updater, operations, home)
  percent = (operations.get("progress") or {}).get("percent")
  measured = None
  if stage == Stage.DOWNLOADING and isinstance(percent, (int, float)) and not isinstance(percent, bool) and 0 <= percent <= 100:
    measured = round(percent)
  auto_installs = operations.get("automaticInstalls")
  schedule, zone, revision = (operations.get(key) for key in ("restartSchedule", "restartTimezone", "installPreferenceRevision"))
  installs = None
  if (auto_installs is None or isinstance(auto_installs, bool)) and isinstance(schedule, str) and isinstance(zone, str) \
      and schedule and zone and (revision is None and auto_installs is None or isinstance(revision, str) and revision):
    installs = InstallPreference(bool(auto_installs), schedule, zone, revision)
  auto_downloads = operations.get("automaticDownloads")
  installed = read("UpdaterCurrentReleaseNotes")
  return SoftwareState(
    stage, home, operations.get("selectedTarget") or "", notes_text(installed.decode("utf-8", "replace") if isinstance(installed, bytes) else ""),
    updater.get("lastCheckedAt") or "", operations.get("nextRestartAt") or "", measured,
    auto_downloads if type(auto_downloads) is bool else None, installs,
    operations.get("canCheck") is True and stage not in (Stage.CHECKING, Stage.DOWNLOADING, Stage.PREPARING),
    operations.get("canDownload") is True and stage in (Stage.AVAILABLE, Stage.DOWNLOAD_FAILED),
    operations.get("canConfigure") is True,
  )


class SoftwareWatch:
  """Serialize updater reads and actions while the panel is displayed."""

  def __init__(self, make_owner: Callable[[], SoftwareOwner], read: Callable[[str], Any], authorized: Callable[[], bool],
               report: Callable[[Exception], None], clock: Callable[[], float] = time.monotonic):
    self.state = SoftwareState()
    self.failed = False
    self._make_owner, self._read, self._authorized, self._report, self._clock = make_owner, read, authorized, report, clock
    self._owner: SoftwareOwner | None = None
    self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-software")
    self._pending: Future[tuple[SoftwareState, bool]] | None = None
    self._writing = False
    self._next = 0.0

  def _work(self, *payloads: dict[str, object]) -> tuple[SoftwareState, bool]:
    """Send the actions in order, stopping at the first the owner refuses, then read the result."""
    if self._owner is None:
      self._owner = self._make_owner()
    failed = False
    for payload in payloads:
      try:
        self._owner.action(str(payload["action"]), payload, authorized=self._authorized)
      except Exception as error:
        self._report(error)
        failed = True
        break
    operations = self._owner.snapshot(include_history=False)
    return project(self._owner.status.snapshot(), operations, self._read), failed

  @property
  def writable(self) -> bool:
    """Whether the panel can send another action to its owner."""
    return not self._writing and self._authorized()

  def refresh(self) -> None:
    """Re-read on entry, or after using the native options."""
    self._next = 0.0

  def poll(self) -> SoftwareState:
    """Return the last completed snapshot and request a new one when due."""
    if self._pending is not None and self._pending.done():
      try:
        self.state, failed = self._pending.result()
        if self._writing:
          self.failed = failed
      except Exception as error:
        self._report(error)
        if self._writing:
          self.failed = True
        self.state = SoftwareState(stage=Stage.UNAVAILABLE, home=HomeSoftware(installed=self.state.home.installed),
                                   installed_notes=self.state.installed_notes)
      self._writing = False
      self._pending = None
    now = self._clock()
    if self._pending is None and now >= self._next:
      interval = 1.0 if self.state.stage in (Stage.CHECKING, Stage.DOWNLOADING, Stage.PREPARING) else 4.0
      self._pending = self._pool.submit(self._work)
      self._next = now + interval
    return self.state

  def _submit(self, *payloads: dict[str, object]) -> bool:
    if not self.writable or not payloads:
      return False
    # A refresh already running may finish first. Every action carries the source the user saw.
    self._writing = True
    self.failed = False
    self._pending = self._pool.submit(self._work, *payloads)
    self._next = self._clock() + 1.0
    return True

  def check(self) -> bool:
    """Request a check only while the owner's observation permits it."""
    return self.state.can_check and self._submit({"action": "check"})

  def download(self) -> bool:
    """Download the selected branch, with the owner rechecking the target."""
    return self.state.can_download and bool(self.state.branch) and self._submit({"action": "download", "branch": self.state.branch})

  def can_install(self, shown: InstallTarget | None) -> bool:
    """Whether the update the driver is looking at can be installed now."""
    return shown is not None and shown == self.state.home.target and self.writable

  def install(self, shown: InstallTarget) -> bool:
    """Ask for a restart with the exact installed and prepared revisions in the notes."""
    return self.can_install(shown) and self._submit({"action": "install", "branch": shown.branch, "expectedCommit": shown.installed_commit,
                                                     "selectedCommit": shown.prepared_commit})

  @property
  def automatic(self) -> bool | None:
    """Automatic Updates: on when StarPilot both downloads and installs on its own; None until both are known."""
    downloads, installs = self.state.downloads, self.state.installs
    if downloads is None or installs is None:
      return None
    return downloads and installs.enabled

  def set_automatic(self, enabled: bool) -> bool:
    """Turn automatic downloads and automatic installation on or off together, keeping the saved restart schedule and
    time zone, each with the value the driver last saw."""
    downloads, installs = self.state.downloads, self.state.installs
    if not self.state.can_configure or downloads is None or installs is None:
      return False
    changes: list[dict[str, object]] = []
    if downloads != enabled:
      changes.append({"action": "preferences", "automaticDownloads": enabled, "expectedAutomaticDownloads": downloads})
    if installs.enabled != enabled:
      changes.append({"action": "install-preferences", "automaticInstalls": enabled, "restartSchedule": installs.schedule,
                      "restartTimezone": installs.zone, "expectedRevision": installs.revision})
    return self._submit(*changes)

  def close(self) -> None:
    """Release worker resources once the settings window is discarded."""
    self._pool.shutdown(wait=False, cancel_futures=True)


_shared: list[SoftwareWatch] = []


def shared_software() -> SoftwareWatch:
  """The one software watch Home and the Software tab share, made on first use. Imported only on the device."""
  if not _shared:
    from openpilot.common.swaglog import cloudlog
    from openpilot.selfdrive.ui.ui_state import ui_state

    def owner() -> SoftwareOwner:
      from openpilot.starpilot.galaxy.software_operations import SoftwareOperations
      return SoftwareOperations(params=ui_state.params)

    def authorized() -> bool:
      return bool(ui_state.is_offroad() and not ui_state.projection_read_only and ui_state.replay_clock is None)

    _shared.append(SoftwareWatch(owner, ui_state.params.get, authorized, lambda error: cloudlog.warning("Tandem software: %s", error)))
  return _shared[0]
