"""Check the upstream state contracts used by the StarPilot 7 port."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from openpilot.cereal import log
from openpilot.cereal.services import SERVICE_LIST

ROOT = Path(__file__).resolve().parents[4]
PLAN = Path(__file__).resolve().parents[1] / "PORTING.md"

# These replacements and reused keys have typed reads even when release used strings or flags.
PARAM_TYPES = {
  "ConditionalModeConfig": "JSON",
  "IsOffroad": "BOOL",
  "LaneChangePreferences": "JSON",
  "LastGPSPosition": "BYTES",
  "LateralControllerSelection": "JSON",
  "LiveDelay": "BYTES",
  "LongitudinalPersonalityProfiles": "JSON",
  "NavDestination": "JSON",
  "OnroadCustomizations": "JSON",
  "SLCConfirmation": "INT",
  "SLCOffsetSchedule": "JSON",
  "SLCOnEngage": "BOOL",
  "SentryMotionPreferences": "JSON",
  "ShowBrakeStatus": "BOOL",
  "StarPilotDisplayPreferencesEnabled": "BOOL",
  "SteeringLearningPreferences": "BYTES",
  "TorqueOverrideDocument": "JSON",
  "UpdaterAutomaticDownloads": "BOOL",
  "UpdaterOSUpdate": "JSON",
  "VehicleSelection": "JSON",
}

# A listed service without fields is still checked for registration. Nested paths
# cover the replacement fields and the shared inputs that need to survive a merge.
SERVICE_FIELDS = {
  "aolAxisState": ("qualified", "lateralActive"),
  "aolIntentWire": (),
  "carControl": ("latActive", "longActive", "actuators.accel", "actuators.torque"),
  "carState": ("vEgo", "aEgo", "canValid", "canTimeout", "cruiseState.standstill", "vCruiseCluster",
               "leftBlinker", "rightBlinker", "leftBlindspot", "rightBlindspot", "gearShifter", "standstill"),
  "controlsState": ("curvature", "longControlState"),
  "deviceState": ("started", "startedMonoTime", "memoryUsagePercent", "networkType", "networkMetered",
                  "networkStrength", "cpuUsagePercent", "gpuUsagePercent", "maxTempC"),
  "driverStateV2": ("leftDriverData", "rightDriverData"),
  "gpsLocation": ("hasFix", "latitude", "longitude", "bearingDeg"),
  "gpsLocationExternal": ("hasFix", "latitude", "longitude", "bearingDeg", "speed"),
  "lateralDelay": ("lateralDelay",),
  "mapdOut": ("roadName", "wayName"),
  "modelV2": ("laneLines", "meta.laneChangeState", "meta.laneChangeDirection"),
  "navRoute": ("coordinates",),
  "onroadEvents": ("name",),
  "pandaStates": ("pandaType",),
  "rawAudioData": ("data",),
  "radarState": ("leadOne.present", "leadOne.dRel", "leadOne.vLead", "leadOne.vRel"),
  "selfdriveState": ("enabled", "experimentalMode", "alertSize", "alertType"),
  "slcAction": ("sessionId", "sequenceId", "decisionId", "presentationId", "kind"),
  "slcState": ("curve.controlling", "curve.ceilingMps", "curve.hasCeiling", "hasPending", "pendingSinceMonoTime",
               "decisionId", "presentationId", "driverOverrideActive", "isLimitingMaxSet", "source", "offset",
               "acceptedSpeedLimit", "acceptedSource", "acceptedAdjustedLimit", "hasAcceptedAdjustedLimit",
               "pendingSpeedLimit", "pendingSource", "pendingAdjustedLimit", "hasPendingAdjustedLimit",
               "presentationAdjustedLimit", "hasPresentationAdjustedLimit", "sourceReadings.observationKind"),
  "spotMonitorState": ("observation.left.warning", "observation.right.warning", "observation.validUntilBootTime"),
  "starpilotCarState": ("pauseLateral", "pauseLongitudinal", "forceCoast", "pulseAndGlide"),
  "starpilotLongitudinalPlan": ("forceStopHolding", "forceStopBraking", "sourcePlanMonoTime",
                               "departureAlertKind", "departureAlertMonoTime"),
  "starpilotNavigation": ("navigation.sessionId", "navigation.revision", "navigation.startedMonoTime",
                          "navigation.frameMonoTime", "navigation.locationMonoTime", "navigation.controlValid",
                          "navigation.status", "navigation.instruction", "navigation.nextManeuver", "navigation.route"),
  "starpilotRadarState": ("leadLeft.status", "leadRight.status", "qualifiedAdjacent"),
  "starpilotSelfdriveState": ("alertSize", "alertType", "conditionalModeAck.effectiveExperimental"),
  "vehicleParameters": ("valid", "steerRatio", "steerRatioValid"),
}

# Keep this test importable on hosts without the device's msgq and Params libraries.
OWNER_ENTRY_POINTS = {
  "starpilot/galaxy/onroad_layout.py": ("OnroadLayoutOwner.snapshot", "OnroadLayoutOwner.save"),
  "starpilot/galaxy/software_operations.py": ("SoftwareOperations.snapshot", "SoftwareOperations.action"),
  "starpilot/galaxy/starport_send.py": ("StarPortLogSender",),
  "starpilot/maps/operation_owner.py": ("request_operation", "MapSnapshotOperationOwner.dispatch"),
  "starpilot/models/manager.py": ("ModelManager.snapshot", "ModelManager.action"),
  "starpilot/navigation/intent.py": ("current_instruction",),
  "starpilot/navigation/offline_owner.py": ("OfflineMapsOwner.snapshot", "OfflineMapsOwner.action"),
  "starpilot/navigation/owner.py": ("NavigationOwner.snapshot", "NavigationOwner.configure", "NavigationOwner.select",
                                         "NavigationOwner.favorite", "NavigationOwner.remove_favorite"),
  "starpilot/parked_vehicle.py": ("ParkedVehicleReader",),
  "starpilot/ui/appearance_owner.py": ("AppearanceOwner.snapshot", "AppearanceOwner.apply"),
  "starpilot/ui/appearance_preferences.py": ("onroad_appearance",),
  "starpilot/ui/conditional_feature.py": ("ConditionalFeature.apply",),
  "starpilot/ui/display_owner.py": ("DisplayOwner.snapshot", "DisplayOwner.apply"),
  "starpilot/ui/feature_settings_owner.py": ("FeatureSettingsOwner.snapshot", "FeatureSettingsOwner.apply"),
  "starpilot/ui/gain_feature.py": ("GainFeature.apply",),
  "starpilot/ui/lane_change_feature.py": ("LaneChangeFeature.apply",),
  "starpilot/ui/navigation_state.py": ("navigation_display", "official_navigation_display"),
  "starpilot/ui/onroad_customization.py": ("read_customization",),
  "starpilot/ui/pip_warning.py": ("PiPWarningSource.sample",),
  "starpilot/ui/runtime_snapshot.py": ("current_alert", "current_message", "display_message", "display_aol_latch", "current_curve_message"),
  "starpilot/ui/sentry_owner.py": ("SentryOwner.snapshot", "SentryOwner.apply"),
  "starpilot/ui/slc_action_dispatch.py": ("SlcActionDispatcher.dispatch",),
  "starpilot/ui/sounds_owner.py": ("SoundsOwner.snapshot", "SoundsOwner.apply"),
  "starpilot/vehicle_selection.py": ("VehicleSelectionOwner.snapshot", "VehicleSelectionOwner.choose"),
}


def section(heading: str) -> str:
  """Return one Markdown section from the stage 3 map."""
  return re.split(r"^#{2,3} ", PLAN.read_text().split(f"### {heading}\n", 1)[1], maxsplit=1, flags=re.M)[0]


def table_keys(markdown: str) -> list[str]:
  """Read the backticked identifiers in the table's first column."""
  return [key for line in markdown.splitlines() if line.startswith("|")
          for key in re.findall(r"`(\w+)`", line.split("|")[1])]


