#!/usr/bin/env python3
"""Draw the bundled "Bouncing Ball" turn-signal frames.

A white ping-pong ball drops in from the top of the screen at the inner edge and
bounces along towards the turn: rigid (no squash), light and lively. It touches
down four times, each bounce keeping 75% of its speed (~56% of its height), and
after the fourth touchdown it bounces off the far edge of the screen while still
rising; the next ball then drops in. It uses the renderer's "traditional" style, which
moves the frames across the screen (and mirrors them for right turns), so each
frame only has to place the ball vertically.

The canvas is the full screen height (1080) so the ball can fall from the very
top, and narrow (64) because the renderer supplies the sideways motion.
40 frames at 75 ms: one unhurried 3 s pass (about 11 MB of textures). A ground
shadow tightens as the ball lands. The blind-spot image is a traffic-red ball
rolling along the ground.

Dev-only dependency: pip install cairosvg
Usage: python selfdrive/ui/tandem/tools/make_bouncing_ball_signals.py [output_dir]
"""
import sys
from pathlib import Path


W, H = 64, 1080
FRAMES = 40
FRAME_MS = 75
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "assets/signal_packs/bouncing_ball/signals"

RADIUS = 26
GROUND = H - 14                 # where the ball's bottom touches down
REST_Y = GROUND - RADIUS        # centre height when touching the ground
START_Y = -RADIUS * 0.4         # a sliver showing at the very top of the screen
TOUCHDOWNS = 4                  # the drop's impact plus three bounce landings
RESTITUTION = 0.75              # ping-pong: each bounce keeps 75% of its speed
EXIT_FRACTION = 0.4             # how far into the final bounce it is when it leaves the screen (still rising)
# Drop time chosen so the ball reaches the far edge (last frame) EXIT_FRACTION into the
# bounce after its last touchdown. Bounce k lasts 2*e^k*t, so:
# t * (1 + 2*(e + ... + e^(N-1)) + 2*EXIT_FRACTION*e^N) = FRAMES - 1
FIRST_CONTACT = (FRAMES - 1) / (1 + 2 * sum(RESTITUTION ** k for k in range(1, TOUCHDOWNS))
                                + 2 * EXIT_FRACTION * RESTITUTION ** TOUCHDOWNS)
DROP = REST_Y - START_Y
GRAVITY = 2 * DROP / FIRST_CONTACT ** 2   # px / frame^2

WHITE = ("#FFFFFF", "#F1F3F4", "#C9CED2")      # highlight, body, rim (matte)
RED = ("#FF9AA1", "#E0303E", "#9E1823")         # TRAFFIC_COLOR family


def bounces():
  """(take-off time, take-off speed, flight time) for each bounce in a pass."""
  out, start, speed = [], FIRST_CONTACT, GRAVITY * FIRST_CONTACT * RESTITUTION
  for _ in range(TOUCHDOWNS):  # the last one carries the ball off screen
    flight = 2 * speed / GRAVITY
    out.append((start, speed, flight))
    start, speed = start + flight, speed * RESTITUTION
  return out


def contacts():
  """Touchdown times (in frames): the drop, then the landings before the final bounce."""
  return [FIRST_CONTACT] + [start + flight for start, _, flight in bounces()[:-1]]


def ball_height(frame):
  """Height of the ball's centre above its touching-the-ground position."""
  # A rigid ball must visibly touch down: the frame nearest each impact shows it on the ground.
  if any(abs(frame - c) < 0.5 for c in contacts()):
    return 0.0
  if frame <= FIRST_CONTACT:
    return DROP - 0.5 * GRAVITY * frame ** 2
  for start, speed, flight in bounces():
    if start <= frame <= start + flight:
      dt = frame - start
      return max(0.0, speed * dt - 0.5 * GRAVITY * dt ** 2)
  return 0.0


def ball(cx, cy, palette, uid):
  highlight, body, rim = palette
  return (f'<defs><radialGradient id="b{uid}" cx="38%" cy="32%" r="75%">'
          + f'<stop offset="0" stop-color="{highlight}"/><stop offset="0.6" stop-color="{body}"/>'
          + f'<stop offset="1" stop-color="{rim}"/></radialGradient></defs>'
          + f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{RADIUS}" fill="url(#b{uid})"/>')


def shadow(cx, height):
  closeness = max(0.0, 1 - height / (DROP * 0.55))
  width = RADIUS * (0.7 + 0.5 * closeness)
  opacity = 0.08 + 0.32 * closeness ** 2
  return (f'<defs><radialGradient id="s"><stop offset="0" stop-color="#000" stop-opacity="{opacity:.2f}"/>'
          + '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>'
          + f'<ellipse cx="{cx}" cy="{GROUND + 3}" rx="{width:.1f}" ry="{width * 0.22:.1f}" fill="url(#s)"/>')


def svg(body):
  return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{body}</svg>'


def frame_svg(frame):
  height = ball_height(frame)
  return svg(shadow(W / 2, height) + ball(W / 2, REST_Y - height, WHITE, frame))


def blindspot_svg():
  glow = ('<defs><radialGradient id="g"><stop offset="0" stop-color="#FF4552" stop-opacity="0.35"/>'
          + '<stop offset="1" stop-color="#FF4552" stop-opacity="0"/></radialGradient></defs>'
          + f'<circle cx="{W / 2}" cy="{REST_Y}" r="{RADIUS * 1.5}" fill="url(#g)"/>')
  return svg(shadow(W / 2, 0) + glow + ball(W / 2, REST_Y, RED, "alert"))


def main():
  import cairosvg
  out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
  out.mkdir(parents=True, exist_ok=True)
  for frame in range(FRAMES):
    cairosvg.svg2png(bytestring=frame_svg(frame).encode(), write_to=str(out / f"turn_signal_{frame + 1}.png"))
  cairosvg.svg2png(bytestring=blindspot_svg().encode(), write_to=str(out / "turn_signal_blindspot.png"))
  (out / f"traditional_{FRAME_MS}").touch()


if __name__ == "__main__":
  main()
