"""A failed build/upload/promotion cannot replace working published routing data."""
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from openpilot.starpilot.tandem.routing import catalog, config as C
from openpilot.starpilot.tandem.routing.tools import check_states, monthly, publication as P


def data():
  result = json.loads(Path(catalog.__file__).with_suffix(".json").read_text())
  result["dataset"]["id"] = "us-driving-20261224-r1-a1"
  result["dataset"]["built_at"] = "2026-12-26T00:00:00+00:00"
  return result


def routes(dataset):
  baseline = [{"name": sample["name"], "status": "ok", "sha256": "a" * 64} for sample in check_states.samples()]
  return {"complete": True, "dataset": dataset["dataset"]["id"], "sha256": dataset["dataset"]["sha256"],
          "baseline": baseline, "selected": [{**row, "matches": True} for row in baseline],
          "national": [{**row, "matches": True} for row in baseline]}


def plan():
  dataset = data()
  tags = monthly.names(dataset["dataset"]["id"])
  buckets = {}
  for index, part in enumerate(dataset["dataset"]["parts"]):
    bucket = index // 300
    assets = buckets.setdefault(bucket, {})
    part["manifest"] = "https://github.com/test/maps/releases/download/" + tags["bucket"].format(bucket=bucket) + "/" + part["id"] + ".json"
    assets[part["id"] + ".json"] = {"bytes": 1, "sha256": part["sha256"]}
    assets[part["id"] + ".squashfs"] = {"bytes": part["bytes"] - 1, "sha256": "b" * 64}
    assets[part["id"] + ".tiles.json"] = {"bytes": 1, "sha256": "c" * 64}
  spec = {"bytes": 1, "sha256": "a" * 64}
  return {"schema": 1, "repository": "test/maps", "commit": "a" * 40, "catalog_tag": tags["catalog"],
          "catalog": dataset, "routes": routes(dataset), "releases": [
            {"tag": tags["source"], "assets": {"SOURCE-MANIFEST.json": spec}},
            *({"tag": tags["bucket"].format(bucket=bucket), "assets": assets} for bucket, assets in buckets.items()),
            {"tag": tags["catalog"], "assets": {"catalog.json": spec}}]}


@pytest.mark.parametrize("fault", ["incomplete", "missing_state", "missing_border", "failed_route", "mismatched", "wrong_build"])
def test_route_gate_rejects_incomplete_or_mixed_evidence(fault):
  dataset = data()
  report = routes(dataset)
  P.check_routes(dataset, report)
  if fault == "incomplete":
    report["complete"] = False
  elif fault == "missing_state":
    report["selected"] = report["selected"][1:]
  elif fault == "missing_border":
    report["national"] = [r for r in report["national"] if r["name"] != "Davenport to Moline"]
  elif fault == "failed_route":
    report["baseline"][0]["status"] = "failed"
  elif fault == "mismatched":
    report["selected"][0]["matches"] = False
  else:
    report["sha256"] = "0" * 64
  with pytest.raises(C.RoutingError):
    P.check_routes(dataset, report)


@pytest.mark.parametrize("fault", ["foreign_repo", "app_tag", "foreign_url", "manifest", "size", "bad_checksum", "too_large"])
def test_plan_targets_only_this_builds_checked_routing_assets(tmp_path, monkeypatch, fault):
  monkeypatch.setenv("GITHUB_REPOSITORY", "test/maps")
  payload = plan()
  path = tmp_path / "plan.json"
  path.write_text(json.dumps(payload))
  P.load_plan(path)
  if fault == "foreign_repo":
    payload["repository"] = "another/repo"
  elif fault == "app_tag":
    payload["releases"][0]["tag"] = "software-release"
  elif fault == "foreign_url":
    payload["catalog"]["dataset"]["parts"][0]["manifest"] = "https://example.com/foreign.json"
  else:
    asset = next(iter(payload["releases"][1]["assets"].values()))
    if fault == "manifest":
      asset["sha256"] = "d" * 64
    elif fault == "bad_checksum":
      asset["sha256"] = "not a checksum"
    elif fault == "too_large":
      asset["bytes"] = 2 * 1024**3
    else:
      next(v for k, v in payload["releases"][1]["assets"].items() if k.endswith(".squashfs"))["bytes"] += 1
  path.write_text(json.dumps(payload))
  with pytest.raises(C.RoutingError):
    P.load_plan(path)


