# Grid workbench

The Grid layer owns normalized keys, LED state, bounded map output, and
all-dark cleanup. It does not discover or claim a device by itself.
`monome-grid-session` composes it with the explicit `monome-session` lifecycle
so capability OSC cannot bypass verified session ownership.

## Grid contract

`monome-grid` accepts LED commands on its left inlet:

```text
led X Y LEVEL
level X Y LEVEL
all LEVEL
clear
map X_OFFSET Y_OFFSET LEVEL_0 ... LEVEL_63
flush
prepare_release
snapshot
```

Levels are integers from 0 through 15. Coordinates are zero-based and bounded
by the dimensions read from `/sys/info`. Supported dimensions are multiples of
8 up to 16-by-16; the current hardware lanes are 16-by-8 and 16-by-16.

The middle inlet receives raw device OSC, and the right inlet receives session
status. Grid key output is normalized as:

```text
key X Y STATE
```

Duplicate key states are ignored. Detaching with held keys emits synthetic
release events before the surface is discarded.

Normal LED edits update an in-memory framebuffer. A 16 ms metro flushes only
dirty 8-by-8 quadrants with `/grid/led/level/map`. `prepare_release` sends zero
maps for every valid quadrant before it asks the session to verify ownership
and send `/sys/port 0`.

## Deterministic fake runs

Start the loopback-only simulator:

```sh
python3 tools/fake_serialosc.py
```

Then open one smoke patch in PlugData:

- `monome-grid-smoke.pd` — one 16-by-8 Grid;
- `monome-grid-256-smoke.pd` — one 16-by-16 Grid;
- `monome-grid-dual-smoke.pd` — independent 128 and 256 sessions.

The fake server supports:

```text
key SERIAL X Y STATE
grid SERIAL
state SERIAL
```

The smoke runs prove dimensions, framebuffer orientation, corner LEDs, key
press/release, independent dual-device state, full-surface darkness, and
verified destination release. The simulator refuses live discovery port
`12002` and never opens USB hardware.

## Live workbench

`monome-grid-live.pd` is the physical-device workbench. It contains two
explicit slots, A and B, backed by registry-populated device menus. Loading the
patch starts callbacks and discovery only; it does not auto-select or claim.

Useful observation and control commands are:

```sh
python3 tools/serialosc_monitor.py
python3 tools/live_grid_events.py --count 2 --timeout 30
python3 tools/live_grid_control.py discovery rescan
python3 tools/live_grid_control.py a_select 0
python3 tools/live_grid_control.py a_session probe
python3 tools/live_grid_control.py a_session claim
python3 tools/live_grid_control.py a_grid all 4
python3 tools/live_grid_control.py a_grid led 0 0 15
python3 tools/live_grid_control.py a_session check
python3 tools/live_grid_control.py a_session release
```

Ports are loopback-only:

- `17779` discovery callback;
- `17780` and `17781` slot callbacks;
- a fresh ephemeral loopback port for each read-only discovery-monitor run;
- `17900` live workbench control; and
- `17910` machine-readable normalized A/B key events.

The monitor deliberately asks the OS for a fresh callback port on every run.
SerialOSC notifications are one-shot and have no unregister message. Reusing a
fixed port while an earlier notification is still pending can deliver both the
old and new notification to the later monitor and make one physical event look
duplicated. `--callback-port` remains available for a deliberately isolated
run, but routine acceptance should use the automatic default.

`live_grid_events.py` binds only loopback and exits after the requested event
count. Its default count of two captures one physical key press and release as
exact `a_key X Y 1` and `a_key X Y 0` (or `b_key ...`) messages. It observes
the patch's normalized output and never discovers, selects, claims, lights, or
releases hardware.

The command-line selector exists for repeatable automation. A person using the
patch should select the visible stable-ID entry from the menu.

### Isolated standalone contender

`monome-grid-contender-live.pd` is a test-only second-application workbench for
deliberate SerialOSC displacement. It reuses the same explicit Grid slot but
cannot collide with the normal live patch's local sockets:

