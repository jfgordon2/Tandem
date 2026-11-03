"""Voice typing for the keyboard's mic key (design/voicelistening.html, voicetranscribing.html, voicedownload.html).

VoiceTyping runs speech.py as its own process and follows what it prints; VoicePanel draws that in place of the keys.
The words land in the field for editing; nothing is sent or searched until the person presses the action key.

Voice typing works parked and driving. Its native runner uses the CPU; driving, it uses micd's audio, two threads and cores 0-3
(speech.driving_limits). The diagnostic tinygrad fallback uses the GPU, so it stays parked-only.
"""
from __future__ import annotations

import collections
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ProgressBar
from openpilot.selfdrive.ui.tandem.layout import Align, column, inset, place
from openpilot.selfdrive.ui.tandem.i18n import N_

WORKER = Path(__file__).resolve().parent / "speech.py"
BARS = 22                                    # the level meter's bars, newest on the right
MESSAGE_S = 3.0                              # how long a "didn't catch that" stays before the keys come back
UNSEEN_S = 3.0                               # the panel went off screen (the page closed): stop listening

ERRORS = {
  "no_speech": N_("Didn't catch that. Tap the mic to try again."),
  "no_mic": N_("The microphone isn't available right now."),
  "no_audio_driving": N_("Voice typing can't hear the microphone while driving right now. Try again parked."),
  "download": N_("Couldn't download the speech model. Check the connection and try again."),
  "failed": N_("Voice typing didn't work this time. Try again or type it."),
}


def driving() -> bool:
  try:
    from openpilot.selfdrive.ui.ui_state import ui_state
  except ImportError:                        # the headless renders and tests, without cereal: parked
    return False
  return bool(getattr(ui_state, "started", False))


def available() -> bool:
  """Parked or driving with the native CPU runner; the tinygrad fallback uses the GPU the driving model needs, so it
  stays parked-only."""
  from openpilot.selfdrive.ui.tandem import speech
  return speech.native_backend() is not None or not driving()


class VoiceTyping:
  """One go at voice typing: start() runs the worker; update() each frame reads where it is.

  state is "idle", "download", "listening", "transcribing" or "message" (an error shown for a moment). on_text gets the
  words when they arrive.
  """

  def __init__(self, on_text: Callable[[str], None], command: list[str] | None = None, style: str = "text"):
    """style "address" writes the words as an address: digits for a house number, "1st Street" (speech.address_text)."""
    self._on_text = on_text
    self._command = command or [sys.executable, str(WORKER), "--style", style]
    self._process: subprocess.Popen | None = None
    self._lines: queue.Queue = queue.Queue()
    self.state = "idle"
    self.progress = 0.0
    self.levels: collections.deque[float] = collections.deque([0.0] * BARS, maxlen=BARS)
    self.message = ""
    self._message_until = 0.0
    self._seen = 0.0

  @property
  def active(self) -> bool:
    return self.state != "idle"

  def start(self) -> None:
    self.cancel()
    from openpilot.selfdrive.ui.tandem import speech
    self.state = "listening" if speech.model_ready() else "download"
    self.progress, self.message = 0.0, ""
    self.levels.extend([0.0] * BARS)
    env = dict(os.environ)
    if driving():
      env["TANDEM_SPEECH_DRIVING"] = "1"     # micd's audio, two threads, cores 0-3 (speech.driving_limits)
    if os.path.isfile("/TICI"):
      env.setdefault("DEV", N_("QCOM"))          # the tinygrad fallback's GPU, free while parked (it's parked-only)
    try:
      log = speech.model_dir() / "worker.log"   # the last run's errors, for a bug report
      log.parent.mkdir(parents=True, exist_ok=True)
      with open(log, "w") as err:
        # A fresh interpreter drops priority before exec. Python preexec_fn can deadlock a threaded UI before Popen returns.
        command = [sys.executable, str(WORKER), "--exec", *self._command]
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1, env=env)
    except OSError:
      self._show("failed")
      return
    lines = self._lines = queue.Queue()      # a fresh queue, so a cancelled worker's last lines can't land here
    self._seen = time.monotonic()
    threading.Thread(target=self._read, args=(self._process, lines), daemon=True).start()
    threading.Thread(target=self._watch, args=(self._process,), daemon=True).start()

  @staticmethod
  def _read(process: subprocess.Popen, lines: queue.Queue) -> None:
    for line in process.stdout:
      lines.put(line)
    lines.put(None)                          # the worker ended

  def _watch(self, process: subprocess.Popen) -> None:
    """Ends the worker if nothing draws the panel any more, so the mic never stays open behind a closed page."""
    while process.poll() is None:
      if time.monotonic() - self._seen > UNSEEN_S and process is self._process:
        self.cancel()
        return
      time.sleep(0.25)

  def stop(self) -> None:
    """Done talking: transcribe what's been heard."""
    if self.state == "listening" and self._process and self._process.stdin:
      try:
        self._process.stdin.write("stop\n")
        self._process.stdin.flush()
      except (BrokenPipeError, OSError, ValueError):
        pass
      self.state = "transcribing"

  def cancel(self) -> None:
    """Type instead: end the worker and drop whatever it would have written."""
    if self._process and self._process.poll() is None:
      self._process.kill()
    self._process = None
    self.state, self.message = "idle", ""

  def update(self) -> None:
    self._seen = time.monotonic()
    if self.state == "message" and time.monotonic() >= self._message_until:
      self.state, self.message = "idle", ""
    while True:
      try:
        line = self._lines.get_nowait()
      except queue.Empty:
        return
      if line is None:
        if self.state in ("download", "listening", "transcribing"):
          self._show("failed")               # it ended without words or a reason
        self._process = None
        return
      self._handle(line)

  def _handle(self, line: str) -> None:
    try:
      message = json.loads(line)
    except ValueError:
      return
    if "level" in message:
      self.levels.append(float(message["level"]))
    elif "state" in message:
      self.state = message["state"]
      self.progress = float(message.get("progress", self.progress))
    elif "text" in message:
      self.state = "idle"
      self._on_text(message["text"])
    elif "error" in message:
      self._show(message["error"])

  def _show(self, error: str) -> None:
    self.state, self.message = "message", ERRORS.get(error, ERRORS["failed"])
    self._message_until = time.monotonic() + MESSAGE_S