def asset(path, identity=1):
  spec = P.record(path)
  return {"id": identity, "name": path.name, "size": spec["bytes"], "digest": "sha256:" + spec["sha256"],
          "state": "uploaded", "browser_download_url": "https://example.invalid/current"}


def test_lost_upload_response_reconciles_and_does_not_upload_twice(tmp_path, monkeypatch):
  path = tmp_path / "graph.bin"
  path.write_bytes(b"checked bytes")
  uploads, remote = [], []
  api = P.GitHub("test/maps", token="test-only")
  class Opener:
    def open(self, request, **_):
      if request.method == "GET":
        return io.BytesIO(json.dumps(remote).encode())
      uploads.append(request.data.read())
      assert request.get_header("Content-length") == str(path.stat().st_size)
      remote.append(asset(path))
      raise TimeoutError("response lost after acceptance")
  api.opener = Opener()
  monkeypatch.setattr(P.time, "sleep", lambda _: None)
  result = api.upload({"id": 1, "draft": True, "upload_url": "https://uploads.github.com/repos/test/maps/releases/1/assets{?name}"}, path)
  assert result == P.record(path) and uploads == [path.read_bytes()]


@pytest.mark.parametrize("draft", [True, False])
def test_checked_immutable_asset_is_never_overwritten(tmp_path, draft):
  path = tmp_path / "graph.bin"
  path.write_bytes(b"new bytes")
  api = P.GitHub("test/maps", token="test-only")
  api.cached[1] = {path.name: {**asset(path), "digest": "sha256:" + "0" * 64}}
  with pytest.raises(RuntimeError, match="overwrite immutable"):
    api.upload({"id": 1, "draft": draft}, path)


