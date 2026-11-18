"""Tandem's diagnostics policy (starpilot/tandem/diagnostics.py): automatic crash reports stay on the device."""
from __future__ import annotations

import ast
from pathlib import Path

from openpilot.starpilot.tandem import diagnostics

SENTRY = Path(__file__).resolve().parents[3] / "system/sentry.py"


def test_only_reports_the_driver_sends_pass() -> None:
  options = diagnostics.sentry_options()
  keep = options["before_send"]
  assert keep({"tags": {"report_type": "manual_issue_report"}}, {}) is not None
  assert keep({"tags": {"daemon": "manager"}}, {}) is None and keep({}, {}) is None
  assert options["before_send_transaction"]({}, {}) is None and options["send_client_reports"] is False


def test_the_options_join_starpilots_init_without_repeating_a_keyword() -> None:
  """A repeated keyword would make sdk.init fail, which StarPilot catches by turning crash reporting off."""
  tree = ast.parse(SENTRY.read_text())
  call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "init"
              and any(k.arg == "dsn" for k in n.keywords))
  starpilot = {k.arg for k in call.keywords if k.arg}
  assert any(k.arg is None for k in call.keywords), "system/sentry.py no longer passes Tandem's sentry_options(); reapply the hook"
  assert not starpilot & set(diagnostics.sentry_options())
