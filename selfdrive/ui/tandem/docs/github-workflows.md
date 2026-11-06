# GitHub workflow review

Reviewed November 5, 2026, while preparing monthly routing-data builds. The
repository's default workflow token is already read-only and cannot approve
pull-request reviews. The map workflow uses its own steps and does not invoke
upstream setup/build/cache composites.

| Workflow | Trigger and effects | Tandem policy |
| --- | --- | --- |
| Compile StarPilot | Manual only. Builds binaries on a TrueNAS runner, commits tracked changes and pushes the selected branch. Requests contents write access. | Disabled in repository Actions settings. A job-level repository guard permits the retained implementation only in StarPilotHQ/StarPilot. |
| Compile Bluescreens | Manual only. Can build panda firmware and other device binaries, commit changes and push the selected branch. Requests contents write access. | Disabled in Actions settings, with the same repository guard. |
| Publish TrueNAS Runner Image | Manual only. Builds and publishes a GHCR container image; requests package write access. | Disabled in Actions settings, with the same repository guard. |
| Fleet controller safety | Manual or pull requests affecting the listed driving/safety paths. Compiles and replays controller tests using temporary params, then uploads test artifacts. Contents read access only. | Retained. No branch push, data release or package publication. |
| Monthly routing maps | Owned monthly/manual data build and publication. Review is read-only; draft/data-release jobs request contents write. Ordinary relevant valhalla pushes run review; a deliberate build-check commit stages drafts only. | Retained. No branch push, device build, GHCR publisher or upstream CI composites. The first probe push ran only this workflow; none of the inherited publishers ran. See the [monthly data guide](valhalla-monthly-map-releases.md). |

The four nested `action.yaml` files are composite actions, not independently
triggered workflows. `setup` fetches LFS data, uses caches, normalizes checkout
permissions and evaluates the caller's build command. `setup-with-retry` wraps
it; `compile-openpilot` builds binaries and saves a cache; `auto-cache` selects
Namespace/GitHub caches and changes permissions on a caller-specified directory.
They remain upstream files for merge compatibility and are not used by maps.

The active map and safety workflows pin current official actions to exact
commits: Checkout 7.0.1, Setup Python 7.1.0 where needed, Upload Artifact 7.0.2
and Download Artifact 8.0.2 where needed. Their action metadata declares Node 24.
The Node 20 warning on the initial resource probe came from Upload Artifact v4;
the retained safety workflow's old versions have been replaced too. Disabled
publishers and uninvoked composites retain their upstream versions. The
[updated hosted review](https://github.com/jfgordon2/Tandem/actions/runs/42067280548)
passed without the Node 20 deprecation warning. Both active workflows' pins and
the inherited publisher guards are also installed on the default `release`
branch. The navigation implementation has since been merged into `release`.
Scheduled map builds use the exact released trigger commit; explicit `valhalla`
push checks remain pinned to their test commit. The merge does not enable any
inherited publisher or add another automatic publication trigger.

## Future upstream merges

`tools/workflow-policy.json` records the reviewed contents of every workflow and
nested composite action. `tools/workflow_policy.py` and its UI-suite test reject
new, missing, modified or symlinked workflow/action files. Review triggers,
permissions, scripts, external services and publishing commands before updating
those fingerprints. There is no automatic accept/update command.

Run the policy check locally before pushing a merge:

```sh
python3 selfdrive/ui/tandem/tools/workflow_policy.py
```

The same check runs in the owned map workflow. It detects unreviewed changes;
it is not a GitHub-wide execution filter. A new workflow could trigger if someone
pushes it without running the local checks. Preserve the three repository guards
and their Actions disablement when merging upstream. Re-enabling a disabled
publisher requires a separate review of its intended use in Tandem.

## Hosted runner measurement

The [resource probe](https://github.com/jfgordon2/Tandem/actions/runs/42048786431)
completed on GitHub-provided Ubuntu 24.04, image `20261101.360.1`, with four vCPUs
and 16 GB RAM. Available disk increased from 90,745,298,944 to 115,546,361,856
bytes (107.6 GiB) after removing unused Android, .NET, Haskell, CodeQL and
PowerShell SDKs from that disposable VM. Python, Node and the Actions runner were
left intact. This establishes available resources, not completion of a national
map build on that runner. The raw report is in `tools/out/monthly-hosted-probe/`.