- `18779` discovery callback;
- `18780` Grid callback; and
- `18900` control inlet.

Pass `--port 18900` to `tools/live_grid_control.py` when controlling it:

```sh
python3 tools/live_grid_control.py --port 18900 a_select 0
python3 tools/live_grid_control.py --port 18900 a_session probe
python3 tools/live_grid_control.py --port 18900 a_session claim
python3 tools/live_grid_control.py --port 18900 a_grid all 6
python3 tools/live_grid_control.py --port 18900 a_grid led 8 3 15
python3 tools/live_grid_control.py --port 18900 a_session release
```

The index is illustrative; inspect the visible stable-ID menu before selecting.
This patch intentionally changes a device's one cooperative SerialOSC
destination. It is an acceptance harness, not a coexistence mechanism.

## Physical legacy-128 record

Passed on 2026-08-25 in PlugData standalone with Homebrew SerialOSC 1.4.7 and
the accepted PlugData nightly at commit `6bb2b60c8`:

- live discovery and stable-ID menu population;
- explicit selection and non-mutating probe;
- 16-by-8 dimension readback;
- verified claim at the slot's exact host, callback port, and prefix;
- all LEDs at low brightness;
- top-left and bottom-right levels at distinct values;
- top-left and bottom-right key press and release coordinates;
- all-dark map cleanup before release;
- verified destination port `0` after release;
- registry/session cleanup on hot-remove; and
- one real hot-add with the same stable identity restored;
- `/sys/info` readback of released port `0` without a daemon crash using the
  project SerialOSC patch; and
- claimed hot-unplug with clean device, registry, selection, and process
  teardown, including `key 0 0 0 synthetic` for a physically held top-left
  key.

The real `/serialosc/remove` arrived as `SERIAL MODEL PORT`, exposing and then
closing a simulator mismatch: discovery now preserves the full status tuple
while sending only `remove SERIAL` to the registry.

### Lease-candidate legacy-128 record

Passed on 2026-08-29 with the pinned SerialOSC lease candidate at revision
`6701959e` and the installed PlugData 0.9.4 candidate:

- loading the live patch bound the expected loopback ports but did not
  auto-select or claim;
- explicit discovery, selection, and non-mutating lease probe;
- verified lease claim on callback port `17780`;
- renewal observed beyond the original six-second TTL;
- full 16-by-8 output at level 4 and independently bright top-left output at
  level 15;
- exact top-left `key 0 0 1` and `key 0 0 0` input in PlugData;
- orderly full-surface darkness before verified release to port `0`;
- a second lit claim followed by abrupt termination of only the PlugData
  process, with the destination still leased immediately afterward; and
- automatic daemon expiry, visibly complete hardware darkness, and independent
  free port-`0` readback.

This record accepts the legacy-128 standalone lease lifecycle. It does not
transfer acceptance to the zero Grid, Arc, simultaneous devices, Bitwig, or
Steam Deck.

## Physical modern-256 record

Passed on 2026-08-26 in PlugData standalone with the accepted nightly and the
installed patched production LaunchAgent. SerialOSC identified the device as
`monome zero`, stable ID `m23215901`, in OSC/SerialOSC mode:

- live discovery, explicit selection, and non-mutating probe;
- 16-by-16 dimension readback and verified claim on callback port `17780`;
- all 256 LEDs at low brightness and distinct top-left/bottom-right levels;
- top-left key press and release at coordinate `0 0`;
- all-dark map cleanup and verified destination port `0` after release;
- released-state `/sys/info` readback without a worker crash;
- claimed hot-unplug while top-left was physically held, producing
  `key 0 0 0 synthetic device_removed` before detach;
- clean device-worker exit while the main SerialOSC service remained alive;
- same-ID rediscovery and registry restoration after reconnect; and
- successful re-probe, re-claim, bottom-right LED output, final darkening, and
  orderly release.

