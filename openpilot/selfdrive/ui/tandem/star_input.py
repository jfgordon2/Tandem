"""StarPilot 7's input on Tandem's screens: wheel buttons, favorites, controllers and Android Auto taps.

StarPilot runs these from its own app (runtime_app.StarShellSession), which Tandem replaces with openpilot's MainLayout.
TandemStarSession is that session without its screens: it subclasses StarShellSession and sets only what the session's
input methods read (the owners and dispatchers, set exactly as StarShellSession.__init__ sets them), skipping the fonts,
view, PiP renderer, map layer and favorite tiles. Every decision (what a wheel press does, whether it's allowed now, the
favorites, Android Auto bookmarks and speed-limit taps) is StarPilot's own inherited code. The few callbacks StarPilot's
layout supplies come from openpilot's: a bookmark from MainLayout, personality from openpilot's toggles, and
Experimental mode from openpilot's button.

tests/test_star_input.py checks this against StarShellSession after every merge: each attribute those methods read is
set here, and each one set here is set by the same code as StarPilot's (KNOWN_DIFFERENCES lists the deliberate ones).
"""
from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from openpilot.cereal import messaging
from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.selfdrive.ui.tandem.map_schedule import MapScheduleWatch, on_wifi
from openpilot.starpilot.ui.runtime_app import (AppearanceOwner, BookmarkReceiver, CruiseActionPublisher, Destination, DisplayOwner,
                                                DriveStateControl, DriveStateOwner, FavoritesOwner, FeaturePage, FeatureSettingsOwner,
                                                PhysicalSource, PiPOwner, PowerOwner, RuntimeSnapshotAdapter, ShellMode,
                                                SlcActionDispatcher, SlcActionReceiver, SoundsOwner, StarShellSession, WheelConsumer,
                                                _galaxy_access_owner, _slc_action_publisher, diagnostic_choice_enabled,
                                                slc_action_transport_enabled, starpilot_storage_root)
from openpilot.starpilot.ui.presentation import Profile


class TandemStarSession(StarShellSession):
  """StarPilot's session for input only (see the module docstring).

  Args:
    bookmark: Saves a bookmark (MainLayout's).
    personality: Sets the driving personality (0 Aggressive, 1 Standard, 2 Relaxed); True when it was allowed.
    experimental: Toggles Experimental mode; True when it was allowed.
  """

  def __init__(self, bookmark: Callable[[], None], personality: Callable[[int], bool], experimental: Callable[[], bool]):
    # No super().__init__(): that builds StarPilot's screens. What follows is StarShellSession.__init__'s non-drawing part.
    profile = Profile.LARGE
    self.profile = profile
    self.network_layer = None
    self.settings_layer = None
    self.home_stats_source = None   # Home's stats are Tandem's own
    self.galaxy_access = _galaxy_access_owner()
    self.bluetooth_source = None
    self.adapter = RuntimeSnapshotAdapter(ui_state, self.galaxy_access, None, home_stats=None)
    self.feature_owner = FeatureSettingsOwner(ui_state.params, self._feature_authority,
                                               learning_messages=lambda: ui_state.sm,
                                               vehicle_fingerprint=lambda: getattr(ui_state.CP, "carFingerprint", None),
                                               vehicle_params=lambda: ui_state.CP,
                                               vision_development=lambda: diagnostic_choice_enabled(os.environ, ui_state.CP))
    self.sounds_owner = SoundsOwner(ui_state.params, self._settings_preference_authority)
    self.appearance_owner = AppearanceOwner(ui_state.params, lambda: self._settings_preference_authority() or self._favorite_authority())
    self.pip_owner = PiPOwner(ui_state.params, self._settings_preference_authority, lambda: False)   # no PiP renderer here
    self.appearance_page = "appearance"
    self.display_owner = DisplayOwner(ui_state.params, self._settings_preference_authority)
    self.model_source = None
    self._home_model = None
    self.map_source = None
    self.model_scroll = 0
    self.model_page = "models"
    self.model_stack = []
    self.model_filter, self.model_sort, self.model_size = "installed", "date", "all"
    self.drive_state = DriveStateControl(DriveStateOwner(ui_state.params, starpilot_storage_root() / "drive-state"),
                                         PhysicalSource(ui_state.sm))
    self.system_power_action = None
    self.power_owner = PowerOwner(ui_state.params, self._settings_preference_authority)
    self._power_request_epoch = 0
    self._pip_request_epoch = 0
    self._lane_change_request_epoch = 0
    self.feature_page = FeaturePage.HUB
    self.feature_root_page = FeaturePage.HUB
    self.feature_scroll = 0
    self.feature_edit_key = None
    self.sounds_scroll = 0
    self.sounds_edit_key = None
    self.appearance_scroll = 0
    self.appearance_edit_key = None
    self.display_scroll = 0
    self.display_page = "system"
    self.display_edit_key = None
    self.slc_actions = None
    if slc_action_transport_enabled(os.environ, ui_state.params):
      try:
        self.slc_actions = SlcActionDispatcher(_slc_action_publisher(), self._live_slc_message)
      except (OSError, RuntimeError):
        pass  # The shell stays readable and reports action unavailability.
    self.selected = Destination.STAR
    self.sidebar_expanded = True
    self._onroad_page_width = 2160.0
    self.compact_y = 0.0
    self.compact_scroll_x = 0.0
    self.notice = ""
    self.notice_until = 0.0
    self._mode = ShellMode.HOME
    self._snapshot_cache = None
    self._visual_preview_flags = frozenset()   # StarPilot's host-only visual preview
    self._visual_preview_start_ns = time.monotonic_ns()
    def bookmarked() -> bool:
      bookmark()
      return True
    self._native_favorite_actions = lambda: self.native_favorite_actions(bookmarked, personality, experimental)
    # Native publisher for taps on the projected car screen.
    self._publish_bookmark = bookmark
    self._wheel_sock = messaging.sub_sock("slcCruiseEvent", conflate=False)
    self._aol_save = None
    self._aol_save_closed = False
    self._wheel_pending = deque(maxlen=32)
    self._wheel_consumer = WheelConsumer()
    self._wheel_personality = None
    self.conditional_actions = None
    self.cruise_actions = CruiseActionPublisher()
    self.favorites_owner = FavoritesOwner(ui_state.params, self._favorite_actions, self._favorite_authority, self._favorite_render_actions,
                                         current_action=lambda key: self._resolve_favorite_actions(frozenset((key,))).get(key))
    self._favorite_snapshot = None
    self._favorite_data = None
    self._favorite_read_at = None
    self._favorite_include_options = False
    self._favorite_claimed = False
    self._projection_bookmarks = None
    self._projection_slc = None
    if getattr(ui_state, 'replay_clock', None) is None:
      try:
        self._projection_bookmarks = BookmarkReceiver()
      except OSError:
        pass  # Projection bookmarks stay unavailable without affecting the native UI.
      try:
        self._projection_slc = SlcActionReceiver()
      except OSError:
        pass  # Car-screen speed-limit taps stay unavailable without affecting the native UI.
    self.onroad_map = self.onroad_jetlink = None

  def set_driving(self, driving: bool) -> None:
    """Tandem's driving view is showing (StarPilot's onroad page would be): wheel presses and favorites act only then."""
    self._mode = ShellMode.ONROAD if driving else ShellMode.HOME

  def poll(self, now_ns: int) -> None:
    """One frame of input while the screen is on: the wheel, as StarPilot's onroad page polls it. StarPilot's own
    screen-off path (ui.py's poll_screen_off_wheel) and the Android Auto receivers run from ui.py's frame loop."""
    if self._mode == ShellMode.ONROAD and device.awake:
      self._poll_wheel(now_ns)


