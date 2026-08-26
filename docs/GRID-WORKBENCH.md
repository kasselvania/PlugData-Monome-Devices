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
- one real hot-add with the same stable identity restored.

The real `/serialosc/remove` arrived as `SERIAL MODEL PORT`, exposing and then
closing a simulator mismatch: discovery now preserves the full status tuple
while sending only `remove SERIAL` to the registry.

## Incomplete physical gates

The final claimed-unplug test did not run. During the attempted setup through
a CalDigit dock, the Grid remained visible in macOS USB and `/dev`, but
SerialOSC's per-device process exited. Restarting the existing user service
recovered the device briefly; it then disconnected again while the nodes
remained. Official source confirms that the supervisor reports this child exit
but does not respawn it until the detector receives a new match or restarts.
With no operator present to re-seat the cable, that is a stopped physical gate,
not a pass.

Still required:

- legacy 128 unplug while claimed, including local detach and held-key release;
- modern 256 Grid probe, 16-by-16 maps, keys, release, and hot swap;
- Grid pair tests in both removal directions;
- Grid plus Arc, then all three devices;
- standalone-versus-Bitwig CLAP contention and lifecycle tests.

Do not infer any of those results from the fake server or the completed
legacy-128 nominal run.
