# Turn chip retained after a hidden turn alert

November 4, 2026, owner report on `valhalla` at `b334e9f6`.

## Drive evidence

The latest drive, `00000555--8dcecb996c`, lasted 1,315.8 seconds. Its qlogs contained 2,627 `starpilotPlan` samples and 13,096 samples each of `carState`, `selfdriveState` and `starpilotSelfdriveState`.

- At 497.71 seconds, the planner reported `turningLeft` while the left signal was on.
- At 502.71 seconds, the live turn event cleared. Both alert messages still carried `turningLeft/warning`, with `alertSize = none` and empty text.
- That empty alert type remained through the rest of the drive, about 13 minutes 33 seconds, including straight driving without a signal and a later right signal. A brief actual right lane-change alert temporarily replaced the normal alert; the StarPilot alert remained empty with the old left-turn type.

The extracted report contains relative times, turn/alert state, speed, signals and steering angle, without location data. The local diagnostic artifact is `tools/out/turn-chip-investigation.json` (ignored by git).

## Cause and correction

StarPilot's hidden turn-banner callback returns the shared `EmptyAlert`. Its event construction then sets that object's `alert_type`. Later, an alert manager with no active alert returns the same shared object, which can retain the old type even though its size is `none` and its text is empty.

Tandem's `onroad/status.snapshot` supplemented live planner events with alert names to retain short events the UI might miss, such as Light is green and Car ahead moved. It accepted any nonempty alert type. The stale empty turn alert therefore refreshed the chip every frame, preventing its normal two-second hold/fade from expiring. A stale left alert could also win over a new right-turn event.

The correction accepts an alert-derived chip reason only when `alertSize` is not `none`. Live planner turn events still supply their own reasons, including when the owner hides StarPilot's turn banner. Existing chip wording, appearance, priorities and hold/fade behavior apply. The fix is entirely owned; no upstream event or control logic changes.

## Verification

The new host regression fails before the correction. It covers both directions and both alert services, holds a completed turn for the normal interval, clears it despite an empty stale alert, and accepts a later opposite turn. Additional cases preserve active green-light, lead-departure, low-memory and blind-spot alerts while rejecting their empty counterparts.

On an isolated device copy, **84 onroad/chip tests passed**, including two tests that reproduce the actual shared-`EmptyAlert` mutation and encode/decode the result through the device's real message schemas. Live checkout, params and driving state were not changed. A new drive is still needed to confirm the owner-visible result after updating the branch.

After merging the current release RAM diagnostics, the host UI suite passed **733 tests, with two skips** and the four cereal/hardware files listed in `AGENTS.md` omitted. The host routing suite passed **187 tests** with its usual compiled/hardware-dependent modules omitted. Ruff and whitespace checks passed.
