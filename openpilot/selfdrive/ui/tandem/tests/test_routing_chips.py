"""The driving screen's routing chip on StarPilot 7 (onroad/status.routing_state and routing_chip): StarPilot's navigation
status with Tandem's routing status, as the approved valhalla2-chip mocks show it."""
from __future__ import annotations

import pytest

from openpilot.selfdrive.ui.tandem.onroad.status import ChipTone, routing_chip, routing_state

NOW = 100.0


def chip(navigation: str, tandem: dict | None = None, fallback: dict | None = None, recalculating: bool = False,
         offline_only: bool = False) -> tuple[str, ChipTone] | None:
  result = routing_chip(routing_state(navigation, tandem, fallback, recalculating, NOW), NOW, offline_only)
  return (result.label, result.tone) if result is not None else None


def test_finding_a_first_route_then_recalculating() -> None:
  assert chip("routing") == ("Finding route", ChipTone.INFO)
  assert chip("routing", recalculating=True) == ("Recalculating route", ChipTone.INFO)


def test_waiting_for_gps() -> None:
  assert chip("waitingForLocation") == ("Waiting for GPS", ChipTone.INFO)


@pytest.mark.parametrize("offline_only, label", [(False, "Route unavailable"), (True, "Offline maps unavailable")])
def test_no_route_warns(offline_only: bool, label: str) -> None:
  assert chip("routeUnavailable", {"status": "outside_coverage"}, offline_only=offline_only) == (label, ChipTone.PAUSED)
  assert chip("routeUnavailable", None, offline_only=offline_only) == (label, ChipTone.PAUSED)


def test_a_fallback_says_which_maps_it_used_briefly() -> None:
  offline = {"status": "ready", "provider": "offline", "fallback": True}
  assert chip("guiding", offline, offline) == ("Using offline maps", ChipTone.INFO)
  online = {"status": "ready", "provider": "online", "fallback": True}
  assert chip("guiding", online, online) == ("Using online maps", ChipTone.INFO)
  assert chip("guiding", online, online, offline_only=True) is None   # never with Offline maps only
  assert chip("guiding", offline, None) is None   # only for the first 3 seconds
  assert chip("guiding", {"status": "ready", "provider": "online", "fallback": False}, {"status": "ready", "fallback": False}) is None


@pytest.mark.parametrize("navigation", ["", "disabled", "noDestination", "needsKey", "arrived", "stale"])
def test_nothing_to_say(navigation: str) -> None:
  assert chip(navigation) is None
