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

Discovery does not select either record. The two numbered controls provide a
temporary direct-selection fallback while the stable PlugData `popmenu` issue
described below remains open.

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

The separate `smoke-popmenu` trace is intentionally retained as an acceptance
gate. On the stable macOS build tested on 2026-08-25, the widget stayed on its
empty label and emitted no value even though the documented `clear`, `add`,
and `set` messages were visible in `smoke-menu`.

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
- explicit callback-collision failure in PlugData.

Still open:

- dynamic `else/popmenu` population/output in the tested stable PlugData build;
- real SerialOSC and physical Grid/Arc acceptance;
- session claim, readback, displacement, and release.