def _keyboard_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.icon(rect, "keyboard", color, T.px(22))


class VoicePanel(Component):
  """The key panel while voice typing: the mic (tap to stop), what's happening, the level meter or download progress,
  and Type instead."""

  def __init__(self, session: VoiceTyping, hint: str = N_("Speak now. Tap the mic when you're done.")):
    super().__init__()
    self.session = session
    self.hint = hint
    self._type_instead = Button(N_("Type instead"), session.cancel, ButtonStyle.SECONDARY, glyph=_keyboard_glyph, height=T.px(56),
                                font_size=T.font_px(17), radius=T.px(14), weight=T.FONT_BOLD, padding=T.px(22))
    self._progress = ProgressBar(lambda: session.progress)
    self._mic_rect = rl.Rectangle(0, 0, 0, 0)

  def words(self) -> tuple[str, str]:
    s = self.session
    if s.state == "download":
      return N_("Getting voice typing ready"), N_("One-time setup for the speech model and voice engine. Everything stays on this device.")
    if s.state == "transcribing":
      return N_("Writing it down"), N_("This takes a few seconds. You can edit the words after.")
    if s.state == "message":
      return N_("Voice typing"), s.message
    return N_("Listening"), self.hint

  def _render(self, rect: rl.Rectangle):
    s = self.session
    s.update()
    draw.fill(rect, T._hex("13161A"))
    draw.hline(rect.x, rect.y, rect.width, T._hex("1F242B"))
    body = inset(rect, left=T.px(24), right=T.px(24), top=T.px(22), bottom=T.px(20))
    title, sub = self.words()
    title_h, sub_h = draw.line_height(T.font_px(26)), draw.line_height(T.font_px(16))
    gap = T.px(16)
    stack = place(body, body.width, T.px(132) + gap + title_h + T.px(6) + sub_h + gap + T.px(80))
    circle, _, words, _, extra = column(stack, [T.px(132), gap, title_h + T.px(6) + sub_h, gap, T.px(80)])
    self._draw_mic(circle)
    draw.text(rl.Rectangle(words.x, words.y, words.width, title_h), title, T.font_px(26), T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)
    draw.text(rl.Rectangle(words.x, words.y + title_h + T.px(6), words.width, sub_h), draw.fit(sub, T.font_px(16), T.FONT, words.width),
              T.font_px(16), T.TEXT_TERTIARY, T.FONT, Align.CENTER)
    if s.state == "listening":
      self._draw_levels(extra)
    elif s.state == "download":
      bar = place(extra, T.px(420), extra.height)
      track, label = column(bar, [T.px(10), T.px(8), draw.line_height(T.font_px(15))])[::2]
      self._progress.render(track)
      draw.text(label, f"{round(s.progress * 100)}%", T.font_px(15), T.TEXT_TERTIARY, T.FONT, Align.CENTER)
    w = self._type_instead.preferred_size(rect.width)[0]
    self._type_instead.render(rl.Rectangle(body.x, body.y + body.height - T.px(56), w, T.px(56)))

  def _draw_mic(self, area: rl.Rectangle) -> None:
    s = self.session
    box = place(area, T.px(132), T.px(132))
    self._mic_rect = box
    center, r = rl.Vector2(box.x + box.width / 2, box.y + box.height / 2), box.width / 2
    if s.state == "listening":
      draw.disc(center, r + T.px(28), draw.alpha(T.ACCENT, 0.08))
      draw.disc(center, r + T.px(14), draw.alpha(T.ACCENT, 0.18))
      draw.disc(center, r, T.ACCENT)
      draw.icon(box, "mic", T.ACCENT_INK, T.px(56))
      return
    draw.disc(center, r, T.CONTROL_NAV)
    if s.state == "transcribing":
      spin = (time.monotonic() * 360) % 360
      draw.arc(center, T.px(26), T.px(6), 0, 360, T.TRACK)
      draw.arc(center, T.px(26), T.px(6), spin - 90, spin, T.ACCENT)
    else:
      draw.icon(box, "mic", T.ACCENT_TEXT, T.px(56))

  def _draw_levels(self, area: rl.Rectangle) -> None:
    w, gap = T.px(8), T.px(6)
    meter = place(area, BARS * w + (BARS - 1) * gap, area.height)
    for i, value in enumerate(self.session.levels):
      h = max(T.px(10), value * area.height)
      x = meter.x + i * (w + gap)
      bar = rl.Rectangle(x, meter.y + (meter.height - h) / 2, w, h)
      draw.fill(bar, draw.alpha(T.ACCENT, 0.55 + 0.45 * value), w / 2)

  def _handle_mouse_release(self, mouse_pos) -> None:
    super()._handle_mouse_release(mouse_pos)
    if self.session.state == "listening" and rl.check_collision_point_circle(
        mouse_pos, rl.Vector2(self._mic_rect.x + self._mic_rect.width / 2, self._mic_rect.y + self._mic_rect.height / 2),
        self._mic_rect.width / 2 + T.px(14)):
      self.session.stop()
    elif self.session.state == "message":
      self.session.cancel()                  # tapping the message brings the keys back sooner