def test_release_param_inventory_still_matches_dom_registry() -> None:
  registry = dict(re.findall(r'^\s*\{"(\w+)",\s*\{[^,]+,\s*(\w+)', (ROOT / "common/params_keys.h").read_text(), re.M))
  removed = table_keys(section("Missing Params"))
  kept = section("Retained Params").split("```text\n", 1)[1].split("```", 1)[0].split()
  assert len(removed) == len(set(removed)) == 119
  assert len(kept) == len(set(kept)) == 117
  assert not set(removed) & set(kept)
  assert not set(removed) & registry.keys(), "Review any legacy keys reintroduced by Dom"
  assert not set(kept) - registry.keys(), "Map newly removed Params in PORTING.md"
  assert {key: registry.get(key) for key in PARAM_TYPES} == PARAM_TYPES


def test_release_services_have_current_contracts() -> None:
  services = table_keys(section("Cereal services").split("| Release `starpilotPlan` fields", 1)[0])
  retired = {"liveDelay", "liveParameters", "starpilotPlan"}
  assert len(services) == len(set(services)) == 22
  assert retired <= set(services)
  assert not retired & SERVICE_LIST.keys(), "Review any reintroduced service before wiring it back"
  for service in (set(services) - retired) | SERVICE_FIELDS.keys():
    assert service in SERVICE_LIST, f"{service} moved from the service registry"
    field = log.Event.schema.fields.get(service)
    assert field is not None, f"{service} has no cereal Event payload"
    for path in SERVICE_FIELDS.get(service, ()):
      parent = field
      for component in path.split("."):
        schema = parent.schema
        if parent.proto.slot.type.which() == "list":
          schema = schema.elementType
        assert component in schema.fields, f"{service}.{path} changed in cereal"
        parent = schema.fields[component]


