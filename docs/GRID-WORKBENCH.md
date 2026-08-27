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
- `17850` read-only discovery monitor;
- `17900` live workbench control.

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

## Remaining lifecycle gate

The earlier claimed-unplug attempt exposed an upstream SerialOSC null-port
crash rather than a USB/dock failure. A valid `/sys/port 0` release left liblo
without a printable port string; the next `/sys/info` passed that null pointer
to `atoi()`. The project patch makes both info readback and configuration write
null-safe. With that build, released-state probe, re-claim, full-grid output,
claimed hot-unplug, and physical held-key synthesis all passed on 2026-08-26.
The held-key run used the installed production LaunchAgent, not the earlier
instrumented build.

Standalone-versus-Bitwig contention now passes. Full Bitwig device deactivation
does not: terminating the isolated PlugData host leaves SerialOSC pointed at
the dead callback and leaves the Grid lit. Guarded recovery worked, but the
project must not claim crash-safe or plug-in-process-restart-safe cleanup until
that host lifecycle gap is closed.
