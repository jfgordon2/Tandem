"""Render every implemented screen with sample data, named after its mock."""
import runpy
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
import pyray as rl
from test_settings import FakeCache, FakeDevice
from openpilot.selfdrive.ui.tandem.settings import window as W
from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.tests.fakes import (FakeBluetooth, FakeBootLogos, FakeCars, FakeData, FakeMaps, FakeModels, FakeUpdates,
                                                       FakeWheel, FakeWifi)

VALUES = {
  "NudgelessLaneChange": True, "SpeedLimitController": True, "ShowSpeedLimits": True, "SLCConfirmation": True, "Offset1": 3.0,
  "WeatherPresets": True, "CarModelName": "RAV4 Hybrid 2019-21", "CarMake": "Toyota", "OpenpilotEnabledToggle": True,
  "IsLdwEnabled": True, "ConditionalExperimental": True, "CurveSpeedController": True, "AlwaysOnLateral": True,
  "FavoriteDestinations": [{"name": "12 Elm St", "is_home": True}, {"name": "Gym"}], "ClearNavOnOffroad": True,
  "AlertVolumeControl": True, "EngageVolume": 60, "DisengageVolume": 60, "PromptVolume": 70, "RefuseVolume": 70,
  "BelowSteerSpeedVolume": 70, "PromptDistractedVolume": 80, "WarningSoftVolume": 80, "WarningImmediateVolume": 100,
  "GreenLightAlert": True, "LeadDepartingAlert": True, "SignalAnimation": "frog", "CustomThemes": True,
  "AdvancedCustomUI": True, "HideChangingLanesBanner": True, "HideTurningBanner": True, "HideDistanceProfileBanner": True,
  "BlindSpotPath": True, "PathWidth": 6.1, "CameraView": 2, "BootLogo": "starpilot", "NavigationUI": True,
  "StartupMessageTop": "Be ready to take over at any time", "StartupMessageBottom": "Always keep hands on wheel and eyes on road",
  "AutomaticallyDownloadModels": True, "LockDoors": True, "LKASButtonControl": 9, "DistanceButtonControl": 1,
  "SteerDelay": 0.18, "SteerDelayStock": 0.18, "UseAutoSteerDelay": True, "SteerFriction": 0.14, "SteerFrictionStock": 0.1,
  "SteerLatAccel": 2.4, "SteerLatAccelStock": 2.4, "SteerKP": 1.0, "SteerKPStock": 1.0, "NNFF": True, "NNFFLite": True,
  "LongitudinalPersonality": 1, "AccelerationProfile": 0, "DecelerationProfile": 1, "MaxDesiredAcceleration": 3.0,
  "StartAccel": 0.8, "StartAccelStock": 0.8, "StopAccel": -0.5, "StopAccelStock": -0.5, "StoppingDecelRate": 0.8,
  "StoppingDecelRateStock": 0.8, "LongitudinalActuatorDelay": 0.15, "LongitudinalActuatorDelayStock": 0.15,
  "RelaxedFollow": 1.6, "StandardFollow": 1.45, "AggressiveFollow": 1.25, "TrafficFollow": 0.75, "LeadDetectionThreshold": 35,
  "ForceStops": True, "CustomCruise": 1.0, "TuningLevel": 3, "DeveloperSidebar": True, "DeveloperUI": True, "FPSCounter": True,
  "ShowCPU": True, "ShowGPU": False, "NumericalTemp": True, "ShowMemoryUsage": True, "AdjacentPathMetrics": True,
  "SpeedLimitSources": True, "ScreenBrightness": 101, "StandbyMode": True, "DisableOnroadUploads": True, "GsmMetered": True,
  "UpdaterState": "idle", "UpdaterCurrentDescription": "0.10.1 / release / Oct 28", "AutomaticUpdates": True,
  "UpdaterTargetBranch": "release", "PreferredSchedule": 1, "MinimumLaneChangeSpeed": 20.0,
}


