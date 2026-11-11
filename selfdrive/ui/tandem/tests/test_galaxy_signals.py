import ast
from pathlib import Path

from types import SimpleNamespace

from openpilot.starpilot.tandem import signals

REPO_ROOT = Path(__file__).resolve().parents[4]
the_galaxy = SimpleNamespace(BUNDLED_SIGNAL_ANIMATIONS=signals.BUNDLED_SIGNAL_ANIMATIONS)
BUNDLED = [
  "sequential", "flow", "open_flow", "glide",
  "frog", "pouncing_cat", "shooting_star", "bouncing_ball", "unicorn_rider",
]


def _client(monkeypatch, tmp_path, values):
  from flask import Flask, jsonify, request

  class Params:
    def __init__(self):
      self.values, self.writes = dict(values), []

    def get(self, key, **kwargs):
      return self.values.get(key)

    def get_bool(self, key):
      return bool(self.values.get(key, False))

    def put(self, key, value):
      self.values[key] = value
      self.writes.append((key, value))

    put_bool = put

  params, refreshes = Params(), []
  normalize = lambda value: value.replace("_", " ").title()  # noqa: E731
  app = Flask(__name__)

  @app.get("/api/turn_signal_animations")
  def options():
    return jsonify(signals.options(params, tmp_path, normalize))

  @app.put("/api/params")
  def update():
    data = request.get_json()
    return signals.set_animation(params, data["key"], data["value"], tmp_path, normalize, lambda: refreshes.append(True))

  @app.get("/api/params/all")
  def all_params():
    return jsonify(dict(params.values, SignalAnimation=signals.effective(params)))

  return app.test_client(), params, refreshes


def _install_pack(root, name, *frames):
  signals = root / "theme_packs" / name / "signals"
  signals.mkdir(parents=True)
  for frame in frames:
    (signals / frame).write_bytes(b"")


def test_dropdown_lists_none_bundled_animations_then_downloaded_png_packs(monkeypatch, tmp_path):
  _install_pack(tmp_path, "zebra_stripes", "turn_signal_1.png", "turn_signal_2.png", "traditional_125")
  _install_pack(tmp_path, "aurora", "turn_signal.png", "static_0")
  _install_pack(tmp_path, "gif_only", "turn_signal.gif")              # the raylib renderer can't draw GIFs
  _install_pack(tmp_path, "blindspot_only", "turn_signal_blindspot.png")
  _install_pack(tmp_path, "frog", "turn_signal_1.png")                 # boot-time copy of a bundled pack
  client, _, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "stock"})

  options = client.get("/api/turn_signal_animations").get_json()

  assert [option["value"] for option in options] == ["stock", *BUNDLED, "aurora", "zebra_stripes"]
  assert options[0] == {"value": "stock", "label": "None"}
  assert {"value": "open_flow", "label": "Open Flow"} in options
  assert {"value": "zebra_stripes", "label": "Zebra Stripes"} in options


def test_saved_pack_that_is_no_longer_installed_is_shown_but_not_selectable(monkeypatch, tmp_path):
  client, fake_params, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "old_pack", "CustomThemes": True})

  options = client.get("/api/turn_signal_animations").get_json()
  assert options[-1] == {"value": "old_pack", "label": "Old Pack (not installed)", "missing": True}

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "old_pack"})
  assert response.status_code == 400
  assert fake_params.writes == []


def test_choosing_an_animation_enables_custom_themes_and_disables_random_themes(monkeypatch, tmp_path):
  client, fake_params, refreshes = _client(monkeypatch, tmp_path, {
    "SignalAnimation": "stock", "CustomThemes": False, "RandomThemes": True, "IconPack": "saved_icons",
  })

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "sequential", "label": "Sequential"})

  assert response.status_code == 200
  body = response.get_json()
  assert body["updated"] == {"SignalAnimation": "sequential", "CustomThemes": True, "RandomThemes": False}
  assert body["message"] == "Turn signal animation set to Sequential."
  assert fake_params.values["SignalAnimation"] == "sequential"
  assert fake_params.values["CustomThemes"] is True and fake_params.values["RandomThemes"] is False
  assert fake_params.values["IconPack"] == "saved_icons"   # other saved theme choices are left alone
  assert refreshes == [True]


def test_choosing_none_only_clears_the_animation(monkeypatch, tmp_path):
  client, fake_params, refreshes = _client(monkeypatch, tmp_path, {
    "SignalAnimation": "frog", "CustomThemes": True, "RandomThemes": False,
  })

  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "stock"})

  assert response.status_code == 200
  assert response.get_json()["updated"] == {"SignalAnimation": "stock"}
  assert fake_params.writes == [("SignalAnimation", "stock")]
  assert refreshes == [True]


def test_downloaded_pack_can_be_chosen_and_unknown_values_are_rejected(monkeypatch, tmp_path):
  _install_pack(tmp_path, "aurora", "turn_signal.png")
  client, fake_params, _ = _client(monkeypatch, tmp_path, {"SignalAnimation": "stock"})

  assert client.put("/api/params", json={"key": "SignalAnimation", "value": "aurora"}).status_code == 200
  assert fake_params.values["SignalAnimation"] == "aurora"

  fake_params.writes.clear()
  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "../../etc"})
  assert response.status_code == 400
  assert fake_params.writes == []


