"""Build checked monthly US data into drafts, then publish the catalog last."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, datasets, images
from openpilot.starpilot.tandem.routing.tools import check_states, export, hosted, publication as P, runtime, us_build

LICENSE = "© OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright"


def names(identity):
  if not identity.startswith("us-driving-") or not bundles.ID.fullmatch(identity) or len(identity) > 48:
    raise C.RoutingError("invalid_request")
  suffix = identity.removeprefix("us-driving-")
  return {"source": "routing-us-sources-" + suffix, "bucket": "routing-us-" + suffix + "-{bucket}",
          "catalog": "routing-us-" + suffix + "-catalog"}


def source_chunks(path, folder, limit=1024**3):
  """One temporary <=1 GiB upload chunk at a time, never another full PBF."""
  with path.open("rb") as stream:
    index = 0
    while stream.tell() < path.stat().st_size:
      chunk = folder / (path.name + f".part-{index:03d}")
      try:
        remaining = min(limit, path.stat().st_size - stream.tell())
        with chunk.open("wb") as target:
          while remaining:
            block = stream.read(min(1024**2, remaining))
            if not block:
              raise C.RoutingError("data_incompatible")
            target.write(block)
            remaining -= len(block)
        yield chunk
      finally:
        chunk.unlink(missing_ok=True)
      index += 1


class Stage:
  def __init__(self, api, output, identity, snapshot, commit):
    self.api, self.output, self.identity, self.snapshot, self.commit = api, output, identity, snapshot, commit
    self.tags, self.releases = names(identity), []

  def release(self, tag, notes):
    return self.api.draft(tag, self.identity, notes + "\n\nBuild source: " + self.commit + "\n\n" + LICENSE)

  def prepare(self):
    # Exercise release permissions before spending time downloading/building.
    self.release(self.tags["source"], "Reproducible source inputs for " + self.identity)

  def sources(self, inputs, build):
    folder = self.output / "source-assets"
    folder.mkdir(parents=True, exist_ok=True)
    release = self.release(self.tags["source"], "Reproducible source inputs for " + self.identity)
    expected, records = {}, []
    auxiliary = self.output / "auxiliary/receipt.json"
    extra = json.loads(auxiliary.read_text())["sources"]
    for source in (self.output / "sources").iterdir():
      receipt = source.with_name(source.name + ".source.json")
      if receipt.exists() and json.loads(receipt.read_text()) in extra:
        inputs = [*inputs, (source, json.loads(receipt.read_text()))]
    for path, receipt in inputs:
      if path.stat().st_size >= 2 * 1024**3:
        parts = []
        for chunk in source_chunks(path, folder):
          spec = self.api.upload(release, chunk)
          expected[chunk.name] = spec
          parts.append({"name": chunk.name, **spec})
        records.append({"name": path.name, **receipt, "parts": parts})
      else:
        spec = self.api.upload(release, path)
        expected[path.name] = spec
        records.append({"name": path.name, **receipt, **spec})
    polygons = folder / "state-polygons.tar.gz"
    with polygons.open("wb") as target, gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as compressed:
      with tarfile.open(fileobj=compressed, mode="w") as archive:
        for path in sorted((self.output / "sources").glob("*.poly")):
          info = archive.gettarinfo(str(path), path.name)
          info.uid = info.gid = info.mtime = 0
          info.uname = info.gname = ""
          with path.open("rb") as stream:
            archive.addfile(info, stream)
    expected[polygons.name] = self.api.upload(release, polygons)
    manifest = folder / "SOURCE-MANIFEST.json"
    C.atomic_json(manifest, {"dataset": self.identity, "snapshot": self.snapshot, "built_at": build["built_at"],
                            "commit": self.commit, "inputs": build["inputs"], "files": records, "polygons": P.record(polygons)})
    expected[manifest.name] = self.api.upload(release, manifest)
    readme = folder / "SOURCE-README.md"
    readme.write_text(f"# {self.identity} sources\n\n{LICENSE}\n\n" +
      "SOURCE-MANIFEST.json records origin URLs, checksums and byte lengths. Reassemble each large extract with " +
      "`cat NAME.part-* > NAME` in lexical order and verify its full SHA-256. State polygons and the complete US " +
      "parent boundary reproduce partition/admin behavior. Time-zone data and its license come from " +
      "https://github.com/evansiroky/timezone-boundary-builder.\n")
    expected[readme.name] = self.api.upload(release, readme)
    self.api.verify(release, expected)
    self.releases.append({"tag": release["tag_name"], "assets": expected})

  def graphs(self, assets):
    data = catalog.validate(json.loads((assets / "catalog.json").read_text()))
    routes = json.loads((self.output / "route-equivalence.json").read_text())
    P.check_routes(data, routes)
    if not self.releases:
      raise RuntimeError("Source inputs must be archived before the graph build")
    for folder in sorted(assets.iterdir()):
      if not folder.is_dir() or not folder.name.isdigit():
        continue
      tag = self.tags["bucket"].format(bucket=int(folder.name))
      release = self.release(tag, "Immutable driving-only state packs for " + self.identity)
      expected = {path.name: self.api.upload(release, path) for path in sorted(folder.iterdir())}
      self.api.verify(release, expected)
      self.releases.append({"tag": tag, "assets": expected})
    release = self.release(self.tags["catalog"], "Verified routing catalog for " + self.identity)
    readme = assets / "README.md"
    readme.write_text(f"# {self.identity}\n\n{LICENSE}\n\n" +
      f"Source data: https://github.com/{self.api.repository}/releases/tag/{self.tags['source']}\n\n" +
      "All selectable US regions were checked against the complete graph, including interstate/border routes " +
      "and the full indexed tar. See ROUTE-VERIFICATION.json. This is a sampled equivalence check, not exhaustive " +
      "route coverage or a device driving/RAM test.\n")
    expected = {}
    for path, name in ((assets / "catalog.json", "catalog.json"), (self.output / "route-equivalence.json", "ROUTE-VERIFICATION.json"),
                       (readme, "README.md"), (self.output / "source-assets/SOURCE-MANIFEST.json", "SOURCE-MANIFEST.json")):
      expected[name] = self.api.upload(release, path, name=name)
    self.api.verify(release, expected)
    self.releases.append({"tag": release["tag_name"], "assets": expected})
    plan = {"schema": 1, "repository": self.api.repository, "commit": self.commit, "catalog_tag": self.tags["catalog"],
            "catalog": data, "routes": routes, "releases": self.releases}
    path = assets / "publication.json"
    C.atomic_json(path, plan)
    self.api.upload(release, path)
    self.api.verify(release, expected, extra=("publication.json",))
    return path


@contextlib.contextmanager
def monitor(output):
  stop = threading.Event()
  started = time.monotonic()
  def record():
    with (output / "resources.jsonl").open("a") as log:
      while not stop.is_set():
        value = {"elapsed": time.monotonic() - started, **hosted.report(output)}
        log.write(json.dumps(value) + "\n")
        log.flush()
        print(json.dumps({"runner_resources": value}), flush=True)
        stop.wait(60)
  thread = threading.Thread(target=record, daemon=True)
  thread.start()
  try:
    yield
  finally:
    stop.set()
    thread.join(2)


def build(output, snapshot, identity, repository, *, stage=True):
  if output.exists():
    raise RuntimeError("Use a fresh output directory for each immutable monthly build")
  output.mkdir(parents=True)
  if shutil.disk_usage(output).free < 90 * 1024**3:
    raise C.RoutingError("no_space")
  commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
  api = P.GitHub(repository) if stage else None
  stager = Stage(api, output, identity, snapshot, commit) if stage else None
  base = f"https://github.com/{repository}/releases/download/" + names(identity)["bucket"]
  runtime.prepare()
  check_tools(output)
  if stager:
    stager.prepare()
  with monitor(output):
    us_build.build_us(output, snapshot, identity, base.format(bucket=0), concurrency=2,
                      prepared=stager.sources if stager else None, keep_sources=False, scratch_bytes=64 * 1024**3)
    check_states.check(output / "graph/tiles", output / "packages", output / "route-equivalence.json")
    export.export(output / "packages", output / "assets", base_url=base)
    if stager:
      return stager.graphs(output / "assets")
  return None


def check_tools(output):
  """Fail on incompatible native tools before downloading the national PBF."""
  native = subprocess.check_output([str(C.runtime_python()), "-c",
    "from valhalla import PYVALHALLA_DIR; print(PYVALHALLA_DIR / 'bin' / 'valhalla_build_tiles')"], text=True).strip()
  subprocess.run([native, "--version"], check=True)
  payload = b"Tandem routing compression check\n"
  image = output / "tool-smoke.squashfs"
  logical = images.pack_stream(iter([payload]), len(payload), image)
  images.verify_graph(output, {"graph": {"file": image.name, **logical}})
  image.unlink()


def public_smoke(data, routes, repository, folder):
  """Fresh public downloads, device-format assembly, and one native DC route."""
  previous = {key: os.environ.get(key) for key in ("TANDEM_ROUTING_DIR", "TANDEM_ROUTING_MOUNT_DIR")}
  runtime_root = C.root() / "runtimes"
  root = folder / "public-smoke"
  root.mkdir(mode=0o700)
  root.chmod(0o700)
  os.environ.update(TANDEM_ROUTING_DIR=str(root), TANDEM_ROUTING_MOUNT_DIR=str(root / "mounts"))
  (root / "runtimes").symlink_to(runtime_root.resolve(), target_is_directory=True)
  try:
    package = catalog.plan("us_state.DC", data)[0][0]
    bundle = datasets.install(package)
    case = next(row for row in check_states.samples() if row["name"] == "DC local")
    with images.reader(bundle):
      actual = check_states.routes(images.graph_path(bundle), [case])[0]
    baseline = next(row for row in routes["baseline"] if row["name"] == "DC local")
    if actual["status"] != "ok" or actual["sha256"] != baseline["sha256"]:
      raise C.RoutingError("data_incompatible")
    C.atomic_json(folder / "public-smoke.json", {"repository": repository, "dataset": data["dataset"]["id"], **actual})
  finally:
    images.release_unused()
    for key, value in previous.items():
      if value is None:
        os.environ.pop(key, None)
      else:
        os.environ[key] = value


def publish(path, folder):
  plan = P.load_plan(path)
  api = P.GitHub(plan["repository"])
  releases = []
  for item in plan["releases"]:
    release = api.find(item["tag"])
    if release is None:
      raise C.RoutingError("data_missing")
    if "<!-- tandem-routing:" + plan["catalog"]["dataset"]["id"] + " -->" not in (release.get("body") or ""):
      raise C.RoutingError("data_incompatible")
    api.verify(release, item["assets"], extra=("publication.json",) if item["tag"] == plan["catalog_tag"] else ())
    releases.append(release)
  # Every SHA-256, source and complete route check passes before any draft is
  # public. The maintained catalog still points at the previous working build.
  for release in releases:
    api.publish(release)
  public_url = f"https://github.com/{api.repository}/releases/download/{plan['catalog_tag']}/catalog.json"
  with urllib.request.urlopen(public_url, timeout=60) as response:
    raw = response.read(1024**2 + 1)
  spec = plan["releases"][-1]["assets"]["catalog.json"]
  if len(raw) != spec["bytes"] or hashlib.sha256(raw).hexdigest() != spec["sha256"]:
    raise C.RoutingError("data_incompatible")
  data = catalog.validate(json.loads(raw))
  runtime.prepare()
  public_smoke(data, plan["routes"], api.repository, folder)
  stable = api.find("routing-us-v1")
  if stable is None or stable["draft"]:
    raise RuntimeError("The maintained routing-us-v1 catalog must already be public")
  candidate = folder / "catalog.json"
  candidate.write_bytes(raw)
  P.promote(api, stable, candidate, data["dataset"]["id"])
  C.atomic_json(folder / "published.json", {"dataset": data["dataset"]["id"], "sha256": data["dataset"]["sha256"],
                                          "catalog": catalog.URL, "complete": True})


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  sub = parser.add_subparsers(dest="action", required=True)
  builder = sub.add_parser("build")
  builder.add_argument("output", type=Path)
  builder.add_argument("--snapshot", default="")
  builder.add_argument("--id", default="")
  builder.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "jfgordon2/Tandem"))
  builder.add_argument("--no-stage", action="store_true", help="local build/verification only; no GitHub uploads")
  publisher = sub.add_parser("publish")
  publisher.add_argument("plan", type=Path)
  publisher.add_argument("--out", type=Path, required=True)
  args = parser.parse_args()
  if args.action == "build":
    date = datetime.datetime.now(datetime.UTC).date() - datetime.timedelta(days=2)
    snapshot = args.snapshot or date.strftime("%y%m%d")
    if not re.fullmatch(r"[0-9]{6}", snapshot):
      parser.error("snapshot must be a dated YYMMDD extract")
    identity = args.id or f"us-driving-20{snapshot}-r{os.environ['GITHUB_RUN_ID']}-a{os.environ['GITHUB_RUN_ATTEMPT']}"
    build(args.output, snapshot, identity, args.repository, stage=not args.no_stage)
  else:
    args.out.mkdir(parents=True, exist_ok=True)
    publish(args.plan, args.out)


if __name__ == "__main__":
  main()
