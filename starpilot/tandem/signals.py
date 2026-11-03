"""Tandem's animation catalog shared by the UI, theme installer and Galaxy hooks."""
import json
from pathlib import Path
import re
import shutil

from openpilot.common.basedir import BASEDIR

SIGNAL_PACKS_PATH = Path(BASEDIR) / "selfdrive/ui/tandem/assets/signal_packs"

SIGNAL_ANIMATION_PARAM = "SignalAnimation"
BUNDLED_SIGNAL_ANIMATIONS = (
  ("sequential", "Sequential"),
  ("flow", "Flow"),
  ("open_flow", "Open Flow"),
  ("glide", "Glide"),
  ("frog", "Frog"),
  ("pouncing_cat", "Pouncing Cat"),
  ("shooting_star", "Shooting Star"),
  ("bouncing_ball", "Bouncing Ball"),
)
SIGNAL_FRAME_PATTERN = re.compile(r"turn_signal(?:_(\d+))?\.png", re.IGNORECASE)

def installed_packs(folder, normalize):
  """Downloaded theme packs with PNG signal frames the raylib renderer can draw (GIF-only packs are skipped)."""
  bundled = {slug for slug, _ in BUNDLED_SIGNAL_ANIMATIONS}
  packs_dir = folder / "theme_packs"
  try:
    candidates = sorted(packs_dir.iterdir()) if packs_dir.is_dir() else []
  except OSError:
    return []
  packs = []
  for pack in candidates:
    signals = pack / "signals"
    if pack.name in bundled or not signals.is_dir():
      continue
    try:
      if any(SIGNAL_FRAME_PATTERN.fullmatch(frame.name) for frame in signals.iterdir()):
        packs.append({"value": pack.name, "label": normalize(pack.name)})
    except OSError:
      continue
  return sorted(packs, key=lambda option: option["label"].casefold())


def options(params, folder, normalize):
  """Choices for the Turn Signal Animation dropdown: None, bundled animations, then downloaded packs."""
  options = [{"value": "stock", "label": "None"}]
  options += [{"value": slug, "label": label} for slug, label in BUNDLED_SIGNAL_ANIMATIONS]
  options += installed_packs(folder, normalize)
  saved = (params.get(SIGNAL_ANIMATION_PARAM, encoding="utf-8") or "stock").strip()
  if saved not in ("stock", "none") and all(option["value"] != saved for option in options):
    options.append({"value": saved, "label": f"{normalize(saved)} (not installed)", "missing": True})
  return options


def effective(params):
  """The animation actually in effect: like the device menus, Custom Themes off means none."""
  if not params.get_bool("CustomThemes"):
    return "stock"
  saved = (params.get(SIGNAL_ANIMATION_PARAM, encoding="utf-8") or "stock").strip()
  return "stock" if saved in ("", "none") else saved


def install_packs(folder):
  if SIGNAL_PACKS_PATH.is_dir():
    for pack in sorted(SIGNAL_PACKS_PATH.iterdir()):
      if (pack / "signals").is_dir():
        shutil.copytree(pack / "signals", folder / "theme_packs" / pack.name / "signals", dirs_exist_ok=True)


def set_animation(params, key, value, folder, normalize, refresh):
  if key != SIGNAL_ANIMATION_PARAM:
    return None
  from flask import jsonify
  choice = value.strip()
  choice = "stock" if choice in ("", "none") else choice
  available = {option["value"]: option for option in options(params, folder, normalize) if not option.get("missing")}
  if choice not in available:
    return jsonify({"error": f"Unknown turn signal animation '{choice}'."}), 400
  params.put(SIGNAL_ANIMATION_PARAM, choice)
  updated = {SIGNAL_ANIMATION_PARAM: choice}
  if choice != "stock":
    params.put_bool("CustomThemes", True)
    params.put_bool("RandomThemes", False)
    updated.update({"CustomThemes": True, "RandomThemes": False})
  refresh()
  return jsonify({"message": f"Turn signal animation set to {available[choice]['label']}.", "updated": updated}), 200


def catalog(path):
  entries = json.loads(path.read_text())
  for section in entries:
    if any(item["key"] == "CustomUI" for item in section["params"]):
      index = next((i + 1 for i, item in enumerate(section["params"]) if item["key"] == "HolidayThemes"), 0)
      section["params"].insert(index, dict(CATALOG_ENTRY))
      break
  return entries


CATALOG_ENTRY = {'key': 'SignalAnimation',
 'label': 'Turn Signal Animation',
 'description': 'The animation shown while a turn signal is on. Indicators (Sequential, Flow, Open Flow, Glide) stay beside the current '
                + 'speed; animations travel across the screen. Choosing one turns on Custom Themes and turns off Random Themes. Holiday '
                + 'Themes still take over during holidays.',
 'picker_description': 'Chooses the turn-signal animation.',
 'data_type': 'string',
 'ui_type': 'dropdown',
 'options_endpoint': '/api/turn_signal_animations',
 'settings_tier': 'simple'}