def main(frame, save, out, tap, gui_app):
  W.UpstreamDevice = lambda: FakeDevice()
  cache = FakeCache(dict(VALUES))
  models, wheel, maps = FakeModels(), FakeWheel(), FakeMaps()
  win = W.SettingsWindow(store=SettingsStore(cache, lambda: None), live=FakeLive(), model_source=lambda: models, car_catalog=FakeCars,
                         device_data=FakeData, device=FakeDevice, wifi=FakeWifi, wheel=lambda: wheel, bluetooth=FakeBluetooth,
                         updates=FakeUpdates, maps_source=lambda: maps, boot_logos=FakeBootLogos)
  win.show_event()
  rect = rl.Rectangle(0, 0, 2160, 1080)
  draw = lambda: win.render(rect)  # noqa: E731

  def shot(name, n=4):
    for _ in range(n):
      frame(draw)
    save(f"{out}/{name}.png")

  def click(widget):
    r = widget.rect
    down, up = tap(r.x + r.width / 2, r.y + r.height / 2)
    frame(draw, down)
    frame(draw, up)

  def tile(i):
    win._unwind(0) if win.tab == 0 else win.select_tab(0)
    win._unwind(0)
    shot("_", 2)
    click(win.top._grid._tiles[i])
    shot("_", 2)

  shot("hub")
  win.top._header._trailing._click_callback()
  win.overlay.type("gas")
  shot("search", 6)
  win.overlay._show_all()
  shot("searchresults", 4)
  win.dismiss()
  tile(0)
  for i, name in enumerate(["driving", "drivingvehicle", "drivingweather", "drivingnav"]):
    win.top.select(i)
    shot(name)
  win.top._sidebar._footer[0]._click_callback()
  for i, name in enumerate(["tuner", "tunergas", "tunerfollowing", "tunerbundles"]):
    win.top.select(i)
    shot(name)
  r = win.top.current._tabs.rect        # tap Lead Insights: the tab changes while the panel draws (it once crashed here)
  down, up = tap(r.x + r.width * 0.75, r.y + r.height / 2)
  frame(draw, down)
  frame(draw, up)
  shot("tunerbundles_lead")
  win.top.current._select(0)
  win.top.current._choose._click_callback()
  shot("barmetrics", 30)
  win.dismiss()
  win.top._sidebar._footer[0]._click_callback()
  shot("tunerreset", 30)
  win.dismiss()
  win.top.select(1)
  shot("_", 2)
  win.top.current.items[3]._control._click_callback()
  shot("valueeditor", 30)
  win.dismiss()
  tile(5)
  shot("assistance")
  tile(1)
  for i, name in enumerate(["display", "displaytheme", "displaymap"]):
    win.top.select(i)
    shot(name)
  win.top.select(1)
  shot("_", 2)
  win.top.current.items[2]._control._click_callback()
  shot("bootlogopicker", 30)
  win.dismiss()
  win.top.select(1)
  shot("_", 2)
  win.top.current.items[0]._control._click_callback()
  shot("pathstylepicker", 30)
  win.dismiss()
  win.top.select(1)
  shot("_", 2)
  win.top.current.items[1]._control._click_callback()
  shot("signalpicker", 30)
  win.dismiss()
  win.top.select(2)
  shot("_", 2)
  win.top.current.items[2]._click_callback()
  shot("mapdata")
  win.top._page._body._items[0]._items[6]._content._click_callback()
  shot("mapregions")
  win.top._side._items[4]._click_callback()
  shot("mapdownloading")
  tile(2)
  shot("alerts")
  win.top._body._items[0]._items[2]._items[2]._click_callback()
  shot("volumeeditor", 30)
  win.dismiss()
  shot("_", 10)
  win.top._body._items[0]._items[2]._items[3]._click_callback()
  shot("volumeeditor_take", 30)
  win.dismiss()
  models.download("nlp")
  tile(3)
  shot("model")
  win.top._body._content._items[1].items[0]._trailing._click_callback()
  shot("modelcatalog")
  tile(4)
  shot("vehicle")
  win.top._body._items[0]._items[0]._items[4]._content._click_callback()
  shot("vehiclepicker", 30)
  win.dismiss()

  win.select_tab(W.Tab.DEVICE)
  for i, name in enumerate(["devicetab", "system", "systembackups", "systemstorage", "systemreport"]):
    win.top.select(i)
    shot(name)
    if name == "devicetab":
      import qrcode
      img = qrcode.QRCode(box_size=10, border=0)
      img.add_data("https://connect.comma.ai/?pair=example-token")
      img.make(fit=True)
      img.make_image(fill_color="black", back_color="white").save(f"{out}/_qr.png")
      qr_texture = rl.load_texture(f"{out}/_qr.png")
      FakeDevice.pairing_qr = lambda self, t=qr_texture: t
      win.top.current.items[0]._control._click_callback()
      shot("pairing")
      win.back()
      shot("_", 2)
      remote = [r for r in win.top.current.items if getattr(r, "_title", "") == "Remote Access"][0]
      remote._control._click_callback()
      shot("remoteaccess")
      FakeDevice.remote_access_link = lambda self: "https://galaxy.firestar.link/k3Rf9TqLm2WxVb7Z"
      gq = qrcode.QRCode(box_size=10, border=0)
      gq.add_data("https://galaxy.firestar.link/k3Rf9TqLm2WxVb7Z")
      gq.make(fit=True)
      gq.make_image(fill_color="black", back_color="white").save(f"{out}/_gqr.png")
      galaxy_texture = rl.load_texture(f"{out}/_gqr.png")
      FakeDevice.remote_access_qr = lambda self, t=galaxy_texture: t
      shot("remoteaccessqr")
      win.back()
      shot("_", 2)
    if name == "systembackups":
      win.top.current._content.items[2]._control._buttons[1]._click_callback()
      shot("confirmdialog", 30)
      win.dismiss()
  win.top.current._content._items[0]._content._items[1]._on_change(1)
  shot("systemreport")
  win.select_tab(W.Tab.CONNECTIONS)
  shot("connections")
  win.top.select(1)
  shot("connectionscellular")
  win.top.select(3)
  shot("connectionsaudio")
  win.top.select(2)
  wheel.state["last_tested"] = {"mapped": True, "slot": 4}
  shot("connectionsremote")
  wheel.state["last_tested"] = None
  win.top.current._panel._content.items[-1]._click_callback()
  shot("wheelbuttonlearn", 30)
  win.back()
  win.select_tab(W.Tab.SOFTWARE)
  shot("softwaretab")

  # The other screens have scenes of their own.
  for scene in ("scene_onroad.py", "scene_sidebar.py", "scene_setup.py", "scene_alerts.py", "scene_extras.py", "scene_dev.py",
                "scene_homealerts.py", "scene_destinations.py", "scene_keyboard.py", "scene_bundlesheet.py", "scene_camera.py",
                "scene_lead.py", "scene_mapbox.py"):
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), scene))["main"](
      frame=frame, save=save, out=out, tap=tap, gui_app=gui_app)
