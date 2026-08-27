# Discovery workbench

This workbench exercises SerialOSC discovery without touching a real device or
the live SerialOSC daemon. It covers discovery transport, callback ownership,
notification re-arming, registry state, and explicit selection.

It does **not** send `/sys/host`, `/sys/port`, `/sys/prefix`, LED, or ring
messages. A discovered device is not a claimed device.

## Ports

- `12002` — live SerialOSC discovery; the simulator refuses this port.
- `12012` — fake discovery server used by the help and smoke patches.
- `17001` and `17002` — fake per-device servers for Step 2 session work.
- `17779` — local PlugData callback used by the examples.
- `17780` and `17781` — session callbacks used by the Step 2 workbench.
- `17850` — read-only live discovery monitor.
- `17900` — loopback-only control inlet for the live Grid workbench.

The fake server binds only to `127.0.0.1` by default. It cannot see or modify a
USB device.

## Interactive run

From the repository root, start the simulator:

```sh
python3 tools/fake_serialosc.py
```

It starts with two records:

```text
m100  monome 128  17001
m200  monome 256  17002
```

Open `monome-discovery-help.pd` in PlugData and click `start`. Expected console
events include:

```text
callback starting 17779
callback ready 17779
scan begin
device added m100 monome 128 17001
device added m200 monome 256 17002
scan end
```

Discovery does not select either record. Choose a device explicitly from the
registry-backed menu. Numbered `select_index` messages remain useful for
automated smoke patches, but they are not the user-facing selection path.

The simulator accepts these commands on standard input:

```text
devices
order m200 m100
duplicate m100 2
remove m100
add m100 "monome 128" 17001
state m100
displace m100 127.0.0.1 19999 /rival
reset
quit
```

`/serialosc/notify` is one-shot, like the real protocol. After `add` or
`remove`, `monome-discovery` immediately re-scans and re-arms notification.

## Automated PlugData smoke patch

With the simulator running, open `monome-discovery-smoke.pd`. Its `loadbang`
performs one scan, explicitly selects the first registry record, probes the
native menu input, and prints a registry snapshot.

The successful transport/state portion ends with two snapshot records and:

```text
selected m100 monome 128 17001
```

The separate `smoke-popmenu` trace is retained as an acceptance gate. It fails
on stable 0.9.3 but passes on the accepted official 0.9.4 nightly at commit
`6bb2b60c8`: two items populate, selection changes the label, and index `0` is
emitted.

Real SerialOSC sends full add/remove tuples:

```text
/serialosc/add SERIAL MODEL PORT
/serialosc/remove SERIAL MODEL PORT
```

`monome-discovery` preserves the full tuple in its status stream but reduces a
remove to `remove SERIAL` before it reaches the registry. The fake server uses
the same real wire shape so this normalization cannot regress behind a
serial-only simulator.

## Callback collision

`start` first binds the callback and sends an instance-specific self-probe.
Discovery begins only after that probe returns. If another process owns the
port, the abstraction emits:

```text
error callback_unavailable 17779
```

It does not claim readiness or send a discovery request. The Python test suite
also verifies the same collision rule at the socket boundary.

The simulator also implements fake per-device `/sys/*` settings for the
session lifecycle workbench. See `docs/SESSION-WORKBENCH.md`. Those endpoints
remain loopback-only and do not change discovery's passive contract.

## Command-line tests

```sh
lua tests/registry_spec.lua
python3 -m unittest -v tests/fake_serialosc_spec.py
luac -p monome_registry.lua monome-registry.pd_lua
```

The Python socket tests require permission to bind local UDP ports. These tests
do not touch live port `12002`.

## Current acceptance boundary

Passed:

- ordered and duplicate discovery replies;
- one-shot add/remove notification and explicit re-arm;
- stable-ID registry ordering and selection preservation;
- selected-device removal and `selection_lost` reporting;
- real PlugData callback bind, self-probe, scan, hot-remove, and hot-add;
- explicit callback-collision failure in PlugData;
- dynamic `else/popmenu` population and output in the accepted nightly;
- full real add/remove tuple normalization;
- live SerialOSC discovery of a physical legacy 128, modern zero Grid, and
  four-ring Arc;
- concurrent stable-ID registry population for both physical Grids;
- selection preservation when the second device reorders the menu;
- remove/add notification and isolated menu cleanup in both removal
  directions; and
- same-ID rediscovery of each device during the simultaneous three-device
  removal/recovery run documented in `docs/THREE-DEVICE-ACCEPTANCE.md`; and
- concurrent Bitwig and standalone registries on isolated discovery callbacks
  while all three physical devices remained visible. The standalone contender
  could claim the legacy Grid without changing either registry's stable-ID
  projection.

No discovery-specific Bitwig gate remains. The failed full-device-deactivation
case is a plug-in-host/session cleanup problem, not a discovery failure; see
`docs/PLUGDATA-BITWIG-AB.md`.
