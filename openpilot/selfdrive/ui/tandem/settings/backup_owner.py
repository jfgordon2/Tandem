"""Device settings snapshots through StarPilot 7's portable backup owner."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile
from typing import TYPE_CHECKING, Any

from openpilot.selfdrive.ui.tandem.prefs import restore_prefs, save_prefs

if TYPE_CHECKING:
  from openpilot.starpilot.galaxy.toggle_backup import ToggleBackup


DIRECTORY = Path("/data/tandem_backups")
SNAPSHOT = "settings.json"
MAX_SAVED_BYTES = 1 << 20  # The native owner also enforces its own payload limit.
KEY = re.compile(r"(\d{4}-\d{2}-\d{2} \d{4})(?: \(([2-9]|[1-9]\d+)\))?-[a-f0-9]{32}")


@dataclass(frozen=True)
class Backup:
  """A saved snapshot's display name, time and unique directory key."""

  key: str
  name: str
  when: str


class BackupStore:
  """Save named native settings exports beside copies of Tandem's preferences."""

  def __init__(self, params: Any, allowed: Callable[[], bool], directory: Path = DIRECTORY) -> None:
    self.params = params
    self.allowed = allowed
    self._directory = directory

  def _folder(self, backup: Backup) -> Path:
    """Resolve only snapshots from this store, without following a directory symlink."""
    if KEY.fullmatch(backup.key) is None:
      raise ValueError("Invalid settings backup")
    folder = self._directory / backup.key
    if folder.is_symlink() or not stat.S_ISREG((folder / SNAPSHOT).lstat().st_mode):
      raise FileNotFoundError(backup.key)
    return folder

  def backups(self) -> tuple[Backup, ...]:
    """List complete snapshots, newest first, using release's display dates."""
    if not self._directory.exists():
      return ()
    entries = []
    for folder in self._directory.iterdir():
      match = KEY.fullmatch(folder.name)
      if match is None or folder.is_symlink():
        continue
      try:
        saved = (folder / SNAPSHOT).lstat()
      except FileNotFoundError:
        continue
      if not stat.S_ISREG(saved.st_mode):
        continue
      name = "Backup " + match[1] + (f" ({match[2]})" if match[2] else "")
      when = datetime.fromtimestamp(saved.st_mtime).strftime("%b %-d, %Y %-I:%M %p")
      entries.append((saved.st_mtime_ns, Backup(folder.name, name, when)))
    entries.sort(key=lambda entry: entry[0], reverse=True)
    return tuple(backup for _, backup in entries)

  @contextmanager
  def _native(self) -> Iterator[tuple[ToggleBackup, Callable[[], bool]]]:
    """Sample StarPilot's offroad and vehicle evidence on the operation's own thread."""
    from openpilot.starpilot.galaxy.onroad_layout import OnroadLayoutOwner
    from openpilot.starpilot.galaxy.settings import LiveContextSource, SettingsGateway
    from openpilot.starpilot.galaxy.toggle_backup import ToggleBackup

    authority = LiveContextSource(self.params)

    def authorized() -> bool:
      """Require both the local UI and verified offroad state throughout a restore."""
      return self.allowed() and authority.offroad()

    gateway = SettingsGateway(self.params, authority)
    layout = OnroadLayoutOwner(self.params, authorized, lambda: authority.sample().cp)
    try:
      self._require(authorized)
      yield ToggleBackup(gateway, layout), authorized
    finally:
      gateway.close()

  @staticmethod
  def _require(authorized: Callable[[], bool]) -> None:
    """Reject a change if the vehicle or local settings session has changed."""
    if not authorized():
      raise PermissionError("Park the vehicle before changing backups.")

  def create(self) -> None:
    """Publish a complete snapshot in one rename after exporting and copying preferences."""
    with self._native() as (owner, authorized):
      data = json.dumps(owner.export(), allow_nan=False)
      minute = datetime.now().strftime("%Y-%m-%d %H%M")
      names = {backup.name for backup in self.backups()}
      suffix = ""
      number = 2
      while f"Backup {minute}{suffix}" in names:
        suffix = f" ({number})"
        number += 1
      target = self._directory / f"{minute}{suffix}-{secrets.token_hex(16)}"
      self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
      with tempfile.TemporaryDirectory(prefix=".backup-", dir=self._directory) as staging:
        folder = Path(staging)
        (folder / SNAPSHOT).write_text(data, encoding="utf-8")
        save_prefs(folder)
        self._require(authorized)
        folder.rename(target)

  def restore(self, backup: Backup) -> str:
    """Restore through StarPilot and report partial or skipped settings to the driver."""
    folder = self._folder(backup)
    with (folder / SNAPSHOT).open("rb") as source:
      encoded = source.read(MAX_SAVED_BYTES + 1)
    if len(encoded) > MAX_SAVED_BYTES:
      raise ValueError("Settings backup is too large")
    payload = json.loads(encoded)
    with self._native() as (owner, authorized):
      identity = (secrets.token_urlsafe(24), secrets.token_bytes(16))
      result = owner.restore(payload, identity, authorized=authorized)
      if not result["complete"]:
        return str(result["error"])
      self._require(authorized)
      restore_prefs(folder)
      skipped = self._unrestored(owner, payload, result["skipped"])
      return f"Some settings were unavailable and could not be restored ({skipped})." if skipped else ""

  @staticmethod
  def _unrestored(owner: ToggleBackup, payload: dict[str, Any], skipped: list[str]) -> int:
    """Count skipped choices that differ from the backup or cannot be verified."""
    if not skipped:
      return 0
    try:
      current = {entry["key"]: entry["value"] for entry in owner.export()["settings"]}
    except (OSError, RuntimeError, ValueError):
      return len(skipped)
    expected = {entry["key"]: entry["value"] for entry in payload["settings"]}
    return sum(current.get(key) != expected[key] for key in skipped)

  def delete(self, backup: Backup) -> None:
    """Remove the selected snapshot by its unique key."""
    self._require(self.allowed)
    shutil.rmtree(self._folder(backup))
