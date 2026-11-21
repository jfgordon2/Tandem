"""Tandem's diagnostics policy (starpilot/tandem/diagnostics.py): automatic crash reports stay on the device."""
from __future__ import annotations

import ast
from pathlib import Path

from openpilot.starpilot.tandem import diagnostics

ROOT = Path(__file__).resolve().parents[3]
SENTRY = ROOT / "system/sentry.py"


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


def _function(path: str, name: str) -> ast.FunctionDef:
  tree = ast.parse((ROOT / path).read_text())
  return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def test_athenad_forwards_no_logs_unattended() -> None:
  """athenad's log_handler sends the device's logs on its own; Tandem's hook returns first while the policy is off."""
  imported, check = _function("system/athena/athenad.py", "log_handler").body[:2]
  assert isinstance(imported, ast.ImportFrom) and imported.module == "openpilot.starpilot.tandem.diagnostics", \
    "system/athena/athenad.py's log_handler no longer checks Tandem's diagnostics policy; reapply the hook"
  assert isinstance(check, ast.If) and "AUTOMATIC_DIAGNOSTICS_ENABLED" in ast.unparse(check.test)
  assert isinstance(check.body[0], ast.Return)


def test_usage_statistics_dont_start_unattended() -> None:
  """StarPilot's usage_stats process reports to its statistics server; it's enabled only with the policy on."""
  tree = ast.parse((ROOT / "system/manager/process_config.py").read_text())
  call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant)
              and n.args[0].value == "usage_stats")
  enabled = next(k.value for k in call.keywords if k.arg == "enabled")
  assert "AUTOMATIC_DIAGNOSTICS_ENABLED" in ast.unparse(enabled), \
    "system/manager/process_config.py starts usage_stats without Tandem's diagnostics policy; reapply the hook"
  assert diagnostics.AUTOMATIC_DIAGNOSTICS_ENABLED is False
