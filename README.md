# PlugData Monome Devices

A PlugData-first device layer for Monome Grid and Arc hardware through
[SerialOSC](https://monome.org/docs/serialosc/).

The project is being rebuilt around explicit device selection, observable
connection state, safe hot swapping, and the same patch behavior in PlugData
standalone and its DAW plugins. Vanilla Pure Data compatibility is not a
project goal.

## Current status

The original proof-of-concept patches are preserved under [`legacy/`](legacy/)
for reference, but they are not the architecture of the rebuilt object.

The workbench now contains `monome-discovery`, `monome-registry`,
`monome-session`, and `monome-grid`. Together they:

- include an isolated fake discovery server on loopback port `12012`;
- bind and self-test a real callback before declaring it ready;
- speak the documented SerialOSC list/notify protocol;
- key devices by stable SerialOSC ID;
- never auto-select or claim the first device;
- preserve an explicit selection across rescans;
- removes devices missed by a completed scan;
- emit the documented `clear`/`add`/`set` protocol for PlugData's
  `else/popmenu` object;
- probe selected devices with non-mutating `/sys/info`;
- claim only after explicit selection and a successful probe;
- verify host, port, prefix, and serial ID before reporting `connected`;
- detect another application's destination as `displaced`;
- release with `/sys/port 0` only after ownership still matches;
- refuse two claims for the same serial inside one PlugData process;
- normalize 128 and 256 Grid key events through one capability API;
- coalesce 0-15 LED state into dirty 8-by-8 level maps;
- synthesize releases for held keys when a Grid disappears; and
- darken every valid Grid quadrant before an orderly release.

Discovery, registry selection, hot-remove/hot-add, and callback collision have
been exercised in PlugData. Dynamic `popmenu` population and output pass in the
accepted official 0.9.4 nightly. The stable 0.9.3 build remains a known menu
failure and is not the current workbench target.

The Grid core passes deterministic 128, 256, and dual-device fake-server
acceptance. A physical legacy 128 has passed discovery, explicit selection,
non-mutating probe, verified claim, 16-by-8 sizing, full-surface and corner LED
output, corner key input, orderly darkening, verified release, remove/add, and
claimed hot-unplug cleanup, including a synthetic release for a physically
held key. The apparent CalDigit reconnect failure was traced to a reproducible
SerialOSC 1.4.7 null-port crash after a valid `/sys/port 0` release followed by
`/sys/info`; it was not a USB continuity failure. The project now carries the
narrow source patch and a pinned Apple-silicon service installer, both verified
with the legacy 128. A physical 16-by-16 zero Grid has now passed the same
single-device lifecycle on that installed service: discovery, probe, claim,
full-surface and corner output, key input, dark/release, released-port readback,
held-key hot-unplug, same-ID rediscovery, reclaim, and final release. Two-Grid,
Arc, and Bitwig acceptance are still pending.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the stepped implementation and
acceptance plan and [`docs/DISCOVERY-WORKBENCH.md`](docs/DISCOVERY-WORKBENCH.md)
for discovery. [`docs/SESSION-WORKBENCH.md`](docs/SESSION-WORKBENCH.md) covers
probe, claim, readback, displacement, contention, and safe release.
[`docs/GRID-WORKBENCH.md`](docs/GRID-WORKBENCH.md) covers the Grid API, fake
smoke patches, live controls, and the physical acceptance boundary.

## Requirements

- PlugData official nightly `0.9.4`; known-good commit `6bb2b60c8`
- SerialOSC
- Monome Grid and/or Arc hardware for physical acceptance

On Apple-silicon macOS, use the project installer for the pinned null-port-safe
SerialOSC build. It uses Homebrew libraries but runs one user-owned service;
the stock Homebrew service stays stopped to prevent port contention. See
[`docs/MACOS-SERIALOSC.md`](docs/MACOS-SERIALOSC.md). Launch PlugData as an
application, not by executing its inner Mach-O binary; see
[`docs/PLUGDATA-MACOS.md`](docs/PLUGDATA-MACOS.md).

## Run the current tests

The registry/session cores and fake SerialOSC workbench have no external
dependencies:

```sh
lua tests/registry_spec.lua
lua tests/session_spec.lua
lua tests/grid_spec.lua
python3 -m unittest -v tests/fake_serialosc_spec.py
python3 -m unittest -v tests/pd_patch_spec.py
python3 -m unittest -v tests/macos_serialosc_spec.py
luac -p monome_registry.lua monome-registry.pd_lua \
  monome_session.lua monome-session-core.pd_lua \
  monome_grid.lua monome-grid-core.pd_lua
```

The Python tests bind only ephemeral loopback UDP ports. The simulator itself
refuses live SerialOSC port `12002`.

Run `python3 tools/fake_serialosc.py`, then open
[`monome-discovery-help.pd`](monome-discovery-help.pd) in PlugData for the
interactive workbench. [`monome-discovery-smoke.pd`](monome-discovery-smoke.pd)
runs the same discovery automatically and exposes the current native-menu gate.

For Step 2, open [`monome-session-help.pd`](monome-session-help.pd) for manual
control or [`monome-session-smoke.pd`](monome-session-smoke.pd) for the nominal
automated lifecycle. The contention and displacement smoke patches preserve
the failure-path acceptance cases.

For Step 3, the 128, 256, and dual-device fake runs are
[`monome-grid-smoke.pd`](monome-grid-smoke.pd),
[`monome-grid-256-smoke.pd`](monome-grid-256-smoke.pd), and
[`monome-grid-dual-smoke.pd`](monome-grid-dual-smoke.pd). Use
[`monome-grid-live.pd`](monome-grid-live.pd) only for explicit physical-device
acceptance against live SerialOSC.
