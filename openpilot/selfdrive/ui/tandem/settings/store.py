"""Reads and writes plain openpilot settings the way openpilot's own settings screen does (StarPilot 7's typed Params).

Settings StarPilot 7 keeps behind its owners (speed limits, lane changes, profiles...) go through starpilot7.py instead.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator


class SettingsStore:
  """Reads and writes Params; StarPilot 7's processes read their settings themselves, so a write needs no signal."""

  def __init__(self, cache: Any | None = None, notify: Callable[[], None] | None = None):
    if cache is None:
      from openpilot.selfdrive.ui.ui_state import ui_state
      cache = ui_state.params
    if notify is None:
      notify = lambda: None  # noqa: E731
    self._cache = cache
    self._notify = notify
    self._batching = 0
    self._pending = False

  @contextmanager
  def batch(self) -> Iterator[None]:
    """Group many writes (e.g. Reset Settings) so the driving processes are signalled once, at the end."""
    self._batching += 1
    try:
      yield
    finally:
      self._batching -= 1
      if not self._batching and self._pending:
        self._pending = False
        self._notify()

  def get_bool(self, key: str) -> bool:
    return bool(self._cache.get_bool(key))

  def get_int(self, key: str) -> int:
    try:
      return int(self._cache.get(key, return_default=True) or 0)
    except (TypeError, ValueError):
      return 0

  def get_float(self, key: str) -> float:
    try:
      return float(self._cache.get(key, return_default=True) or 0.0)
    except (TypeError, ValueError):
      return 0.0

  def get_str(self, key: str) -> str:
    value = self._cache.get(key, return_default=True)
    return value.decode() if isinstance(value, bytes) else str(value or "")

  def get_json(self, key: str) -> Any:
    """JSON params come back parsed; returns None when unset."""
    return self._cache.get(key, return_default=True)

  def write(self, values: dict) -> None:
    """Write several params, then notify once. Params converts each value to its key's registered type."""
    for key, value in values.items():
      if isinstance(value, bool):
        self._cache.put_bool(key, value, block=True)
      else:
        self._cache.put(key, value, block=True)
    if self._batching:
      self._pending = True
    else:
      self._notify()