No bottom-right key-input claim is made by this record; that coordinate was
used only for LED-output verification.

### Lease-candidate modern-256 record

Passed on 2026-08-29 with the pinned SerialOSC lease candidate at revision
`6701959e` and the installed PlugData 0.9.4 candidate:

- SerialOSC identified `m23215901` as `monome zero` in OSC/SerialOSC mode and
  free at port `0`;
- loading the patch did not auto-claim;
- explicit selection, non-mutating probe, verified lease claim, and renewal
  beyond the original daemon TTL;
- all 256 LEDs at level 4 and the bottom-right LED independently at level 15;
- exact bottom-right `key 15 15 1` and `key 15 15 0` input in PlugData;
- orderly full-surface darkness before verified release to port `0`;
- a second lit claim followed by abrupt termination of only the PlugData
  process, with the destination still leased immediately afterward; and
- automatic daemon expiry, visibly complete hardware darkness, and independent
  free port-`0` readback.

This record accepts the isolated zero-Grid standalone lease lifecycle. It does
not transfer acceptance to Arc, simultaneous devices, Bitwig, or Steam Deck.

## Physical two-Grid record

Passed on 2026-08-26 with the legacy 128 and zero Grid connected concurrently
to the installed production LaunchAgent:

- stable-ID ordering preserved the zero selection when the legacy device was
  added ahead of it in the menu;
- the zero held slot A at `127.0.0.1:17780` with a 16-by-16 surface while the
  legacy held slot B at `127.0.0.1:17781` with a 16-by-8 surface;
- a restored legacy destination on `17780` was observed non-mutatingly, then
  moved to and verified on slot B's `17781` before slot A was claimed;
- the zero displayed a full low-level surface while only the legacy
  bottom-right LED was bright;
- input routed independently as zero slot-A `key 0 0 1/0` and legacy slot-B
  `key 15 7 1/0`;
- unplugging the zero removed only slot A; the legacy retained its LED state,
  passed a fresh ownership check, and accepted another LED update;
- the zero returned with the same stable ID, re-probed and re-claimed on slot A
  without disturbing the legacy;
- unplugging the legacy removed only slot B; the zero retained its framebuffer,
  passed a fresh ownership check, and accepted another LED update;
- the legacy returned with the same stable ID, re-probed and re-claimed on slot
  B without disturbing the zero; and
- each Grid darkened and released independently to port `0`, with the other
  session remaining verified until its own orderly release.

The pair-removal runs did not hold a physical key during unplug; held-key
synthesis was already accepted separately on each single-Grid run.

## Physical three-device record

The zero Grid and legacy 128 subsequently passed alongside the physical
four-ring Arc in the same PlugData standalone process. All three held distinct
verified callback destinations, routed distinguishable output and input, and
survived active removal and same-ID recovery of each other device. Removing
either Grid left the other Grid-plus-Arc pair verified with its visible state
unchanged; removing the Arc left both Grids verified. The three sessions then
darkened and released independently to port `0`.

See `docs/THREE-DEVICE-ACCEPTANCE.md` for the exact identities, routes,
physical observations, recovery sequence, and acceptance boundary.

## Bitwig Grid and contention record

On 2026-08-27, the pinned PlugData CLAP candidate at commit `98ae0f78` ran the
live Grid patch inside Bitwig 6.1. The legacy 128 and zero Grid passed isolated
and simultaneous verified claims on `17780` and `17781`, distinct output and
input, active removal/recovery in both directions, and survivor preservation.
Each reconnect retained its own prior callback; recovery used fresh exact
readback, guarded release to port `0`, and explicit reclaim.

The isolated contender then displaced Bitwig's legacy-Grid route from `17780`
to `18780`. It displayed a separate level pattern and received
`key 8 3 1/0`. Bitwig reported `displaced destination_changed`, detached Grid
output, rejected a new LED command with `grid_not_attached`, and skipped
release. Direct readback remained at `18780`. After the standalone owner
darkened and released to port `0`, Bitwig freshly probed, reclaimed `17780`,
restored output, and received `key 0 0 1/0`.