def test_github_api_rate_limit_waits_for_reset_without_logging_credentials(monkeypatch, capsys):
  api = P.GitHub("test/maps", token="test-only-never-log")
  calls, waits = [], []
  class Opener:
    def open(self, request, **_):
      calls.append(request)
      if len(calls) == 1:
        raise urllib.error.HTTPError(request.full_url, 403, "rate limit", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1001"}, None)
      return io.BytesIO(b"{}")
  api.opener = Opener()
  monkeypatch.setattr(P.time, "time", lambda: 1000)
  monkeypatch.setattr(P.time, "sleep", waits.append)
  assert api.request("GET", "/releases") == {}
  assert waits == [3] and len(calls) == 2
  assert "test-only-never-log" not in capsys.readouterr().out


def test_token_cannot_follow_an_api_redirect():
  request = urllib.request.Request("https://api.github.com/repos/test/maps", headers={"Authorization": "Bearer test-only"})
  with pytest.raises(RuntimeError, match="refusing to forward"):
    P.NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://example.com")


def test_release_lookup_finds_an_unpublished_draft_without_a_git_tag(monkeypatch):
  api = P.GitHub("test/maps", token="test-only")
  draft = {"id": 4, "tag_name": "routing-us-test-catalog", "draft": True}
  def request(method, path, **_):
    if "/tags/" in path:
      raise urllib.error.HTTPError(path, 404, "tag not found", {}, None)
    return [draft]
  monkeypatch.setattr(api, "request", request)
  assert api.find(draft["tag_name"]) == draft


class CatalogAPI:
  def __init__(self, old_path, fail=""):
    self.rows = {"catalog.json": asset(old_path)}
    self.calls, self.fail, self.next_id = [], fail, 2

  def assets(self, *_, **__):
    return self.rows.copy()

  def upload(self, release, path, *, name):
    self.calls.append(("upload", name))
    self.rows[name] = {**asset(path, self.next_id), "name": name}
    return P.record(path)

  def rename(self, item, name):
    self.calls.append(("rename", item["id"], name))
    is_candidate = item["id"] == 2 and name == "catalog.json"
    if is_candidate and self.fail == "before":
      raise OSError("rename failed")
    if item["id"] == 1 and name != "catalog.json" and self.fail == "old_before":
      raise OSError("old rename failed")
    for old_name, row in list(self.rows.items()):
      if row["id"] == item["id"]:
        self.rows[name] = {**self.rows.pop(old_name), "name": name}
        break
    if is_candidate and self.fail == "after":
      raise OSError("rename response lost")
    if item["id"] == 1 and name != "catalog.json" and self.fail == "old_after":
      raise OSError("old rename response lost")


@pytest.mark.parametrize("fault", ["", "before", "after", "old_before", "old_after"])
def test_catalog_promotion_preserves_old_bytes_and_recovers_a_failed_rename(tmp_path, monkeypatch, fault):
  candidate = data()
  previous = copy.deepcopy(candidate)
  previous["dataset"]["built_at"] = "2026-11-04T00:00:00+00:00"
  old, new = tmp_path / "catalog.json", tmp_path / "candidate.json"
  old.write_text(json.dumps(previous))
  new.write_text(json.dumps(candidate))
  api = CatalogAPI(old, fault)
  monkeypatch.setattr(P.urllib.request, "urlopen", lambda *_, **__: io.BytesIO(old.read_bytes()))
  if fault in ("before", "old_before", "old_after"):
    with pytest.raises(OSError):
      P.promote(api, {"id": 1}, new, candidate["dataset"]["id"])
    assert api.rows["catalog.json"]["digest"] == asset(old)["digest"]
  else:
    P.promote(api, {"id": 1}, new, candidate["dataset"]["id"])
    assert api.rows["catalog.json"]["digest"] == asset(new)["digest"]
    assert api.rows["catalog.previous.1.json"]["digest"] == asset(old)["digest"]


def test_older_build_cannot_replace_a_newer_catalog(tmp_path, monkeypatch):
  candidate, previous = data(), data()
  previous["dataset"]["built_at"] = "2027-01-01T00:00:00+00:00"
  old, new = tmp_path / "catalog.json", tmp_path / "candidate.json"
  old.write_text(json.dumps(previous))
  new.write_text(json.dumps(candidate))
  api = CatalogAPI(old)
  monkeypatch.setattr(P.urllib.request, "urlopen", lambda *_, **__: io.BytesIO(old.read_bytes()))
  with pytest.raises(RuntimeError, match="older"):
    P.promote(api, {"id": 1}, new, candidate["dataset"]["id"])
  assert api.calls == []


def test_source_chunking_bounds_scratch_and_releases_it_on_interruption(tmp_path):
  source = tmp_path / "source.pbf"
  source.write_bytes(b"abcdefg")
  pieces, collected = monthly.source_chunks(source, tmp_path, limit=3), []
  for path in pieces:
    assert len(list(tmp_path.glob("*.part-*"))) == 1
    collected.append(path.read_bytes())
  assert collected == [b"abc", b"def", b"g"] and not list(tmp_path.glob("*.part-*"))
  pieces = monthly.source_chunks(source, tmp_path, limit=3)
  assert next(pieces).read_bytes() == b"abc"
  pieces.close()
  assert not list(tmp_path.glob("*.part-*")) and source.read_bytes() == b"abcdefg"


def test_source_release_contains_original_auxiliary_and_polygon_inputs(tmp_path):
  sources = tmp_path / "sources"
  sources.mkdir()
  main, country = sources / "us-261224.osm.pbf", sources / "us-country.osm"
  main.write_bytes(b"original dated PBF")
  country.write_bytes(b"complete parent boundary")
  (sources / "iowa.poly").write_text("checked polygon")
  original = {"url": "https://example.com/us-261224.osm.pbf", **P.record(main)}
  extra = {"url": "https://example.com/country.osm", **P.record(country)}
  country.with_name(country.name + ".source.json").write_text(json.dumps(extra))
  auxiliary = tmp_path / "auxiliary"
  auxiliary.mkdir()
  (auxiliary / "receipt.json").write_text(json.dumps({"sources": [extra]}))
  uploaded = {}
  class API:
    def draft(self, tag, *args):
      return {"tag_name": tag}
    def upload(self, release, path):
      uploaded[path.name] = path.read_bytes()
      return P.record(path)
    def verify(self, release, expected):
      assert set(uploaded) == set(expected)
  stager = monthly.Stage(API(), tmp_path, "us-driving-20261224-r1-a1", "261224", "a" * 40)
  stager.sources([(main, original)], {"built_at": "2026-12-26", "inputs": {"boundary": "checked"}})
  manifest = json.loads(uploaded["SOURCE-MANIFEST.json"])
  assert {row["name"] for row in manifest["files"]} == {main.name, country.name}
  assert manifest["commit"] == "a" * 40 and manifest["snapshot"] == "261224"
  assert {"state-polygons.tar.gz", "SOURCE-README.md"} <= set(uploaded)
  assert main.exists() and country.exists() and len(stager.releases) == 1


def test_build_stages_drafts_only_after_complete_route_checks(tmp_path, monkeypatch):
  calls = []
  monkeypatch.setattr(monthly.shutil, "disk_usage", lambda _: SimpleNamespace(total=200 * 1024**3, free=100 * 1024**3))
  monkeypatch.setattr(monthly.subprocess, "check_output", lambda *_, **__: "a" * 40)
  monkeypatch.setattr(monthly.runtime, "prepare", lambda: calls.append("runtime"))
  monkeypatch.setattr(monthly, "check_tools", lambda _: calls.append("native tools"))
  monkeypatch.setattr(monthly.P, "GitHub", lambda *_: SimpleNamespace())
  class Stager:
    def __init__(self, *_):
      pass
    def sources(self, *_):
      calls.append("sources archived")
    def graphs(self, *_):
      calls.append("graphs staged")
  monkeypatch.setattr(monthly, "Stage", Stager)
  def builder(*_, **kwargs):
    assert kwargs["keep_sources"] is False and kwargs["concurrency"] == 2
    kwargs["prepared"]([], {})
    calls.append("build")
  monkeypatch.setattr(monthly.us_build, "build_us", builder)
  monkeypatch.setattr(monthly.check_states, "check", lambda *_: calls.append("all route checks"))
  monkeypatch.setattr(monthly.export, "export", lambda *_, **__: calls.append("checked export"))
  monthly.build(tmp_path / "fresh", "261224", "us-driving-20261224-r1-a1", "test/maps")
  assert calls == ["runtime", "native tools", "sources archived", "build", "all route checks", "checked export", "graphs staged"]


def test_route_check_failure_cannot_stage_graphs(tmp_path, monkeypatch):
  monkeypatch.setattr(monthly.shutil, "disk_usage", lambda _: SimpleNamespace(total=200 * 1024**3, free=100 * 1024**3))
  monkeypatch.setattr(monthly.subprocess, "check_output", lambda *_, **__: "a" * 40)
  monkeypatch.setattr(monthly.runtime, "prepare", lambda: None)
  monkeypatch.setattr(monthly, "check_tools", lambda _: None)
  monkeypatch.setattr(monthly.P, "GitHub", lambda *_: SimpleNamespace())
  monkeypatch.setattr(monthly.us_build, "build_us", lambda *_, **__: None)
  def fail(*_):
    raise C.RoutingError("data_incompatible")
  monkeypatch.setattr(monthly.check_states, "check", fail)
  def forbidden(*_, **__):
    pytest.fail("failed routing data reached export/publication")
  monkeypatch.setattr(monthly.export, "export", forbidden)
  with pytest.raises(C.RoutingError):
    monthly.build(tmp_path / "fresh", "261224", "us-driving-20261224-r1-a1", "test/maps")


@pytest.mark.parametrize("keep_sources", [False, True])
@pytest.mark.parametrize("archive_failed", [False, True])
def test_compact_builder_reclaims_only_archived_sources_and_keeps_the_verified_merge(tmp_path, monkeypatch, keep_sources, archive_failed):
  builder = monthly.us_build
  monkeypatch.setattr(builder, "REGIONS", {"IA": "Iowa", "IL": "Illinois"})
  monkeypatch.setattr(builder, "territory_polygons", lambda _: {})
  inputs, calls = [], []
  def fetch(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"source")
    inputs.append(target)
    return {"url": url, **P.record(target)}
  monkeypatch.setattr(builder.sources, "fetch", fetch)
  monkeypatch.setattr(builder.states, "polygon", lambda _: None)
  monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *_, **__: io.BytesIO(b"polygon"))
  def merge(_, target):
    target.write_bytes(b"verified merged data")
    return P.record(target)
  monkeypatch.setattr(builder.sources, "merge", merge)
  monkeypatch.setattr(builder.auxiliary, "prepare", lambda *args: (tmp_path / "admin", tmp_path / "timezone", {"sources": []}))
  monkeypatch.setattr(builder.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
  def archived(values, receipt):
    assert all(path.exists() for path, _ in values)
    calls.append("archived")
    if archive_failed:
      raise OSError("source upload failed")
  def native(sources, output, **kwargs):
    assert all(path.is_file() for path, _ in sources)
    assert all(path.exists() == keep_sources for path in inputs)
    calls.append("native build")
    return output / "tiles"
  monkeypatch.setattr(builder.build, "build_graph", native)
  monkeypatch.setattr(builder.states, "partition", lambda *args: calls.append("partition"))
  if archive_failed:
    with pytest.raises(OSError, match="source upload"):
      builder.build_us(tmp_path, "261224", "us-driving-test", "https://example.com", prepared=archived, keep_sources=keep_sources)
    assert calls == ["archived"] and all(path.exists() for path in inputs)
  else:
    builder.build_us(tmp_path, "261224", "us-driving-test", "https://example.com", prepared=archived, keep_sources=keep_sources)
    assert calls == ["archived", "native build", "partition"]
    assert (tmp_path / "sources/us-combined-261224.osm.pbf").read_bytes() == b"verified merged data"


@pytest.mark.parametrize("fault", ["", "remote_digest", "public_download", "public_route"])
def test_publish_verifies_every_release_before_publication_and_promotes_only_after_public_route(tmp_path, monkeypatch, fault):
  payload = plan()
  monkeypatch.setenv("GITHUB_REPOSITORY", "test/maps")
  raw = json.dumps(payload["catalog"]).encode()
  candidate = tmp_path / "catalog.json"
  candidate.write_bytes(raw)
  payload["releases"][-1]["assets"]["catalog.json"] = P.record(candidate)
  path = tmp_path / "publication.json"
  path.write_text(json.dumps(payload))
  calls = []
  class API:
    repository = "test/maps"
    def find(self, tag):
      return {"id": tag, "draft": tag != "routing-us-v1", "tag_name": tag,
              "body": "<!-- tandem-routing:" + payload["catalog"]["dataset"]["id"] + " -->"}
    def verify(self, release, *_, **__):
      calls.append(("verify", release["tag_name"]))
      if fault == "remote_digest" and len(calls) == 2:
        raise C.RoutingError("data_incompatible")
    def publish(self, release):
      calls.append(("publish", release["tag_name"]))
  monkeypatch.setattr(P, "GitHub", lambda *_: API())
  monkeypatch.setattr(monthly.urllib.request, "urlopen", lambda *_, **__: io.BytesIO(b"changed" if fault == "public_download" else raw))
  monkeypatch.setattr(monthly.runtime, "prepare", lambda: calls.append(("runtime", "")))
  def smoke(*_):
    calls.append(("public route", ""))
    if fault == "public_route":
      raise C.RoutingError("data_incompatible")
  monkeypatch.setattr(monthly, "public_smoke", smoke)
  monkeypatch.setattr(P, "promote", lambda *_: calls.append(("promote", "")))
  if fault:
    with pytest.raises(C.RoutingError):
      monthly.publish(path, tmp_path)
    assert not any(operation == "promote" for operation, _ in calls)
    if fault == "remote_digest":
      assert not any(operation == "publish" for operation, _ in calls)
  else:
    monthly.publish(path, tmp_path)
    count = len(payload["releases"])
    assert [operation for operation, _ in calls] == ["verify"] * count + ["publish"] * count + ["runtime", "public route", "promote"]
    assert json.loads((tmp_path / "published.json").read_text())["complete"]
