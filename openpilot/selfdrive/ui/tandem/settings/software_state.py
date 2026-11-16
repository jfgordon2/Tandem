"""Read and act on StarPilot's software state away from the frame loop."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
import time
from typing import Any

from openpilot.selfdrive.ui.tandem.home_software import HomeSoftware, InstallTarget, SoftwareOwner, notes_text, project_software, qualified_description


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
  """The schedule and revision shown when automatic installation is edited."""

  enabled: bool
  schedule: str
  zone: str
  revision: str


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
  if (isinstance(auto_installs, bool) and isinstance(schedule, str) and isinstance(zone, str) and isinstance(revision, str)
      and schedule and zone and revision):
    installs = InstallPreference(auto_installs, schedule, zone, revision)
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

  def _work(self, payload: dict[str, object] | None = None) -> tuple[SoftwareState, bool]:
    if self._owner is None:
      self._owner = self._make_owner()
    failed = False
    if payload is not None:
      try:
        self._owner.action(str(payload["action"]), payload, authorized=self._authorized)
      except Exception as error:
        self._report(error)
        failed = True
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

  def _submit(self, **payload: object) -> bool:
    if not self.writable:
      return False
    # A refresh already running may finish first. Every action carries the source the user saw.
    self._writing = True
    self.failed = False
    self._pending = self._pool.submit(self._work, payload)
    self._next = self._clock() + 1.0
    return True

  def check(self) -> bool:
    """Request a check only while the owner's observation permits it."""
    return self.state.can_check and self._submit(action="check")

  def download(self) -> bool:
    """Download the selected branch, with the owner rechecking the target."""
    return self.state.can_download and bool(self.state.branch) and self._submit(action="download", branch=self.state.branch)

  def install(self, shown: InstallTarget) -> bool:
    """Ask for a restart with the exact installed and prepared revisions in the notes."""
    return shown == self.state.home.target and self._submit(action="install", branch=shown.branch,
                                                            expectedCommit=shown.installed_commit, selectedCommit=shown.prepared_commit)

  def automatic_downloads(self, enabled: bool) -> bool:
    """Change downloads using the last displayed expected value."""
    expected = self.state.downloads
    return self.state.can_configure and expected is not None and enabled != expected and self._submit(
      action="preferences", automaticDownloads=enabled, expectedAutomaticDownloads=expected)

  def automatic_installs(self, enabled: bool) -> bool:
    """Preserve the existing schedule and timezone when changing automatic installation."""
    saved = self.state.installs
    return self.state.can_configure and saved is not None and enabled != saved.enabled and self._submit(
      action="install-preferences", automaticInstalls=enabled, restartSchedule=saved.schedule,
      restartTimezone=saved.zone, expectedRevision=saved.revision)

  def close(self) -> None:
    """Release worker resources once the settings window is discarded."""
    self._pool.shutdown(wait=False, cancel_futures=True)