See `docs/PLUGDATA-BITWIG-AB.md` for the full three-device record and host
lifecycle boundary.

## Lease closure of the Bitwig host lifecycle gate

The earlier claimed-unplug attempt exposed an upstream SerialOSC null-port
crash rather than a USB/dock failure. A valid `/sys/port 0` release left liblo
without a printable port string; the next `/sys/info` passed that null pointer
to `atoi()`. The project patch makes both info readback and configuration write
null-safe. With that build, released-state probe, re-claim, full-grid output,
claimed hot-unplug, and physical held-key synthesis all passed on 2026-08-26.
The held-key run used the installed production LaunchAgent, not the earlier
instrumented build.

Standalone-versus-Bitwig contention passes. The pre-lease full-deactivation
run left SerialOSC pointed at the dead callback and left the Grid lit. The
lease-candidate rerun on 2026-08-31 closed that macOS gap: terminating the
isolated host caused daemon expiry, automatic darkness, and free port-`0`
readback for both Grids and the Arc; a fresh host then started fail-closed.

The exact Steam Deck x86-64 candidate has now passed corresponding bounded
single-device standalone slices for both the legacy 128 and Zero/256. Each
renewed beyond the first TTL, routed full-surface output and exact key input,
darkened before orderly release, expired to visible darkness and free port `0`
after abrupt PlugData death, started a fresh host fail-closed before explicit
reclaim, and survived active-lease unplug/reconnect with same-ID/same-port
return as dark/free before explicit reselection and reclaim. The Arc has also
passed its separate isolated lane.

The same Deck candidate then passed the legacy-plus-Zero simultaneous lane.
Distinct patterns and exact A/B key events stayed isolated on callbacks
`17780` and `17781`. Active removal and same-ID/same-port dark/free recovery
passed in both directions; each survivor retained output, renewal, and a fresh
key event. Pre-reselection output was blocked for each returning Grid,
independent releases left the other device untouched, and shared PlugData host
death expired and visibly darkened both leases. A fresh host started
fail-closed, explicitly recovered both, and released both to free port `0`.

The legacy-plus-Arc lane now also passes. Grid callback `17780` and Arc
callback `17782` renewed independently; distinct output and exact Grid/Arc
input stayed isolated. Active removal/recovery passed in both directions, each
survivor retained output and fresh input, and each returning device stayed
dark/free until explicit reclaim. Reciprocal death of the separate Grid and
Arc workbench processes expired and darkened only the dead process's device
while the survivor continued. Those checks prove process isolation, not the
still-open all-device shared-host-death row.

The Zero-plus-Arc functional lane now also passes isolated output/input,
renewal, removal, explicit recovery, independent release, and reciprocal
separate-process expiry. Arc removal/reconnect preserved Zero unchanged. Zero
removal preserved Arc, but reconnecting Zero physically reset and re-enumerated
the Arc USB device in both tested dock-port orientations. Both devices then
returned dark/free and required explicit reclaim. This documented Zero-boot
dock/power boundary does not support a claim of uninterrupted Arc continuity;
the later M4 run did observe a clean Zero reconnect on the same dock, making
the reset intermittent rather than inevitable.

The all-three shared-host lane now also passes. One PlugData PID owned both
Grid slots and the Arc session. Legacy and Zero renewed on `17780` and `17781`,
with Arc on `17782`; distinct output and exact input stayed isolated. Each
hotplug preserved both survivors, returning devices stayed dark/free until
explicit reclaim, and all three released independently. Killing the one host
expired and visibly darkened both Grids and Arc together. A fresh shared host
started fail-closed, explicitly recovered all three, routed fresh input, and
completed final all-dark release.

The Bitwig Deck row is still required before any complete cross-platform
claim. See
`docs/STEAMOS-LEASE-CANDIDATE.md` and `docs/PLUGDATA-BITWIG-AB.md`.
