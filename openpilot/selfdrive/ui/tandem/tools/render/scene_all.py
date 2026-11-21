"""Every built screen: runs each scene_*.py here in turn, saving each render under its mock's name.

  PYTHONPATH=$PWD BIG=1 .venv/bin/python openpilot/selfdrive/ui/tandem/tools/render/snap.py \\
    openpilot/selfdrive/ui/tandem/tools/render/scene_all.py openpilot/selfdrive/ui/tandem/tools/out/renders

A scene that fails is reported and skipped, so one broken screen doesn't hide the rest.
"""
import os
import runpy
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"scene_all.py", "scene_pseudo.py"}


def scenes() -> list[str]:
  """The scene files, in name order."""
  return sorted(name for name in os.listdir(HERE) if name.startswith("scene_") and name.endswith(".py") and name not in SKIP)


def main(frame, save, out, tap, gui_app):
  os.makedirs(out, exist_ok=True)
  failed = []
  for name in scenes():
    try:
      runpy.run_path(os.path.join(HERE, name))["main"](frame=frame, save=save, out=out, tap=tap, gui_app=gui_app)
    except Exception:
      failed.append(name)
      traceback.print_exc()
  print(f"scenes: {len(scenes()) - len(failed)} rendered" + (f", failed: {', '.join(failed)}" if failed else ""))