class TandemInput:
  """The session, StarPilot's controller runtime and Tandem's map schedule, polled once a frame from ui.py.

  Args:
    session: StarPilot's input session.
    runtime: StarPilot's ControllerRuntime (Bluetooth remotes, keyboards and gamepads), or None in replay.
    driving: Whether Tandem's driving view is showing.
  """

  def __init__(self, session: TandemStarSession, runtime: Any, driving: Callable[[], bool]):
    self.session, self.runtime, self._driving = session, runtime, driving
    self._failed = False
    self._maps = MapScheduleWatch()

  def poll(self) -> None:
    """A failure is logged once and never stops the frame."""
    try:
      self.session.set_driving(self._driving())
      self.session.poll(time.monotonic_ns())
      if self.runtime is not None:
        self.runtime.poll()
      self._poll_map_schedule()
    except Exception:
      if not self._failed:
        from openpilot.common.swaglog import cloudlog
        cloudlog.exception("Tandem: StarPilot input poll failed")
        self._failed = True

  def _poll_map_schedule(self) -> None:
    """Offline Maps › Keep up to date: a check at most once a minute, while parked on Wi-Fi, even with the screen off."""
    self._maps.poll(not ui_state.started, on_wifi(ui_state.sm))

  def close(self) -> None:
    self._maps.close()
    if self.runtime is not None:
      self.runtime.close()


_running: list[TandemInput] = []   # the input ui.py polls, for Settings' Bluetooth Remote


def controller_owner() -> Any | None:
  """StarPilot's ControllerOwner, the one the running controller runtime feeds presses to; None without it."""
  runtime = _running[0].runtime if _running else None
  return runtime.owner if runtime is not None else None


def star_input(layout: Any) -> tuple[TandemStarSession, TandemInput]:
  """StarPilot's input for Tandem's MainLayout: (session for ui.py's projection and screen-off polling, the per-frame input).

  Args:
    layout: openpilot's MainLayout with Tandem's screens.
  """
  from openpilot.selfdrive.ui.layouts.main import MainState
  from openpilot.starpilot.controllers.runtime import ControllerRuntime
  from openpilot.starpilot.galaxy.settings import LiveContextSource
  toggles: list[Any] = []
  button: list[Any] = []

  def personality(index: int) -> bool:
    if not toggles:
      from openpilot.selfdrive.ui.layouts.settings.toggles import TogglesLayout
      toggles.append(TogglesLayout())
    return bool(toggles[0].request_personality(index))

  def experimental() -> bool:
    if not button:
      from openpilot.selfdrive.ui.onroad.exp_button import ExpButton
      button.append(ExpButton(0, 0))
    return bool(button[0].request_toggle())

  session = TandemStarSession(layout._on_bookmark_clicked, personality, experimental)
  runtime = None
  if ui_state.replay_clock is None:
    # As StarPilot's own app: the runtime reads the UI collector, without advancing or closing its sockets.
    authority = LiveContextSource(ui_state.params, messages=ui_state.sm, borrowed_messages=True, evidence_wait_ms=0)
    runtime = ControllerRuntime(ui_state.params, actions=session._favorite_actions, favorites=session.favorites_owner.snapshot,
                                invoke_favorite=session.favorites_owner.invoke, authority=authority,
                                # the car and messages for vehicle-aware remote actions, as StarPilot's ui.py passes them
                                vehicle=lambda: ui_state.CP, messages=lambda: ui_state.sm,
                                speed_actions=getattr(session, "_comma_speed_actions", None),
                                keyed_actions=getattr(session, "_favorite_render_actions", None))
  inputs = TandemInput(session, runtime, lambda: layout._current_mode == MainState.ONROAD)
  _running[:] = [inputs]
  return session, inputs
