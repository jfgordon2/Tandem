"""Release Backups with isolated filesystem and current StarPilot ownership."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.prefs import TEMPERATURE
from openpilot.selfdrive.ui.tandem.settings.backup_owner import Backup, BackupStore, SNAPSHOT
from openpilot.selfdrive.ui.tandem.settings.backups import backups_panel
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.system.ui.widgets import DialogResult


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[BackupStore, Mock]:
  """Use a private store with the portable-owner interface and parked admission."""
  store = BackupStore(None, lambda: True, tmp_path / "backups")
  native = Mock()
  native.export.return_value = {"format": "galaxy-toggles"}
  native.restore.return_value = {"complete": True, "skipped": []}

  @contextmanager
  def owner() -> Iterator[tuple[Mock, Callable[[], bool]]]:
    """Use the test owner with the same authorization contract as the device."""
    store._require(store.allowed)
    yield native, store.allowed

  monkeypatch.setattr(store, "_native", owner)
  return store, native


def test_backup_uses_native_snapshot_and_keeps_tandem_prefs(store: tuple[BackupStore, Mock], tandem_prefs: Path) -> None:
  """Keep release's preferences, leave caches live, and restore through the native owner."""
  backups, native = store
  TEMPERATURE.set("F")
  cache = tandem_prefs / ".tandem_forecast.json"
  cache.write_text("forecast")
  backups.create()
  (backup,) = backups.backups()
  folder = backups._folder(backup)
  assert json.loads((folder / SNAPSHOT).read_text()) == native.export.return_value
  TEMPERATURE.set("C")
  cache.write_text("fresh forecast")
  assert backups.restore(backup) == ""
  assert TEMPERATURE.get() == "F" and cache.read_text() == "fresh forecast"
  assert native.restore.call_args.args[0] == native.export.return_value
  assert native.restore.call_args.kwargs["authorized"]()


def test_name_collision_and_stale_selection(store: tuple[BackupStore, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
  """Two saves in one minute get unique names and deleting one preserves the other."""
  backups, _ = store
  clock = Mock(wraps=datetime)
  clock.now.return_value = datetime(2026, 10, 24, 9, 10)
  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.settings.backup_owner.datetime", clock)
  backups.create()
  backups.create()
  newer, older = backups.backups()
  assert newer.key != older.key and newer.name.endswith(" (2)")
  backups.delete(older)
  assert backups.backups() == (newer,)
  with pytest.raises(FileNotFoundError):
    backups.restore(older)
  with pytest.raises(ValueError):
    backups.delete(Backup("../other", "Other", ""))


def test_interrupted_create_never_appears(store: tuple[BackupStore, Mock], monkeypatch: pytest.MonkeyPatch) -> None:
  """Clean up staged data if the vehicle state changes before publishing."""
  backups, native = store
  parked = True

  def export() -> dict[str, str]:
    """Revoke permission while the export is in progress."""
    nonlocal parked
    parked = False
    return {"format": "galaxy-toggles"}

  native.export.side_effect = export
  monkeypatch.setattr(backups, "allowed", lambda: parked)
  with pytest.raises(PermissionError):
    backups.create()
  assert backups.backups() == ()
  assert not list(backups._directory.iterdir())


def test_partial_restore_keeps_tandem_preferences(store: tuple[BackupStore, Mock]) -> None:
  """An incomplete native restore reports its reason and leaves Tandem choices alone."""
  backups, native = store
  TEMPERATURE.set("F")
  backups.create()
  (backup,) = backups.backups()
  TEMPERATURE.set("C")
  native.restore.return_value = {"complete": False, "error": "The vehicle state changed."}
  assert backups.restore(backup) == "The vehicle state changed."
  assert TEMPERATURE.get() == "C"


def test_restore_reports_only_different_skipped_choices(store: tuple[BackupStore, Mock]) -> None:
  """An unavailable setting that already matches does not make a restore incomplete."""
  backups, native = store
  native.export.return_value = {"settings": [
    {"key": "AlwaysAllowUploads", "value": "On"},
    {"key": "UnavailableOption", "value": "Off"},
  ]}
  backups.create()
  (backup,) = backups.backups()
  native.restore.return_value = {"complete": True, "skipped": ["AlwaysAllowUploads", "UnavailableOption"]}
  assert backups.restore(backup) == ""
  native.export.return_value = {"settings": [{"key": "AlwaysAllowUploads", "value": "On"}]}
  assert backups.restore(backup) == "Some settings were unavailable and could not be restored (1)."


def test_restore_uses_release_confirmation_and_ignores_repeated_start(monkeypatch: pytest.MonkeyPatch) -> None:
  """Cancel does nothing, and confirmation schedules a single restore away from the UI thread."""
  jobs = []
  sample = Backup("test", "Backup 2026-10-24 0910", "Oct 24, 2026 9:10 AM")
  store = Mock(spec=BackupStore)
  store.allowed = Mock(return_value=True)
  store.backups.return_value = (sample,)
  store.restore.return_value = ""

  def fake_thread(*, target: Callable[[], None], **kwargs: object) -> SimpleNamespace:
    """Let the test deliver the job result deterministically."""
    return SimpleNamespace(start=lambda: jobs.append(target))

  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.settings.backups.threading.Thread", fake_thread)
  window = SettingsWindow({Tab.DEVICE: lambda: backups_panel(store, window)}, initial=Tab.DEVICE)
  panel = window.top
  window.show_event()
  jobs.pop()()
  panel._update_state()
  restore = panel._content.items[1]._control._buttons[1]
  restore._click_callback()
  dialog = window._overlay
  assert dialog._title == "Restore this backup?"
  dialog._on_result(DialogResult.CANCEL)
  assert jobs == [] and not store.restore.called

  restore._click_callback()
  window._overlay._on_result(DialogResult.CONFIRM)
  panel._content._header_control._click_callback()
  assert len(jobs) == 1 and not restore.enabled
  jobs.pop()()
  panel._update_state()
  store.restore.assert_called_once_with(sample)
  store.create.assert_not_called()


def test_restoring_a_saved_upload_mode_replaces_existing_marker(
  store: tuple[BackupStore, Mock], tandem_prefs: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  """An existing upload policy never falls back to Always during a restore."""
  backups, _ = store
  marker = tandem_prefs / ".tandem_uploads"
  marker.write_text("parked")
  backups.create()
  (backup,) = backups.backups()
  marker.write_text("off")
  unlink = Path.unlink

  def guard(path: Path, *, missing_ok: bool = False) -> None:
    """Include ordinary preference cleanup and reject a gap in this marker."""
    assert path != marker
    unlink(path, missing_ok=missing_ok)

  monkeypatch.setattr(Path, "unlink", guard)
  assert backups.restore(backup) == ""
  assert marker.read_text() == "parked"
