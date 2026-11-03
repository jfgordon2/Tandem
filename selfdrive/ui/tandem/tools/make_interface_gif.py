#!/usr/bin/env python3
"""Build the README's interface tour from built-screen PNGs, keeping recorder test screens out.

Render the scenes using tools/render/snap.py, then run:
  python3 selfdrive/ui/tandem/tools/make_interface_gif.py --renders selfdrive/ui/tandem/tools/out/renders

Needs Pillow. The explicit sequence is the published tour; extra render outputs never enter it automatically.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
TANDEM = ROOT / "selfdrive/ui/tandem"

# (render stem, caption, hold time in milliseconds). Only implemented English screens, no test variants.
SLIDES = (
  ("onroad_hero", "The essentials while driving", 3000),
  ("homeweather", "Home and the weather ahead", 2800),
  ("destinations", "Favorites and recent places", 2200),
  ("navsearch", "Find a destination", 2200),
  ("voicelistening", "Voice typing on the device", 2400),
  ("routepreview", "Preview the route", 2400),
  ("onroad_nav", "Turn-by-turn directions", 2800),
  ("onroad_helpsteer", "Help steer at the steering limit", 2600),
  ("onroaddev", "Developer View", 2800),
  ("hub", "Driving settings", 2400),
  ("search", "Find a setting", 2200),
  ("driving", "Driving style and speed limits", 2800),
  ("drivingweather", "Adjust for the weather", 2200),
  ("display", "Choose what stays in view", 2400),
  ("pathstylepicker", "Path styles", 2000),
  ("signalpicker", "Turn signals and a little whimsy", 2400),
  ("alerts", "Alerts and chimes", 2400),
  ("volumeeditor", "Set the volume", 2000),
  ("model", "Driving models", 2400),
  ("vehicle", "Controls for your car", 2400),
  ("mapdata", "Offline maps", 2200),
  ("tuner", "Tuner Mode", 2600),
  ("devicetab", "Your device", 2200),
  ("connections", "Wi-Fi and connections", 2200),
  ("connectionsremote", "Steering wheel remotes", 2400),
  ("softwaretab", "Updates and software", 2600),
)


def make_frame(source: Path, title: str, index: int, width: int) -> Image.Image:
  height = width // 2
  footer = round(width * 0.045)
  with Image.open(source) as screenshot:
    if screenshot.width != screenshot.height * 2:
      raise ValueError(f"Expected a 2:1 built-screen capture: {source}")
    screen = screenshot.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
  frame = Image.new("RGB", (width, height + footer), "#000000")
  frame.paste(screen, (0, 0))
  draw = ImageDraw.Draw(frame)
  fonts = ROOT / "selfdrive/assets/fonts"
  title_font = ImageFont.truetype(str(fonts / "Figtree-Medium.ttf"), round(width * 0.017))
  detail_font = ImageFont.truetype(str(fonts / "Figtree-Regular.ttf"), round(width * 0.012))
  pad, middle = round(width * 0.016), height + footer // 2
  draw.line((0, height, width, height), fill="#262A31")
  draw.text((pad, middle), "TANDEM", font=detail_font, fill="#8BC9FF", anchor="lm")
  draw.text((round(width * 0.105), middle), title, font=title_font, fill="#F2F5F9", anchor="lm")
  draw.text((width - pad, middle), f"{index + 1:02d} / {len(SLIDES)}", font=detail_font, fill="#AEB6C2", anchor="rm")
  return frame


def build(renders: Path, destination: Path, width: int) -> None:
  if width < 640 or width % 2:
    raise ValueError("Use an even width of at least 640 pixels")
  if any("can" in name.lower() or "recorder" in name.lower() for name, _, _ in SLIDES):
    raise ValueError("Recorder test screens must not appear in the public tour")
  missing = [name for name, _, _ in SLIDES if not (renders / f"{name}.png").is_file()]
  if missing:
    raise FileNotFoundError("Render these scenes first: " + ", ".join(missing))

  frames = [make_frame(renders / f"{name}.png", title, index, width) for index, (name, title, _) in enumerate(SLIDES)]
  # Local palettes retain small colored details such as warnings and the illustrated signal previews.
  # No dithering: text and flat surfaces stay crisp.
  encoded = [frame.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for frame in frames]
  durations = [duration for _, _, duration in SLIDES]
  destination.parent.mkdir(parents=True, exist_ok=True)
  encoded[0].save(destination, save_all=True, append_images=encoded[1:], duration=durations, loop=0, disposal=1, optimize=True)

  # Decode the delivered file rather than trusting the encoder inputs.
  with Image.open(destination) as result:
    if result.n_frames != len(SLIDES) or result.info.get("loop") != 0:
      raise ValueError("The GIF did not retain every slide or its loop setting")
    for index, duration in enumerate(durations):
      result.seek(index)
      result.load()
      if result.info.get("duration") != duration:
        raise ValueError(f"Unexpected hold time for slide {index + 1}")
  print(f"{destination}: {len(frames)} slides, {sum(durations) / 1000:g} seconds, " +
        f"{encoded[0].width} × {encoded[0].height}, {destination.stat().st_size / 1024**2:.2f} MiB")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--renders", type=Path, default=TANDEM / "tools/out/renders")
  parser.add_argument("--out", type=Path, default=TANDEM / "assets/screenshots/interface-tour.gif")
  parser.add_argument("--width", type=int, default=1200)
  args = parser.parse_args()
  build(args.renders, args.out, args.width)


if __name__ == "__main__":
  main()
