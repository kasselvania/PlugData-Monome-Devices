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
workbench without callback collisions.

## Physical acceptance

The physical four-ring Arc passed its PlugData standalone gate on 2026-08-26:

- stable ID `m1001113`, model `monome arc`, device-server port `18226`;
- `/sys/info` reported host `127.0.0.1`, rotation `0`, and the Arc-specific
  zero-by-zero size `0 0`;
- the initial non-mutating probe preserved the pre-existing `/bitwig:19996`
  destination before the explicit claim;
- the verified claim moved the destination to `127.0.0.1:17782` with prefix
  `/monome` and initialized all four rings dark;
- all-ring level output, isolated ring `0`/position `0` and ring `3`/position
  `63` output, positive encoder-`0` deltas, and negative encoder-`3` deltas
  were physically confirmed;
- orderly release sent four dark maps before verified `/sys/port 0`;
- released unplug/reconnect restored the same stable identity at port `0`;
- active-claim unplug removed only the Arc while both Grids remained
  registered and capability commands failed closed with `no_device_selected`;
  and
- active-claim reconnect retained SerialOSC's stale `17782` destination. A
  fresh probe plus guarded release verified that it still matched this
  workbench, then set and read back port `0`.

That last case is now a session regression: a release from `available` may
adopt a stale destination only when fresh `/sys/info` matches the session's
bound host, callback port, prefix, and stable ID. It performs a second readback
before sending `/sys/port 0`. A nonzero destination belonging to another app
is reported as `release_skipped destination_not_owned` and is never changed.

Key input is not required for this buttonless Arc. The Arc subsequently passed
simultaneous standalone acceptance with both Grids, including isolated routing,
survivor checks, and removal/recovery of every device. See
`docs/THREE-DEVICE-ACCEPTANCE.md`. It then passed the same bounded Bitwig CLAP
surface: four independent ring markers, signed encoder input, removal/recovery
with both Grids unchanged, exact stale-self callback recovery, and final
all-dark release to port `0`. Bitwig's separate full-device-deactivation gap is
documented in `docs/PLUGDATA-BITWIG-AB.md`.

## Lease-candidate standalone record

On 2026-08-29, the same physical Arc passed the isolated opt-in lease lifecycle
with PlugData 0.9.4 and SerialOSC candidate revision `7187832`:

- macOS reported USB serial `m1001113` at
  `/dev/tty.usbserial-m1001113`, while SerialOSC exposed model `monome arc` on
  device-server port `18226`;
- the first candidate build did not discover the Arc even though macOS did.
  Its IOKit enumeration reused an in/out property-buffer length after shorter
  modem paths, so the later, longer FTDI Arc path was omitted. Revision
  `7187832` resets that length for every device and checks the property read;
- opening `monome-arc-live.pd` bound only its expected control, discovery, and
  Arc callback ports and did not auto-claim;
- an independent probe reported the exact legacy destination
  `127.0.0.1:17782`; the operator explicitly approved takeover before PlugData
  changed it;
- the verified lease renewed beyond its original six-second TTL at callback
  port `17782`;
- all four rings visibly lit at level 4, with independent markers at ring `0`,
  position `0`, level 15 and ring `3`, position `63`, level 10;
- PlugData printed positive ring-`0` deltas and negative ring-`3` deltas from
  the buttonless physical encoders;
- orderly release visibly darkened every ring before independent readback
  reported free port `0`;
- after a fresh claim settled, all four rings lit again. `SIGKILL` terminated
  only the verified PlugData process, and immediate readback still reported a
  live lease with about 4.4 seconds remaining; and
- the daemon then expired the abandoned lease, all four rings visibly went
  dark by themselves, and independent readback returned free port `0`.

The candidate log independently recorded `lease granted by takeover`,
`lease released`, a fresh `lease granted`, and `lease expired`. This accepted
the Arc's isolated standalone lease lifecycle. At that point it did not yet
accept the simultaneous lease matrix, Bitwig process death, or Steam Deck
behavior.

The Arc subsequently passed the 2026-08-29 lease-candidate matrix with both
Grids in one PlugData process. Its lease, ring output, and encoder route stayed
isolated through removal/recovery of every device. Arc reconnect returned the
same stable ID as free port `0`, required explicit reselection and reclaim, and
did not disturb either Grid. A final shared-process `SIGKILL` left all three
leases active briefly before SerialOSC expired and darkened each surface. See
`docs/THREE-DEVICE-ACCEPTANCE.md`.

The Arc then passed the macOS Bitwig host-death gate on 2026-08-31. Its
`17782` lease expired when full device deactivation killed the shared PlugData
host, all four rings auto-darkened, and fresh readback returned port `0`.
Reactivation required explicit selection, probe, and claim; positive ring-`1`
input remained isolated. Steam Deck acceptance remains open.