def test_settings_show_the_animation_actually_in_effect(monkeypatch, tmp_path):
  cases = [
    ({"SignalAnimation": "frog", "CustomThemes": False}, "stock"),   # saved but inactive, like the device menus
    ({"SignalAnimation": "frog", "CustomThemes": True}, "frog"),
    ({"SignalAnimation": "none", "CustomThemes": True}, "stock"),
  ]
  for values, expected in cases:
    client, _, _ = _client(monkeypatch, tmp_path, values)
    assert client.get("/api/params/all").get_json()["SignalAnimation"] == expected


def test_layout_offers_the_dropdown_next_to_holiday_themes():
  layout = signals.catalog(REPO_ROOT / "starpilot/common/assets/device_settings_layout.json")
  visual = next(section for section in layout if section["name"] == "Visual (Display & UI)")
  keys = [param["key"] for param in visual["params"]]
  entry = visual["params"][keys.index("SignalAnimation")]
  assert keys.index("SignalAnimation") == keys.index("HolidayThemes") + 1
  assert entry["ui_type"] == "dropdown" and entry["data_type"] == "string"
  assert entry["options_endpoint"] == "/api/turn_signal_animations"
  assert "parent_key" not in entry  # visible without enabling another feature first


def test_bundled_list_matches_the_owned_device_renderer():
  from openpilot.selfdrive.ui.tandem.onroad.turn_signals import BUNDLED_SIGNAL_PATHS
  assert {slug for slug, _ in signals.BUNDLED_SIGNAL_ANIMATIONS} == set(BUNDLED_SIGNAL_PATHS)
  assert [slug for slug, _ in signals.BUNDLED_SIGNAL_ANIMATIONS] == BUNDLED


def test_production_galaxy_routes_call_the_owned_helpers(monkeypatch, tmp_path):
  """Exercise the actual route bodies without starting Galaxy's unrelated device services."""
  from flask import Flask, jsonify, request

  _, params, refreshes = _client(monkeypatch, tmp_path, {"SignalAnimation": "stock", "CustomThemes": False})
  path = REPO_ROOT / "starpilot/system/the_galaxy/the_galaxy.py"
  source = ast.parse(path.read_text())
  setup = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "setup")
  names = {"_get_signal_animation_options", "_get_effective_signal_animation", "get_turn_signal_animations",
           "device_settings_layout_asset", "get_param", "get_all_params"}
  functions = [node for node in [*source.body, *setup.body] if isinstance(node, ast.FunctionDef) and node.name in names]
  assert {node.name for node in functions} == names
  app = Flask(__name__)
  namespace = {
    "app": app, "jsonify": jsonify, "request": request, "params": params, "tandem_signals": signals,
    "THEME_SAVE_PATH": tmp_path, "SETTINGS_CATALOG_PATH": REPO_ROOT / "starpilot/common/assets/device_settings_layout.json",
    "utilities": SimpleNamespace(normalize_theme_name=lambda value: value.replace("_", " ").title()),
    "update_starpilot_toggles": lambda: refreshes.append(True),
    "_get_param_type_info": lambda: ({"SignalAnimation"}, {"SignalAnimation": str}),
    "PERSONALITY_PROFILES_PARAM": "PersonalityProfiles", "FAVORITE_SLOTS_PARAM": "FavoriteSlots",
    "migrate_cancel_button_controls": lambda _: None, "_get_default_param_values": dict,
    "_get_current_param_value": lambda key, *args: params.values.get(key), "_get_effective_car_make": lambda value: value,
    "supports_tesla_can_wake": lambda _: False, "_sanitize_json_value": lambda value: value,
  }
  for name in ("PERSONALITY_PARKED_PARAM_KEYS", "PERSONALITY_PROFILE_ENABLE_PARAM_KEYS", "LONGITUDINAL_MODE_KEYS",
               "MODEL_SMOOTHING_KEYS", "PERSONALITY_ADVANCED_PARAM_KEYS", "PERSONALITY_FOLLOW_PARAM_KEYS"):
    namespace[name] = set()
  for name in ("_get_has_radar", "_get_vehicle_parked", "_get_alpha_longitudinal_available", "_get_has_rivian_angle_harness",
               "_get_is_tici_or_tizi"):
    namespace[name] = lambda: False
  exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), namespace)
  client = app.test_client()
  assert [item["value"] for item in client.get("/api/turn_signal_animations").get_json()] == ["stock", *BUNDLED]
  layout = client.get("/assets/components/tools/device_settings_layout.json").get_json()
  assert any(param["key"] == "SignalAnimation" for section in layout for param in section["params"])
  response = client.put("/api/params", json={"key": "SignalAnimation", "value": "frog"})
  assert response.status_code == 200 and params.values["CustomThemes"] and refreshes == [True]
  assert client.get("/api/params/all").get_json()["SignalAnimation"] == "frog"
  params.values["CustomThemes"] = False
  assert client.get("/api/params/all").get_json()["SignalAnimation"] == "stock"
  assert client.put("/api/params", json={"key": "SignalAnimation", "value": "../missing"}).status_code == 400
