# Demand-driven routing broker

November 4, 2026. Implemented on `valhalla`, after merging release's RAM diagnostics.

## Why

The owner's drive logs showed roughly 65 MB retained by `tandem_routingd` on every drive, including drives without navigation or downloads. The device reached 95% RAM. The larger, separate growth in `starpilot_process` remains under investigation in [the memory findings](starpilot-process-memory.md); this change removes routing's unnecessary idle process.

## Code paths

- The existing `system/manager/process_config.py` registration already calls owned `routing.config.should_run`. No additional upstream edit was needed. Its gate now requires routing to be enabled and either a destination, a pending map job, or a recent request wake.
- `routing/demand.py` reads `NavDestination`, `map-request.json`, `map-job.json` and a shared-memory `routing-wake.json` snapshot. The map installer shares these journal readers and phase definitions. Manager never imports the broker, map catalog/installer or native worker. Its no-demand check creates no directories or processes.
- `client.request("route")` wakes the broker before connecting. This covers both the existing preview and navigation callers, even before a preview has set `NavDestination`. Missing/refused socket connections retry for at most five seconds, within the fifteen-second total request budget. The remaining deadline follows the request into the broker/native queue. Requests already sent are not replayed. Status and release requests neither start the broker nor refresh its idle grace.
- `routingd.main` refreshes the wake while a destination or map job needs it, and after route requests. The shared grace is 120 seconds, with active-demand refreshes every five seconds. Once demand ends, shutdown therefore begins after roughly 115–120 seconds, plus bounded cleanup. Manager uses the same record and will not continually restart an idle broker. A new preview/request wakes it again.
- New map request IDs start the process. Road-wait, preparation, download and installation journals keep it eligible, including paused jobs. Completed, failed or cancelled journals do not. The existing map gates and restart/resume behavior remain unchanged.
- Native Valhalla still exits after fifteen seconds without route work, including during guidance. A destination retains the broker for reroutes, while navigation owns the completed route.
- `TANDEM_ROUTING=0`, the maintainer disable marker and all four upstream-screen rollback switches still disable the integration. Startup and request wakes respect those switches.

Full parked audits now run opportunistically while the broker is already alive and the Wi-Fi/parked gate permits. They do not start an otherwise unused process. File identity/receipt checks on route startup and acceptance checks during installation remain unchanged.

## Verification

- Host routing suite: **187 passed**. Compiled/hardware-dependent navigation, routing-cereal, sentry and telemetry modules were omitted on the host.
- Private device routing suite: **188 passed**, including routing-cereal. Navigation, sentry and telemetry modules were omitted.
- Host UI suite after the release merge: **703 passed, 2 skipped**. The four cereal/hardware files listed in `AGENTS.md` were omitted. Ruff and whitespace checks passed.
- New regression coverage resolves the actual manager predicate/registration and verifies an onroad drive without a route/download does not start routing. Tests cover completed/new/paused map jobs, preview wakes, bounded startup failures, rollback precedence, lightweight manager imports, actual broker/socket startup, idle exit and restart.
- On the parked comma, an isolated copy ran the production broker and map loop with an empty private store. The no-route drive gate was false. A preview woke it and received the expected `runtime_missing` response after **2.031 s**. Its observed RSS was **42,132 KiB**. With the production 120-second timeout, it exited with code zero after **120.585 s**, removed the socket and left the manager gate false. `TANDEM_ROUTING=0` also left the gate false. No live destination, map packages or checkout were changed.

The device check verifies lifecycle, not a native route or memory pressure alongside `modeld`. It does not establish a new routed-drive RAM peak or fix the separate `starpilot_process` growth.

## Owner check after updating valhalla

1. Restart openpilot while parked. With no destination or pending map update, Device › RAM/process inspection should show no `tandem_routingd` process.
2. Preview a saved destination with offline routing selected. The first preview may include broker startup; it should otherwise work normally. Dismiss without starting navigation. After about two minutes, the broker should be gone.
3. Start a route, then end it. Confirm guidance/reroutes work and the broker disappears about two minutes after the route ends. Compare RAM during a supervised drive; this change does not remove navigation's required working memory.
4. Start a map update while parked on Wi-Fi. Confirm it starts routing, follows the existing pause/resume gates and completes. Once the job is terminal and no route/preview needs it, the broker should stop after the idle grace.
