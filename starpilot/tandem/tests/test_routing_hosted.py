"""Hosted runner cleanup cannot target a workstation or accept arbitrary paths."""
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing.tools import hosted


@pytest.mark.parametrize("missing", ["GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS"])
def test_cleanup_requires_all_disposable_runner_markers(monkeypatch, missing):
  monkeypatch.setenv("GITHUB_ACTIONS", "true")
  monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
  monkeypatch.setenv("RUNNER_OS", "Linux")
  monkeypatch.delenv(missing)
  def forbidden(*_, **__):
    pytest.fail("attempted privileged cleanup outside a GitHub-hosted Linux VM")
  monkeypatch.setattr(hosted.subprocess, "run", forbidden)
  with pytest.raises(RuntimeError, match="disposable"):
    hosted.prepare()


def test_hosted_cleanup_uses_only_fixed_unused_sdk_paths(monkeypatch):
  monkeypatch.setenv("GITHUB_ACTIONS", "true")
  monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
  monkeypatch.setenv("RUNNER_OS", "Linux")
  calls = []
  monkeypatch.setattr(hosted.subprocess, "run", lambda command, **_: calls.append(command))
  hosted.prepare()
  assert calls == [["sudo", "rm", "-rf", "--", *hosted.UNUSED_SDKS]]
  assert not any("Python" in path or "node" in path or path == "/opt/hostedtoolcache" for path in hosted.UNUSED_SDKS)


def test_resource_report_records_available_disk_without_modifying_it(monkeypatch, tmp_path):
  monkeypatch.setattr(hosted.shutil, "disk_usage", lambda _: SimpleNamespace(total=100, free=60))
  assert hosted.report(tmp_path)["disk"] == {"total": 100, "free": 60}
