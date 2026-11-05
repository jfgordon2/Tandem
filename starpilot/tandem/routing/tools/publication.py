"""Checked, resumable GitHub data releases. Only the maintained catalog is mutable."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C
from openpilot.starpilot.tandem.routing.tools import check_states


def record(path):
  return {"bytes": path.stat().st_size, "sha256": bundles.digest(path)}


def check_routes(data, report):
  expected = {sample["name"] for sample in check_states.samples()}
  regions = {region for sample in check_states.samples() for region in sample["regions"]}
  if (not report.get("complete") or report.get("dataset") != data["dataset"]["id"]
      or report.get("sha256") != data["dataset"]["sha256"] or set(data["dataset"]["regions"]) != regions):
    raise C.RoutingError("data_incompatible")
  for group in ("baseline", "selected", "national"):
    cases = report.get(group, [])
    if len(cases) != len(expected) or {row["name"] for row in cases} != expected:
      raise C.RoutingError("coverage_unavailable")
    if any(row.get("status") != "ok" or (group != "baseline" and not row.get("matches")) for row in cases):
      raise C.RoutingError("data_incompatible")


class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    raise RuntimeError("GitHub API redirected; refusing to forward its token")


class GitHub:
  def __init__(self, repository, token=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
      raise C.RoutingError("invalid_request")
    self.repository = repository
    self.token = token or os.environ["GH_TOKEN"]
    self.opener = urllib.request.build_opener(NoRedirect())
    self.cached = {}

  def request(self, method, path, data=None, *, file=None):
    if path.startswith("https://uploads.github.com/"):
      url = path
    elif path.startswith("/"):
      url = "https://api.github.com/repos/" + self.repository + path
    else:
      raise C.RoutingError("invalid_request")
    for attempt in range(12):
      headers = {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "Tandem-routing-data"}
      body = None if data is None else json.dumps(data).encode()
      if body is not None:
        headers["Content-Type"] = "application/json"
      if file is not None:
        headers.update({"Content-Length": str(file.stat().st_size), "Content-Type": "application/octet-stream"})
      try:
        if file is not None:
          with file.open("rb") as stream:
            with self.opener.open(urllib.request.Request(url, data=stream, method=method, headers=headers), timeout=180) as response:
              return json.load(response)
        with self.opener.open(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=180) as response:
          raw = response.read()
          return json.loads(raw) if raw else None
      except urllib.error.HTTPError as error:
        limited = error.code == 429 or error.headers.get("Retry-After") or error.headers.get("X-RateLimit-Remaining") == "0"
        if error.code == 403 and not limited:
          try:
            limited = "secondary rate limit" in json.loads(error.read(65536)).get("message", "").lower()
          except (ValueError, OSError):
            pass
        if error.code in (403, 429) and limited:
          delay = float(error.headers.get("Retry-After", 0)) or max(1, float(error.headers.get("X-RateLimit-Reset", 0)) - time.time() + 2)  # noqa: TID251
          if error.headers.get("X-RateLimit-Remaining") != "0" and not error.headers.get("Retry-After"):
            delay = 60 * 2 ** attempt
          if delay > 7200:
            raise
          print(json.dumps({"github_rate_limit_wait_seconds": round(delay)}), flush=True)
          time.sleep(delay)
          continue
        # An upload may have succeeded despite a transport failure. Its caller
        # reconciles remote assets before trying again, rather than replaying it.
        if error.code not in (500, 502, 503, 504) or file is not None or attempt == 11:
          raise
      except OSError:
        if file is not None or attempt == 11:
          raise
      time.sleep(min(60, 2 ** attempt))
    raise C.RoutingError("download_failed")

  def find(self, tag):
    try:
      return self.request("GET", "/releases/tags/" + urllib.parse.quote(tag, safe=""))
    except urllib.error.HTTPError as error:
      if error.code != 404:
        raise
    # Drafts may not have a Git tag yet; the by-tag endpoint describes published
    # releases. Authenticated release listings also include this repo's drafts.
    page = 1
    while True:
      rows = self.request("GET", f"/releases?per_page=100&page={page}")
      found = next((row for row in rows if row["tag_name"] == tag), None)
      if found is not None or len(rows) < 100:
        return found
      page += 1

  def draft(self, tag, commit, identity, notes):
    marker = "<!-- tandem-routing:" + identity + " -->"
    release = self.find(tag)
    if release is None:
      try:
        release = self.request("POST", "/releases", {"tag_name": tag, "target_commitish": commit, "name": tag,
          "body": marker + "\n\n" + notes, "draft": True, "prerelease": True, "make_latest": "false"})
      except urllib.error.HTTPError as error:
        if error.code != 422:
          raise
        release = self.find(tag)  # reconcile a lost successful creation response
        if release is None:
          raise
    if marker not in (release.get("body") or ""):
      raise RuntimeError("Existing release is not owned by this routing build: " + tag)
    return release

  def assets(self, release, *, fresh=False):
    identity = release["id"]
    if fresh or identity not in self.cached:
      result, page = {}, 1
      while True:
        rows = self.request("GET", f"/releases/{identity}/assets?per_page=100&page={page}")
        result.update((row["name"], row) for row in rows)
        if len(rows) < 100:
          break
        page += 1
      self.cached[identity] = result
    return self.cached[identity]

  def upload(self, release, path, *, name=None):
    name = name or path.name
    spec = record(path)
    for attempt in range(4):
      existing = self.assets(release, fresh=attempt > 0).get(name)
      if existing is not None:
        if existing.get("state") == "uploaded" and existing.get("size") == spec["bytes"] and existing.get("digest") == "sha256:" + spec["sha256"]:
          return spec
        if release["draft"] and existing.get("state") == "starter":
          self.request("DELETE", f"/releases/assets/{existing['id']}")
        else:
          raise RuntimeError("Refusing to overwrite immutable routing asset: " + name)
      if not release["draft"]:
        raise RuntimeError("Refusing to add a missing asset to a published build: " + name)
      try:
        url = release["upload_url"].split("{", 1)[0] + "?name=" + urllib.parse.quote(name, safe="")
        row = self.request("POST", url, file=path)
        self.cached[release["id"]][name] = row
        if row.get("size") != spec["bytes"] or row.get("digest") != "sha256:" + spec["sha256"]:
          raise C.RoutingError("data_incompatible")
        return spec
      except (OSError, urllib.error.HTTPError):
        if attempt == 3:
          raise
        time.sleep(min(30, 2 ** attempt))
    raise C.RoutingError("download_failed")

  def verify(self, release, expected, *, extra=()):
    remote = self.assets(release, fresh=True)
    if set(remote) != set(expected) | set(extra):
      raise C.RoutingError("data_incompatible")
    for name, spec in expected.items():
      row = remote[name]
      if row.get("state") != "uploaded" or row.get("size") != spec["bytes"] or row.get("digest") != "sha256:" + spec["sha256"]:
        raise C.RoutingError("data_incompatible")

  def publish(self, release):
    if release["draft"]:
      # Anchor data tags to the workflow's authorized commit. Actual builder
      # provenance is recorded separately; no workflow-write PAT is needed.
      target = os.environ.get("GITHUB_SHA", release.get("target_commitish"))
      return self.request("PATCH", f"/releases/{release['id']}",
                          {"draft": False, "prerelease": True, "make_latest": "false", "target_commitish": target})
    return release

  def rename(self, asset, name):
    return self.request("PATCH", f"/releases/assets/{asset['id']}", {"name": name})


def promote(api, release, path, identity):
  """Verify a candidate first, preserve the old asset, restore it on failure.

  GitHub has no transactional asset replacement. A brief missing canonical URL
  during the two renames falls back to devices' cached/bundled catalog.
  """
  data = catalog.validate(json.loads(path.read_text()))
  current = api.assets(release, fresh=True).get("catalog.json")
  spec = record(path)
  if current and current.get("digest") == "sha256:" + spec["sha256"]:
    return
  if current:
    with urllib.request.urlopen(current["browser_download_url"], timeout=60) as response:
      old_raw = response.read(1024**2 + 1)
    if hashlib.sha256(old_raw).hexdigest() != current.get("digest", "").removeprefix("sha256:"):
      raise C.RoutingError("data_incompatible")
    previous = catalog.validate(json.loads(old_raw))
    if previous["runtime_version"] != data["runtime_version"]:
      raise RuntimeError("A runtime change requires a new maintained catalog URL")
    if previous["dataset"]["built_at"] > data["dataset"]["built_at"]:
      raise RuntimeError("Refusing to promote an older routing build")
  # This release is deliberately mutable, unlike dated source/graph releases.
  candidate_name = "catalog." + identity + ".json"
  api.upload({**release, "draft": True}, path, name=candidate_name)
  candidate = api.assets(release, fresh=True)[candidate_name]
  try:
    if current:
      api.rename(current, f"catalog.previous.{current['id']}.json")
    api.rename(candidate, "catalog.json")
  except Exception:
    # A response can be lost after a successful rename. Reconcile before undoing.
    latest = api.assets(release, fresh=True).get("catalog.json")
    if latest and latest.get("digest") == "sha256:" + spec["sha256"]:
      return
    if current and latest is None:
      api.rename(current, "catalog.json")
    raise
  if api.assets(release, fresh=True)["catalog.json"].get("digest") != "sha256:" + spec["sha256"]:
    raise C.RoutingError("data_incompatible")


def load_plan(path):
  plan = json.loads(path.read_text())
  data = catalog.validate(plan["catalog"])
  check_routes(data, plan["routes"])
  identity = data["dataset"]["id"]
  if (plan.get("schema") != 1 or not identity.startswith("us-driving-")
      or not re.fullmatch("[a-f0-9]{40}", plan["commit"])
      or plan["repository"] != os.environ.get("GITHUB_REPOSITORY", plan["repository"])):
    raise C.RoutingError("invalid_request")
  suffix = identity.removeprefix("us-driving-")
  prefix = "routing-us-" + suffix
  tags = [row["tag"] for row in plan["releases"]]
  expected = ["routing-us-sources-" + suffix,
              *(prefix + f"-{i}" for i in range(len(tags) - 2)), prefix + "-catalog"]
  if len(tags) < 3 or tags != expected or plan["catalog_tag"] != tags[-1]:
    raise C.RoutingError("invalid_request")
  for release in plan["releases"]:
    if not release["assets"] or len(release["assets"]) > 1000:
      raise C.RoutingError("invalid_request")
    for name, spec in release["assets"].items():
      if (not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not 0 < spec["bytes"] < 2 * 1024**3
          or not re.fullmatch("[a-f0-9]{64}", spec["sha256"])):
        raise C.RoutingError("invalid_request")
  for part in data["dataset"]["parts"]:
    tag = part["manifest"].rsplit("/", 2)[-2]
    expected_url = f"https://github.com/{plan['repository']}/releases/download/{tag}/{part['id']}.json"
    if tag not in tags[1:-1] or part["manifest"] != expected_url:
      raise C.RoutingError("invalid_request")
    assets = next(row["assets"] for row in plan["releases"] if row["tag"] == tag)
    manifest = assets.get(part["id"] + ".json", {})
    size = sum(assets.get(part["id"] + suffix, {}).get("bytes", 0) for suffix in (".squashfs", ".tiles.json"))
    if manifest.get("sha256") != part["sha256"] or size != part["bytes"]:
      raise C.RoutingError("data_incompatible")
  return plan
