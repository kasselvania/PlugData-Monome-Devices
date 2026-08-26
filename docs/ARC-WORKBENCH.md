# Arc workbench

The Arc layer owns normalized encoder events, one 64-level framebuffer per
ring, bounded ring-map output, and all-dark cleanup. It does not discover or
claim a device by itself. `monome-arc-session` composes it with the verified
`monome-session` lifecycle so capability OSC cannot bypass session ownership.

## Explicit surface contract

Every Arc object must be created with an explicit ring count:

```text
monome-arc 2
monome-arc 4
monome-arc-session CALLBACK_PORT INFO_WINDOW_MS RINGS
```

Only `2` and `4` are accepted. The layer never guesses a ring count from a
model name or generic `/sys/size` response.

`monome-arc` accepts LED commands on its left inlet:

```text
led RING POSITION LEVEL
level RING POSITION LEVEL
map RING LEVEL_0 ... LEVEL_63
all LEVEL
clear
flush
prepare_release
snapshot
```

Ring and position indexes are zero-based. Positions run from `0` through `63`
and LED levels from `0` through `15`. A map is accepted only after all 64
levels validate.

The middle inlet receives raw device OSC and the right inlet receives session
status. Events are normalized as:

```text
delta RING AMOUNT
key RING STATE
```

Delta is a signed integer. Arc key input is supported for hardware that emits
it; the four-ring Arc available for physical acceptance has no buttons, so its
physical gate covers encoder deltas rather than key presses. Duplicate key
states are ignored. Detaching with a held key emits a synthetic release.

Normal edits update an in-memory framebuffer. A 16 ms metro flushes only dirty
rings using `/ring/map`. `prepare_release` sends a zero map for every declared
ring before asking the session to verify ownership and send `/sys/port 0`.

## Deterministic fake run

Start the loopback-only simulator with an explicitly declared four-ring Arc:

```sh
python3 tools/fake_serialosc.py --with-arc 4
```

Then open `monome-arc-smoke.pd` in PlugData. During its hold window the
simulator accepts:

```text
delta a400 3 -12
arc_key a400 1 1
arc_key a400 1 0
arc a400
state a400
```

The accepted PlugData nightly run on 2026-08-26 proved non-mutating probe,
verified claim, four deterministic dark initialization maps, bounded dirty
ring updates, normalized delta and optional key events, four all-dark release
maps, verified destination port `0`, and transport stop. Independent simulator
readback showed all 256 ring levels at zero after release.

## Live four-ring workbench

Open `monome-arc-live.pd` for physical acceptance. Loading the patch starts its
callback transport and live SerialOSC discovery only. It does not select or
claim a device.

Choose the Arc's visible stable-ID entry from the menu, then run `probe` and
inspect the real model and `/sys/info` response before `claim`. The terminal
control path is:

```sh
python3 tools/live_arc_control.py discovery rescan
python3 tools/live_arc_control.py select INDEX
python3 tools/live_arc_control.py session probe
python3 tools/live_arc_control.py session claim
python3 tools/live_arc_control.py arc all 4
python3 tools/live_arc_control.py arc led 0 0 15
python3 tools/live_arc_control.py arc led 3 63 10
python3 tools/live_arc_control.py session check
python3 tools/live_arc_control.py session release
```

`INDEX` must be the actual Arc entry shown by discovery; do not assume it is
the first device. The workbench's ring count is explicitly fixed at four.

Ports are loopback-only:

- `17778` discovery callback;
- `17782` Arc session callback;
- `17901` live Arc control.

The dedicated ports allow this patch to run beside the existing two-Grid live
workbench for later Grid-plus-Arc and all-three-device acceptance.

## Remaining physical gate

No physical Arc claim is made yet. The first hardware run must record the real
stable ID, model string, `/sys/info` fields, and released destination before
mutating anything. Then it must prove all four rings, distinct ring/position
output, encoder delta routing, all-dark cleanup, verified release, unplug and
same-ID reconnect. Key input is not required for the available buttonless Arc.
