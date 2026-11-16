"""Tandem's hotspot name, stored in NetworkManager's existing Wi-Fi profile.

The profile ID identifies a renamed hotspot at startup, before upstream decides whether to create its default.
All scanning, activation, passwords and routing still use upstream's WifiManager. Its own UI keeps that class.
"""
from __future__ import annotations

import threading
from dataclasses import replace

from openpilot.system.ui.lib import wifi_manager as upstream
from openpilot.starpilot.tandem.radios import RadioControls

HOTSPOT_PROFILE = "Tandem hotspot"


def name_problem(name: str) -> str | None:
  """Why name can't be a hotspot name: "empty", "long" (over 32 bytes) or "control" (control characters); None when it can."""
  if not name.strip():
    return "empty"
  try:
    if len(name.encode("utf-8")) > 32:
      return "long"
  except UnicodeEncodeError:
    return "control"
  if any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name):
    return "control"
  return None


class WifiManager(upstream.WifiManager):
  """Upstream's WifiManager with a hotspot name kept in NetworkManager's own Wi-Fi profile."""

  def __init__(self, active: bool = True):
    self.tethering_name_busy = False
    self.tethering_name_failed = False
    super().__init__(active)
    self.radios = None if self._fake_networking or self._backend_unavailable else RadioControls()

  def _init_connections(self) -> None:
    super()._init_connections()
    for ssid, path in self._connections.items():
      settings = self._get_connection_settings(path)
      if (settings.get("connection", {}).get("id", (None, None))[1] == HOTSPOT_PROFILE and
          settings.get("802-11-wireless", {}).get("mode", (None, None))[1] == "ap"):
        self._tethering_ssid = ssid
        break

  @property
  def tethering_ssid(self) -> str:
    return self._tethering_ssid

  @property
  def tethering_name_ready(self) -> bool:
    return not (self._backend_unavailable or self._nmcli_networking or self.tethering_name_busy) and (
      self._fake_networking or self._tethering_ssid in self._connections)

  def set_tethering_ssid(self, name: str) -> None:
    """Renames the hotspot in its NetworkManager profile, keeping its secrets."""
    if name_problem(name):
      raise ValueError("Invalid hotspot name")
    if not self.tethering_name_ready:
      return
    self.tethering_name_failed = False
    if name == self._tethering_ssid:
      return
    if name in self._connections:
      self.tethering_name_failed = True
      return
    self.tethering_name_busy = True

    def worker() -> None:
      try:
        old_name = self._tethering_ssid
        was_active = self.is_tethering_active()
        path = self._connections.get(old_name)
        if not self._fake_networking:
          router = self._router_main
          if path is None or router is None:
            raise RuntimeError("Hotspot profile unavailable")
          settings = self._get_connection_settings(path)
          if not settings or settings.get("802-11-wireless", {}).get("mode", (None, None))[1] != "ap":
            raise RuntimeError("Hotspot profile unavailable")
          address = upstream.DBusAddress(path, bus_name=upstream.NM, interface=upstream.NM_CONNECTION_IFACE)
          # GetSettings omits secrets. Preserve them explicitly when replacing the profile with Update:
          # https://www.networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Settings.Connection.html
          secrets = router.send_and_get_reply(upstream.new_method_call(
            address, "GetSecrets", "s", ("802-11-wireless-security",)))
          if secrets.header.message_type == upstream.MessageType.error:
            raise RuntimeError("Hotspot password unavailable")
          security = secrets.body[0].get("802-11-wireless-security", {})
          if not security.get("psk", (None, ""))[1]:
            raise RuntimeError("Hotspot password unavailable")
          settings["802-11-wireless-security"].update(security)
          settings["802-11-wireless"]["ssid"] = ("ay", name.encode("utf-8"))
          settings["connection"]["id"] = ("s", HOTSPOT_PROFILE)
          reply = router.send_and_get_reply(upstream.new_method_call(address, "Update", "a{sa{sv}}", (settings,)))
          if reply.header.message_type == upstream.MessageType.error:
            raise RuntimeError("Hotspot update failed")
        self._connections = {ssid: p for ssid, p in self._connections.items() if ssid != old_name}
        self._connections[name] = path or name
        self._tethering_ssid = name
        self._networks = [replace(n, ssid=name) if n.is_tethering and n.ssid == old_name else n for n in self._networks]
        if was_active:
          self.activate_connection(name, block=True)
      except Exception:
        # Never log a settings/secret reply: the UI reports the failure without exposing a password.
        upstream.cloudlog.warning("Could not change hotspot name")
        self.tethering_name_failed = True
      finally:
        self.tethering_name_busy = False

    threading.Thread(target=worker, daemon=True).start()