def declaration(node: ast.Module | ast.ClassDef, name: str) -> ast.ClassDef | ast.FunctionDef:
  """Find a direct class, method or function by its identifier without loading it."""
  for item in node.body:
    if isinstance(item, (ast.ClassDef, ast.FunctionDef)) and item.name == name:
      return item
  raise AssertionError(f"{name} is no longer defined here")


def test_upstream_settings_and_state_owners_keep_their_entry_points() -> None:
  for source, entry_points in OWNER_ENTRY_POINTS.items():
    module = ast.parse((ROOT / source).read_text())
    for entry_point in entry_points:
      owner, _, method = entry_point.partition(".")
      item = declaration(module, owner)
      if method:
        assert isinstance(item, ast.ClassDef), f"{source}: {owner} changed"
        assert isinstance(declaration(item, method), ast.FunctionDef)


def test_ui_state_supplies_mapped_offroad_and_display_sources() -> None:
  module = ast.parse((ROOT / "selfdrive/ui/ui_state.py").read_text())
  state = declaration(module, "UIState")
  assert isinstance(state, ast.ClassDef)
  for method in ("add_offroad_transition_callback", "engaged", "is_offroad", "is_onroad"):
    assert isinstance(declaration(state, method), ast.FunctionDef)
  initialize = declaration(state, "_initialize")
  attrs = {node.attr for node in ast.walk(initialize)
           if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
           and isinstance(node.value, ast.Name) and node.value.id == "self"}
  assert {"CP", "chestnut_state", "ignition", "is_metric", "params", "prime_state", "started", "started_frame"} <= attrs

  submaster = next(node for node in ast.walk(initialize) if isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Attribute) and node.func.attr == "SubMaster")
  service_list = submaster.args[0]
  assert isinstance(service_list, ast.List)
  subscribed = {node.value for node in service_list.elts if isinstance(node, ast.Constant)}
  required = {"aolAxisState", "aolIntentWire", "carControl", "carOutput", "carState", "controlsState", "deviceState",
              "driverStateV2", "gpsLocation", "gpsLocationExternal", "lateralDelay", "modelV2", "navInstruction",
              "navRoute", "onroadEvents", "pandaStates", "radarState", "rawAudioData", "selfdriveState", "slcState",
              "starpilotCarState", "starpilotNavigation", "starpilotSelfdriveState", "vehicleParameters"}
  assert not required - subscribed, "Review UIState subscriptions in PORTING.md"
