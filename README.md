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
`monome-session`, `monome-grid`, and `monome-arc`. Together they:

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
- optionally probe and claim the versioned SerialOSC lease extension without
  silently falling back when it is unsupported;
- renew leased destinations every two seconds under a six-second daemon TTL;
- require an explicit `takeover` command for a legacy destination;
- claim only after explicit selection and a successful probe;
- verify host, port, prefix, and serial ID before reporting `connected`;
- detect another application's destination as `displaced`;
- release with `/sys/port 0` only after ownership still matches;
- recover a stale self-destination after an active USB unplug only after a
  fresh exact readback, without overwriting another application's destination;
- refuse two claims for the same serial inside one PlugData process;
- normalize 128 and 256 Grid key events through one capability API;
- coalesce 0-15 LED state into dirty 8-by-8 level maps;
- synthesize releases for held keys when a Grid disappears; and
- darken every valid Grid quadrant before an orderly release;
- require an explicit two- or four-ring Arc surface rather than guessing;
- normalize Arc encoder delta and optional key events;
- coalesce Arc LED state into bounded dirty-ring maps; and
- darken every declared Arc ring before an orderly release.

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
held-key hot-unplug, same-ID rediscovery, reclaim, and final release. The two
Grids have also passed simultaneous independent claims, output and input
routing, removal and recovery in both directions, surviving-session checks,
and isolated port-`0` release.

The Arc core, Pd-Lua bridge, session composition, fake device server, smoke
patch, and four-ring live workbench are now implemented. The accepted
standalone PlugData nightly passed the deterministic fake lifecycle, and the
physical four-ring Arc passed discovery, non-mutating probe, verified claim,
independent ring/position output, encoder deltas in both directions, all-dark
cleanup, verified destination port `0`, released reconnect, and active-claim
hot-unplug recovery. The physical reconnect exposed SerialOSC's retained
callback destination; the session now verifies and releases that exact stale
self-destination without touching a rival destination. The two Grids and Arc
have now passed simultaneous standalone claims, isolated output and input,
ownership checks, active removal/recovery in every direction, survivor checks,
and independent release to port `0`. A pinned 2026-06-12 PlugData candidate
now also passes the native discovery-menu smoke plus five Bitwig CLAP and three
VST3 editor close/reopen cycles without restarting either plug-in host. That
candidate now also passes the Monome patch inside Bitwig with stopped
transport, ordinary bypass, fail-closed save/reload and explicit reclaim, one
device, both Grids, all three devices, active hot-swap in every direction,
survivor preservation, deliberate standalone displacement, safe refusal by the
displaced Bitwig session, fresh reclaim, and final all-dark port-`0` cleanup.

The accepted pre-lease Bitwig lifecycle has one explicit failure: fully deactivating the
device terminates the isolated PlugData host before it can darken or release,
leaving a stale SerialOSC callback and lit hardware. Guarded manual recovery
passes; plug-in-process restart safety does not. The lease-enabled daemon and
PlugData session are now implemented and deterministically tested, but this
failure is not closed until the physical Bitwig process-death run passes.

The complete committed state can now be emitted as a checksum-addressed
development workbench bundle with `./tools/build_workbench_bundle.sh`. This is
a reproducible continuation baseline, not the final end-user PlugData package;
see [`docs/WORKBENCH-BUNDLE.md`](docs/WORKBENCH-BUNDLE.md). The division between
this device layer, the SerialOSC lease fork, the Steam Deck installer, and the
later musical patches is recorded in [`docs/PROJECT-MAP.md`](docs/PROJECT-MAP.md).

The feature lease workbench now executes the version 1 contract in the fake
server and the opt-in PlugData session path. The live Grid and Arc slots select
lease policy at load; the older smoke patches remain the legacy A/B lane. A
separate, rollback-safe macOS candidate manager is ready, but the installed
macOS and Steam Deck services are still unchanged. See
[`docs/LEASE-WORKBENCH.md`](docs/LEASE-WORKBENCH.md) and
[`docs/MACOS-LEASE-CANDIDATE.md`](docs/MACOS-LEASE-CANDIDATE.md).

