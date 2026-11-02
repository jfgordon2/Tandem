import pyray as rl
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.home import HomeContent, HomeState
from openpilot.selfdrive.ui.tandem.sidebar import WIDTH, Health, SidebarState, SidebarView, Status, connect_status, network_status


def main(frame, save, out, tap, gui_app):
  parked = SidebarState([network_status("Wi-Fi", 4), connect_status(Health.GOOD), Status("Temperature", "Good", Health.GOOD),
                         Status("Vehicle", "Connected", Health.GOOD),
                         Status("Maps", "Up to date", Health.GOOD)])
  onroad = SidebarState([network_status("LTE", 1), connect_status(Health.WARN), Status("Temperature", "Warm", Health.WARN),
                         Status("Vehicle", "Connected", Health.GOOD),
                         Status("Maps", "Not downloaded", Health.OFF)], onroad=True, recording_audio=True)
  for name, state in (("sidebar_home", parked), ("sidebar_onroad", onroad)):
    view = SidebarView(lambda s=state: s, lambda: None, lambda: None, lambda: None)
    home = HomeContent(lambda: HomeState(0, True, "Standard style · Matching speed limits · Auto lane change", True, "0.10.1"),
                       lambda: None, lambda: None, lambda: None)
    def render(view=view, home=home):
      draw.fill(rl.Rectangle(0, 0, 2160, 1080), T.BG)
      view.render(rl.Rectangle(0, 0, WIDTH, 1080))
      home.render(rl.Rectangle(WIDTH + T.px(16), T.px(18), 2160 - WIDTH - T.px(34), 1080 - T.px(36)))
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")

  # The parked screen's forecast strip (design/homeweather.html, homeweatherdry.html), with the mocks' sample hours.
  from openpilot.selfdrive.ui.tandem.forecast import HourTile, Outlook
  snow = [("3 PM", "cloud", 34), ("4 PM", "cloud", 33), ("5 PM", "cloud", 32), ("6 PM", "snow", 31), ("7 PM", "snow", 30),
          ("8 PM", "snow", 30), ("9 PM", "cloud", 29), ("10 PM", "cloud", 28), ("11 PM", "moon", 27), ("12 AM", "moon", 26),
          ("1 AM", "moon", 25), ("2 AM", "moon", 25)]
  sunny = [("3 PM", "sun", 68), ("4 PM", "sun", 69), ("5 PM", "partly", 67), ("6 PM", "sun", 65), ("7 PM", "sun", 61),
           ("8 PM", "moon", 58), ("9 PM", "moon", 56), ("10 PM", "cloud", 55), ("11 PM", "moon", 53), ("12 AM", "moon", 52),
           ("1 AM", "moon", 51), ("2 AM", "moon", 50)]
  outlooks = {
    "homeweather": Outlook("Light snow from 5:45 to 8:30 PM", "snow", True, "2:10 PM",
                           [HourTile(t, i, temp, i == "snow") for t, i, temp in snow]),
    "homeweatherdry": Outlook("Mostly sunny", "sun", False, "2:10 PM", [HourTile(t, i, temp, False) for t, i, temp in sunny]),
  }
  for name, look in outlooks.items():
    view = SidebarView(lambda: parked, lambda: None, lambda: None, lambda: None)
    home = HomeContent(lambda: HomeState(0, True, "Standard style · Matching speed limits · Nudge to change lanes", True, "0.10.1"),
                       lambda: None, lambda: None, lambda: None, forecast=lambda look=look: look)
    def render(view=view, home=home):
      draw.fill(rl.Rectangle(0, 0, 2160, 1080), T.BG)
      view.render(rl.Rectangle(0, 0, WIDTH, 1080))
      home.render(rl.Rectangle(WIDTH + T.px(16), T.px(18), 2160 - WIDTH - T.px(34), 1080 - T.px(36)))
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
