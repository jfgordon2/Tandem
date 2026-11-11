"""Reads and writes settings the same way StarPilot's own screens do."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator


class SettingsStore:
  """Reads through the shared per-frame param cache; every write signals the driving processes once."""

  def __init__(self, cache: Any | None = None, notify: Callable[[], None] | None = None):
    if cache is None:
      from openpilot.selfdrive.ui.lib.ui_param_cache import shared_ui_params
      cache = shared_ui_params()
    if notify is None:
      from openpilot.starpilot.common.starpilot_variables import update_starpilot_toggles
      notify = update_starpilot_toggles
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
    return int(self._cache.get_int(key, return_default=True))

  def get_float(self, key: str) -> float:
    return float(self._cache.get_float(key, return_default=True))

  def get_str(self, key: str) -> str:
    value = self._cache.get(key, return_default=True)
    return value.decode() if isinstance(value, bytes) else str(value or "")

  def get_json(self, key: str) -> Any:
    """JSON params come back parsed; returns None when unset."""
    return self._cache.get(key, return_default=True)

  def write(self, values: dict) -> None:
    """Write several params, then notify once. The type of each value picks the put method."""
    for key, value in values.items():
      if isinstance(value, (str, list, dict)):
        self._cache.put(key, value)
      elif isinstance(value, bool):
        self._cache.put_bool(key, value)
      elif isinstance(value, int):
        self._cache.put_int(key, value)
      else:
        self._cache.put_float(key, float(value))
    self._cache.invalidate()
    if self._batching:
      self._pending = True
    else:
      self._notify()