See [`docs/DESIGN.md`](docs/DESIGN.md) for the stepped implementation and
acceptance plan and [`docs/DISCOVERY-WORKBENCH.md`](docs/DISCOVERY-WORKBENCH.md)
for discovery. [`docs/SESSION-WORKBENCH.md`](docs/SESSION-WORKBENCH.md) covers
probe, claim, readback, displacement, contention, and safe release.
[`docs/GRID-WORKBENCH.md`](docs/GRID-WORKBENCH.md) covers the Grid API, fake
smoke patches, live controls, and the physical acceptance boundary.
[`docs/ARC-WORKBENCH.md`](docs/ARC-WORKBENCH.md) covers the explicit Arc API,
fake smoke run, and live controls. The exact simultaneous hardware record is
in [`docs/THREE-DEVICE-ACCEPTANCE.md`](docs/THREE-DEVICE-ACCEPTANCE.md).
The exact moving-nightly-versus-pinned-candidate record is in
[`docs/PLUGDATA-BITWIG-AB.md`](docs/PLUGDATA-BITWIG-AB.md).

## Requirements

- PlugData official `0.9.4` candidate, commit `98ae0f78`, for the current
  standalone-menu and bounded Bitwig hardware lane; full device deactivation
  remains unsupported by the accepted lifecycle record
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
lua tests/lease_session_spec.lua
lua tests/grid_spec.lua
lua tests/arc_spec.lua
python3 -m unittest -v tests/fake_serialosc_spec.py
python3 -m unittest -v tests/live_grid_control_spec.py
python3 -m unittest -v tests/live_serialosc_state_spec.py
python3 -m unittest -v tests/live_serialosc_lease_spec.py
python3 -m unittest -v tests/pd_patch_spec.py
python3 -m unittest -v tests/macos_serialosc_spec.py
python3 -m unittest -v tests/macos_lease_candidate_spec.py
luac -p monome_registry.lua monome-registry.pd_lua \
  monome_session.lua monome-session-core.pd_lua \
  monome_grid.lua monome-grid-core.pd_lua \
  monome_arc.lua monome-arc-core.pd_lua
```

The Python tests bind only ephemeral loopback UDP ports. The simulator itself
refuses live SerialOSC port `12002`.

For an independent, non-mutating readback during physical host tests, run
`python3 tools/live_serialosc_state.py`. It discovers the live devices and
prints each device server plus its current destination, prefix, rotation, and
reported size without claiming or releasing anything.

Against the lease candidate, `python3 tools/live_serialosc_lease.py probe`
adds a non-mutating version/mode/remaining-time readback. Its explicit
`expiry-test --serial SERIAL` command refuses non-free devices by default,
acquires one short lease, sends a bounded test pattern, deliberately omits
renewal and release, and verifies that the daemon returns to free port `0`. Arc runs also
require `--arc-rings 2` or `--arc-rings 4`. A verified legacy destination is
crossed only with the separately named `--takeover-legacy` flag after explicit
operator approval; a different active lease is never crossed.

Run `python3 tools/fake_serialosc.py`, then open
[`monome-discovery-help.pd`](monome-discovery-help.pd) in PlugData for the
interactive workbench. [`monome-discovery-smoke.pd`](monome-discovery-smoke.pd)
runs the same discovery automatically and exposes the current native-menu gate.

For Step 2, open [`monome-session-help.pd`](monome-session-help.pd) for manual
control or [`monome-session-smoke.pd`](monome-session-smoke.pd) for the nominal
legacy automated lifecycle. Use
[`monome-session-lease-smoke.pd`](monome-session-lease-smoke.pd) for the
lease-capable fake-server lifecycle. The contention and displacement smoke
patches preserve the legacy failure-path acceptance cases.

For Step 3, the 128, 256, and dual-device fake runs are
[`monome-grid-smoke.pd`](monome-grid-smoke.pd),
[`monome-grid-256-smoke.pd`](monome-grid-256-smoke.pd), and
[`monome-grid-dual-smoke.pd`](monome-grid-dual-smoke.pd). Use
[`monome-grid-live.pd`](monome-grid-live.pd) only for explicit physical-device
acceptance against the lease-enabled SerialOSC candidate. Its slots fail closed
if lease capability is absent and expose `takeover` separately from `claim`.
Use
[`monome-grid-contender-live.pd`](monome-grid-contender-live.pd) only for a
deliberate second-application displacement test; its isolated control port is
selected with `tools/live_grid_control.py --port 18900`.

For Step 4, start the simulator with `--with-arc 4` and open
[`monome-arc-smoke.pd`](monome-arc-smoke.pd). Use
[`monome-arc-live.pd`](monome-arc-live.pd) only for explicit four-ring Arc
physical acceptance against the lease candidate. It uses separate loopback
ports so it can later run beside the two-Grid workbench.
