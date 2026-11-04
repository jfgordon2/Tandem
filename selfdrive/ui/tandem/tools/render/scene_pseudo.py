"""The pseudo-language check: every screen with each marked string drawn as "[Text ~~~]" (i18n.pseudo).

  PYTHONPATH=$PWD BIG=1 xvfb-run -a python3 selfdrive/ui/tandem/tools/render/snap.py \\
    selfdrive/ui/tandem/tools/render/scene_pseudo.py selfdrive/ui/tandem/tools/out/pseudo

Writes the renders there, and missed.txt: drawn text with letters but no brackets, so not marked with N_(), t_() or tn_()
(or not in tandem.pot: run tools/translations.py update). Names and values from the sample data show up too; the
list is for reading, not a test. In the renders, text cut off with "…" or overflowing its box is where a longer
language won't fit.
"""
import os
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = {"RAV4 Hybrid 2019-21", "Toyota", "12 Elm St", "Gym", "SE Hawthorne Blvd", "Market Street"}   # fakes' data


def main(frame, save, out, tap, gui_app):
  os.environ["TANDEM_PSEUDO"] = "1"
  from openpilot.selfdrive.ui.tandem import draw
  draw.DRAWN = set()
  os.makedirs(out, exist_ok=True)
  scene = os.environ.get("TANDEM_PSEUDO_SCENE", "scene_compare.py")
  runpy.run_path(os.path.join(HERE, scene))["main"](frame=frame, save=save, out=out, tap=tap, gui_app=gui_app)
  missed = sorted(t for t in draw.DRAWN if any(c.isalpha() for c in t) and "[" not in t and t not in SAMPLE)
  with open(os.path.join(out, "missed.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(missed) + "\n")
  print(f"pseudo: {len(draw.DRAWN)} strings drawn, {len(missed)} without brackets (missed.txt)")
