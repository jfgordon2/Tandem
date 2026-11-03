import pyray as rl
from openpilot.selfdrive.ui.tandem import destinations as D
from openpilot.selfdrive.ui.tandem.tests.fakes import FakePlaces


def main(frame, save, out, tap, gui_app):
  places = FakePlaces()
  screen = D.DestinationsScreen(places, lambda: None, open_maps=lambda: None)
  rect = rl.Rectangle(0, 0, 2160, 1080)
  draw = lambda: screen.render(rect)  # noqa: E731

  def shot(name, n=4):
    for _ in range(n):
      frame(draw)
    save(f"{out}/{name}.png")

  shot("destinations")
  screen._go(D.SEARCH)
  screen._keys.set_text("Hy-Vee")
  # Sample branches with the same name and locality; the street distinguishes them on the existing second line.
  places.found = [
    ("Hy-Vee", "410 N Ankeny Blvd, Ankeny, IA 50023, United States"),
    ("Hy-Vee", "2510 SW State St, Ankeny, IA 50023, United States"),
    ("Hy-Vee Fast & Fresh", "410 N Ankeny Blvd, Ankeny, IA 50023, United States"),
    ("Hy-Vee Pharmacy", "2510 SW State St, Ankeny, IA 50023, United States"),
  ]
  screen._searched = "Hy-Vee"
  screen._typed = "Hy-Vee"
  shot("navsearch")
  # Voice typing's three states, set directly: no worker or microphone here.
  session = screen._keys._voice
  screen._keys.set_text("")
  session.levels.extend([0.12, 0.2, 0.3, 0.42, 0.57, 0.5, 0.72, 0.9, 0.8, 0.62, 1.0, 0.85, 0.68, 0.55, 0.75, 0.48, 0.35, 0.45, 0.28,
                         0.2, 0.15, 0.12])
  for state, name in (("listening", "voicelistening"), ("transcribing", "voicetranscribing"), ("download", "voicedownload")):
    session.state, session.progress = state, 0.42
    shot(name)
  session.state = "idle"
  screen._keys.set_text("Hy-Vee")
  screen._view = D.RESULTS
  shot("navresults")
  places.search("hardware sto")   # keep the route preview's sample place
  screen._pick_result(0)
  screen._update_state()
  shot("routepreview")
