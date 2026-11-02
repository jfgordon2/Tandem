"""First-run setup: three questions (driving style, speed limits, lane changes), or Use defaults.

It runs once, after upstream's onboarding (terms and training). Either way out applies the Essentials defaults first,
then the answers, so everything the questions don't cover starts from a good default too.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import SETUP_CARDS, Button, ButtonStyle, ChoiceCards
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

MARKER = ".tandem_setup_done"   # beside the params folder, so no new param key (upstream's registry stays untouched)


@dataclass(frozen=True)
class Question:
  name: str
  title: str
  options: list[tuple[str, str]]
  default: int


QUESTIONS = [
  Question(N_("driving style"), N_("How should your car drive?"), [
    (N_("Relaxed"), N_("Longer following gap, gentle starts and early, soft braking.")),
    (N_("Standard · recommended"), N_("Keeps pace with traffic. A good fit for most drivers and roads.")),
    (N_("Sport"), N_("Shorter gap, quicker acceleration and later braking.")),
  ], 1),
  Question(N_("speed limits"), N_("What should it do with speed limits?"), [
    (N_("Off"), N_("Speed limits aren't shown or used.")),
    (N_("Show"), N_("Shows the limit next to your speed. You set the speed.")),
    (N_("Match · recommended"), N_("Sets cruise to the limit plus 3. Asks before speeding up.")),
  ], 2),
  Question(N_("lane changes"), N_("How should lane changes start?"), [
    (N_("Nudge · recommended"), N_("Signal, then nudge the wheel toward the lane.")),
    (N_("Auto"), N_("Signal and the car changes lanes when it's clear.")),
  ], 0),
]


class Setup:
  def __init__(self, store: SettingsStore, done: Callable[[], None], boot_logos=None):
    """boot_logos makes the source that installs Tandem's boot logo (the device's; none in tests)."""
    self._store = store
    self._done = done
    self._boot_logos = boot_logos
    self.step = 0
    self.answers = [q.default for q in QUESTIONS]

  @property
  def question(self) -> Question:
    return QUESTIONS[self.step]

  def pick(self, index: int) -> None:
    self.answers[self.step] = index

  def back(self) -> None:
    self.step = max(0, self.step - 1)

  def next(self) -> None:
    if self.step < len(QUESTIONS) - 1:
      self.step += 1
    else:
      self.finish(use_answers=True)

  def finish(self, use_answers: bool) -> None:
    from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
    from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
    with self._store.batch():
      apply_essentials(self._store, self._boot_logos)
      if use_answers:
        speed = SpeedSteering(self._store)
        speed.set_style(self.answers[0])
        speed.set_speed_limits(self.answers[1])
        speed.set_lane_changes(self.answers[2])
    self._done()


class SetupWindow(Component):
  grow_touch_target = False

  def __init__(self, setup: Setup):
    super().__init__()
    self._setup = setup
    self._cards = [self._child(ChoiceCards(q.options, lambda i=i: setup.answers[i], setup.pick, columns=3, large=SETUP_CARDS))
                   for i, q in enumerate(QUESTIONS)]
    self._defaults = self._child(Button(N_("Use defaults"), lambda: setup.finish(use_answers=False), ButtonStyle.GHOST))
    self._back = self._child(Button(N_("Back"), setup.back, ButtonStyle.SECONDARY))
    self._back.set_visible(lambda: setup.step > 0)
    self._next = self._child(Button(lambda: N_("Next") if setup.step < len(QUESTIONS) - 1 else N_("Start driving"), setup.next,
                                    ButtonStyle.PRIMARY, weight=T.FONT_EXTRABOLD))

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    s = self._setup
    body = inset(rect, x=T.px(28), y=T.px(24))
    header, cards, footer = column(body, [T.px(24) + T.px(6) + draw.line_height(T.font_px(34)), FILL, T.px(64)], T.px(18))
    cap, title = column(header, [T.px(24), FILL], T.px(6))
    draw.caption(cap, t_("STEP {} OF {}", s.step + 1, len(QUESTIONS)), T.ACCENT_TEXT)
    draw.text(title, s.question.title, T.font_px(34), T.TEXT, T.FONT_EXTRABOLD)
    for i in range(len(QUESTIONS)):   # progress dots, top right
      dot = rl.Rectangle(header.x + header.width - (len(QUESTIONS) - i) * T.px(42) + T.px(8), header.y + T.px(8), T.px(34), T.px(8))
      draw.fill(dot, T.ACCENT if i <= s.step else T.TRACK, T.px(4))

    card = self._cards[s.step]
    card.render(cards)
    remaining = [q.name for q in QUESTIONS[s.step + 1:]]
    hint = N_("You can change all of these later in Settings › Driving.")
    note = hint if not remaining else t_("Next: {}. You can change all of these later.", translate(N_(", then ")).join(translate(r) for r in remaining))
    widths = [self._defaults.preferred_size(footer.width)[0], T.px(140) if s.step > 0 else 0, T.px(200)]
    text, defaults, back, nxt = row(footer, [FILL, *widths], T.px(14))
    draw.text(text, note, T.font_px(16), T.TEXT_TERTIARY)
    self._defaults.render(defaults)
    if s.step > 0:
      self._back.render(back)
    self._next.render(nxt)


def setup_done_marker() -> Path:
  from openpilot.common.params import Params
  return Path(Params().get_param_path()).parent / MARKER


def maybe_show_setup() -> bool:
  """Push setup once nothing else (onboarding, a dialog) is on top of the main layout.

  Returns True once handled (shown now, or done before); False means try again later.
  """
  from openpilot.system.ui.lib.application import gui_app
  if len(getattr(gui_app, "_nav_stack", [])) != 1:
    return False
  marker = setup_done_marker()
  if marker.exists():
    return True

  def done() -> None:
    marker.touch()
    gui_app.pop_widget()

  from openpilot.selfdrive.ui.tandem.settings.display import UpstreamBootLogos
  gui_app.push_widget(SetupWindow(Setup(SettingsStore(), done, UpstreamBootLogos)))
  return True
