"""The sidebar, parked and while driving (design/home.html and onroadmenu.html). Home isn't ported yet, so it stands alone."""
from openpilot.starpilot.ui.raylib import rl
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.sidebar import WIDTH, Health, SidebarState, SidebarView, Status, connect_status, network_status


def main(frame, save, out, tap, gui_app):
  parked = SidebarState([network_status("Wi-Fi", 4), connect_status(Health.GOOD), Status("Temperature", "Good", Health.GOOD),
                         Status("Vehicle", "Connected", Health.GOOD),
                         Status("Maps", "Ready", Health.GOOD)])
  onroad = SidebarState([network_status("LTE", 1), connect_status(Health.WARN), Status("Temperature", "Warm", Health.WARN),
                         Status("Vehicle", "Connected", Health.GOOD),
                         Status("Maps", "Not downloaded", Health.OFF)], onroad=True, recording_audio=True)
  for name, state in (("sidebar_home", parked), ("sidebar_onroad", onroad)):
    view = SidebarView(lambda s=state: s, lambda: None, lambda: None, lambda: None)

    def render(view=view):
      draw.fill(rl.Rectangle(0, 0, 2160, 1080), T.BG)
      view.render(rl.Rectangle(0, 0, WIDTH, 1080))
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
