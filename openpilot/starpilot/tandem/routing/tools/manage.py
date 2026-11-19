"""Inspect and install routing data independently of mapd. Run with --help."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

from openpilot.starpilot.tandem.routing import bundles, config as C


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, newurl):
    if urllib.parse.urlparse(newurl).scheme != "https":
      raise C.RoutingError("invalid_request")
    return super().redirect_request(request, fp, code, message, headers, newurl)


def download(url: str, progress=lambda done, total: None, cancelled=lambda: False):
  C.require_parked()
  if urllib.parse.urlparse(url).scheme != "https":
    raise C.RoutingError("invalid_request")
  opener = urllib.request.build_opener(HTTPSRedirect())
  with opener.open(url, timeout=30) as response:
    raw = response.read(65537)
  if len(raw) > 65536:
    raise C.RoutingError("invalid_request")
  try:
    manifest = bundles.validate_manifest(json.loads(raw))
  except ValueError:
    raise C.RoutingError("data_incompatible") from None
  (C.root() / "staging").mkdir(parents=True, exist_ok=True)
  def gate():
    C.require_parked()
    if cancelled():
      raise C.RoutingError("cancelled")
  from openpilot.starpilot.tandem.routing import downloads
  return downloads.install({"id": manifest["id"], "manifest": url, "sha256": hashlib.sha256(raw).hexdigest(),
                            "bytes": sum(r.get("download", r)["bytes"] for r in manifest["files"].values())},
                           gate=gate, progress=progress, activate=False)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("status")
  commands.add_parser("runtime")
  commands.add_parser("enable")
  commands.add_parser("disable")
  for name in ("install", "activate", "remove", "download", "verify"):
    commands.add_parser(name).add_argument("target")
  args = parser.parse_args()
  if args.command == "runtime":
    from openpilot.starpilot.tandem.routing.tools.runtime import prepare
    print(prepare())
  elif args.command in ("enable", "disable"):
    C.set_enabled(args.command == "enable")
  elif args.command == "install":
    print(bundles.install(Path(args.target)).id)
  elif args.command == "download":
    print(download(args.target, progress=lambda done, total: print(f"{done}/{total}", flush=True)).id)
  elif args.command == "activate":
    print(bundles.activate(args.target).id)
  elif args.command == "remove":
    bundles.remove(args.target)
  elif args.command == "verify":
    if not bundles.ID.fullmatch(args.target):
      raise C.RoutingError("invalid_request")
    print(bundles.verify(C.root() / "bundles" / args.target).id)
  else:
    print(json.dumps({**bundles.capability(), "offline_only": C.policy()[0], "preferred": C.policy()[1],
                      "root": str(C.root()), "bundles": [b.manifest for b in bundles.installed()]}, indent=2))


if __name__ == "__main__":
  main()
