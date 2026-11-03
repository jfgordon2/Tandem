#!/usr/bin/env python3
"""Render Essentials settings and its overlays using the shared sample scenes.

  PYTHONPATH=. BIG=1 python selfdrive/ui/tandem/tools/render_settings_preview.py --out /tmp/settings-preview
  PYTHONPATH=. BIG=1 python selfdrive/ui/tandem/tools/render_settings_preview.py --page hub --page display --out /tmp/settings-preview

Page names are the PNG names from tools/render/scene_compare.py. With no --page, capture every scene.
"""
import argparse
from pathlib import Path
import runpy
import sys


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--page", action="append", help="capture this scene name (repeat for several)")
  parser.add_argument("--out", type=Path, default=Path("selfdrive/ui/tandem/tools/out/settings"))
  args = parser.parse_args(argv)
  here = Path(__file__).resolve().parent / "render"
  sys.path.insert(0, str(here))
  import snap
  args.out.mkdir(parents=True, exist_ok=True)
  snap.open_window()
  saved = set()

  def save(path):
    name = Path(path).stem
    if args.page is None or name in args.page:
      snap.save(path)
      saved.add(name)

  try:
    runpy.run_path(str(here / "scene_compare.py"))["main"](
      frame=snap.frame, save=save, out=str(args.out), tap=snap.tap, gui_app=snap.gui_app)
  finally:
    snap.rl.close_window()
  if args.page and (missing := set(args.page) - saved):
    raise SystemExit("No scene named: " + ", ".join(sorted(missing)))
  print(f"Saved {len(saved)} scenes to {args.out}")


if __name__ == "__main__":
  main()
