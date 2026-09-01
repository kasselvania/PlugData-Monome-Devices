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

The accepted pre-lease Bitwig lifecycle had one explicit failure: fully
deactivating the device terminated the isolated PlugData host before it could
darken or release, leaving a stale SerialOSC callback and lit hardware. On
2026-08-31, lease candidate `7187832` closed that exact physical gate. Full
Bitwig deactivation killed the shared PlugData host without an orderly release;
SerialOSC expired all three abandoned leases, visibly darkened both Grids and
all four Arc rings, and returned every destination to free port `0`. A fresh
host then started fail-closed, required explicit reselection/probe/claim, and
renewed all three leases without routine heartbeat console spam.

The pinned macOS lease candidate at SerialOSC revision `6701959e` has now
passed its first direct-daemon physical gate with legacy 128 `m1000853`. After
an operator-authorized takeover of the verified legacy destination, the daemon
granted a three-second lease, lit the full 16-by-8 surface at a low level, and
expired the lease when the harness deliberately sent neither renewal nor
release. The Grid visibly went completely dark, `/sys/lease/lost` arrived, the
daemon recorded the expiry, and an independent probe reported `free` at
`127.0.0.1:0` with no owner. This proves only the legacy-128 direct-daemon
expiry lane; at that point PlugData standalone, Bitwig, the other devices, and
Steam Deck lease acceptance remained open.

An unattended standalone control-plane slice has also passed with the same
candidate and Grid. Opening `monome-grid-live.pd` through LaunchServices bound
the expected local ports without claiming the device. Explicit discovery,
selection, and probe left it free; explicit claim leased it at port `17780`;
and independent reads beyond the original six-second TTL proved that
PlugData's two-second renewals kept arriving. Orderly release returned port
`0`. On a second claim, `SIGKILL` terminated only the test-owned PlugData
process: the immediate readback remained leased, then the daemon expired it and
returned port `0`.

The attended continuation completes the legacy-128 standalone physical gate.
PlugData lit the full Grid dimly, addressed the top-left LED independently, and
printed the exact top-left press and release events while renewals continued.
Its orderly release visibly darkened the full surface before independent free
port-`0` readback. On a final lit lease, `SIGKILL` again left the destination
leased immediately after PlugData died; the Grid then went completely dark by
itself when the daemon expired the lease and returned port `0`. This does not
transfer acceptance to Bitwig, the zero Grid, the Arc, combined devices, or
Steam Deck.

The physical zero Grid `m23215901` has now passed the same isolated standalone
lease lifecycle in OSC/SerialOSC mode. PlugData verified its 16-by-16 surface,
lit all 256 LEDs at level 4, addressed the bottom-right LED independently at
level 15, and printed exact `key 15 15 1` and `key 15 15 0` input while the
lease renewed. Orderly release visibly darkened the full surface and returned
port `0`. A second lit lease remained present immediately after `SIGKILL`, then
the zero went completely dark by itself when the daemon expired it and an
independent probe reported free port `0`.

The current macOS lease candidate is SerialOSC revision `7187832`. It resets
the macOS IOKit serial-property buffer length for every enumerated device; the
previous reuse of a shortened in/out length could omit the later, longer FTDI
path of Arc `m1001113`. With that detector correction, the four-ring Arc passed
the complete isolated PlugData lifecycle: explicit legacy takeover, renewal,
all-ring output, independent first/fourth-ring markers, positive ring-`0` and
negative ring-`3` encoder deltas, orderly all-dark release, and automatic
all-dark expiry after abrupt PlugData death. Independent reads ended at free
port `0`, and the daemon log recorded takeover, release, fresh grant, and
expiry.

The same candidate has now passed the complete simultaneous standalone matrix
with zero `m23215901`, legacy 128 `m1000853`, and Arc `m1001113` in one
PlugData process. Their leases renewed independently on `17780`, `17781`, and
`17782`; visibly distinct output and exact Grid/Arc input stayed isolated.
Unplugging and reconnecting each device left both survivors unchanged. Every
returning USB worker restored the same stable ID as free on port `0`, and
PlugData refused to act until the device was explicitly reselected, reprobed,
and reclaimed. Independent orderly releases passed. A final `SIGKILL` left all
three lit and leased briefly; SerialOSC then expired all three leases, visibly
darkened both Grids and every Arc ring, and returned every device to free port
`0`.

The exact x86-64 SteamOS candidate at revision `7187832` has now passed bounded
single-device Deck slices with legacy Grid `m1000853`, Zero Grid `m2321590`,
and four-ring Arc `m1001113`. Each device passed direct lease expiry and
renew/release plus PlugData fail-closed startup, explicit claim and renewal,
physical output and exact input, orderly dark release, automatic dark/free
recovery after abrupt PlugData death, fresh fail-closed restart, and
active-lease unplug/reconnect with same-ID/same-port dark/free recovery before
explicit reclaim. The Arc lane captured signed ring-`0` and ring-`3` deltas;
its hardware has no encoder switches. SteamOS stayed read-only and SerialOSC
did not restart. See
[`docs/STEAMOS-LEASE-CANDIDATE.md`](docs/STEAMOS-LEASE-CANDIDATE.md).

The same Deck candidate now also passes the legacy-128 plus Zero/256 pair.
Their leases renewed independently on `17780` and `17781`; distinct surface
patterns and exact A/B key events stayed isolated. Active unplug/reconnect in
both directions preserved the survivor's output, input, and lease while the
returning device stayed dark/free until explicit reclaim. Each slot released
without disturbing the other. Killing the shared PlugData process left both
leases briefly active, then SerialOSC expired both, visibly darkened both
Grids, and returned both to free port `0`. A fresh host started fail-closed,
recovered only after explicit selection/probe/claim, and completed final
all-dark release. SteamOS stayed read-only and SerialOSC retained zero
restarts.

The legacy-128 plus Arc pair now also passes. Separate Grid and Arc PlugData
workbenches held renewable callbacks `17780` and `17782`; distinct Grid/ring
patterns, exact Grid key input, and signed Arc encoder input stayed isolated.
Active unplug/reconnect in both directions preserved the survivor's lease,
visible state, and fresh input. Each returning device kept its stable ID and
saved device port, but stayed dark/free and blocked output until explicit
rediscovery, selection, probe, and reclaim. Independent release passed in both
directions. Killing each workbench separately expired and darkened only its
own device while the other process and device continued; fresh processes
started fail-closed before explicit recovery. Because the Grid and Arc ran in
separate PlugData processes, that reciprocal evidence is process isolation,
not the still-required all-device shared-host-death row. SteamOS stayed
read-only and SerialOSC retained zero restarts. Zero-plus-Arc, three-device,
Bitwig, and remaining lifecycle rows remained open at that point.

The Zero/256 plus Arc functional lane now also passes, with one explicit
dock/power boundary. Separate Grid and Arc workbenches held renewable
callbacks `17780` and `17782`; distinct surface/ring patterns, exact Zero key
input, and signed Arc delta input stayed isolated. Removing Zero preserved the
Arc lease, pattern, and fresh input. Removing and reconnecting Arc preserved
the Zero unchanged, and the Arc returned with the same ID and saved port as
dark/free before explicit reclaim. Independent release and reciprocal
separate-process expiry/recovery also passed. Reconnecting the Zero, however,
physically removed and re-added the Arc USB device before the Zero enumerated,
in both tested dock-port orientations. SerialOSC handled that event
fail-closed: both devices returned under their stable IDs and saved ports as
dark/free, rejected preselection output, and recovered only after explicit
selection, probe, and claim. The kernel recorded the Arc USB disconnect and no
over-current warning. This accepts M3 routing and bounded fail-closed recovery;
it does not claim uninterrupted Arc-survivor continuity during Zero boot
insertion. The supported test order is Zero first, then Arc. Three-device,
Bitwig, and remaining lifecycle rows remain open.

The complete committed state can now be emitted as a checksum-addressed
development workbench bundle with `./tools/build_workbench_bundle.sh`. This is
a reproducible continuation baseline, not the final end-user PlugData package;
see [`docs/WORKBENCH-BUNDLE.md`](docs/WORKBENCH-BUNDLE.md). The division between
this device layer, the SerialOSC lease fork, the Steam Deck installer, and the
later musical patches is recorded in [`docs/PROJECT-MAP.md`](docs/PROJECT-MAP.md).

The feature lease workbench now executes the version 1 contract in the fake
server and the opt-in PlugData session path. The live Grid and Arc slots select
lease policy at load; the older smoke patches remain the legacy A/B lane. A
separate, rollback-safe macOS candidate manager now runs the pinned candidate
beside a fully preserved stable installation. Its first direct-daemon physical
expiry gate and the complete isolated PlugData standalone physical lifecycles
for both Grids and the four-ring Arc have passed, as has the full simultaneous
standalone matrix and the full Bitwig plug-in-host-death/restart matrix. The
Steam Deck's bounded single-device direct and PlugData standalone slices for
the legacy 128, Zero/256, and four-ring Arc, including hotplug and host death,
now pass. The three pair lanes now have bounded evidence; Zero-plus-Arc carries
the documented Zero-boot dock reset boundary and does not claim uninterrupted
Arc continuity during that insertion. Three-device, Bitwig, and the remaining
lifecycle matrix stay open. See
[`docs/LEASE-WORKBENCH.md`](docs/LEASE-WORKBENCH.md) and
[`docs/MACOS-LEASE-CANDIDATE.md`](docs/MACOS-LEASE-CANDIDATE.md), plus the
bounded [`docs/STEAMOS-LEASE-CANDIDATE.md`](docs/STEAMOS-LEASE-CANDIDATE.md)
record.

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
  standalone-menu and accepted Bitwig hardware/process-death lane
- PlugData official Debian x64 `0.9.4` nightly identified by metadata commit
  `1c83c0c0` for the bounded SteamOS lane
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
python3 -m unittest -v tests/live_grid_events_spec.py
python3 -m unittest -v tests/live_arc_events_spec.py
python3 -m unittest -v tests/live_serialosc_state_spec.py
python3 -m unittest -v tests/live_serialosc_lease_spec.py
python3 -m unittest -v tests/pd_patch_spec.py
python3 -m unittest -v tests/macos_serialosc_spec.py
python3 -m unittest -v tests/macos_lease_candidate_spec.py
python3 -m unittest -v tests/workbench_bundle_spec.py
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
renewal and release, and verifies that the daemon returns to free port `0`.
The separate `renew-release-test --serial SERIAL` command sends the same
bounded pattern, renews the lease beyond its initial TTL, verifies that exact
ownership remains active, then performs a token-guarded release and verifies
free port `0`. Its defaults exercise the production policy: a 6000 ms TTL,
2000 ms renewal interval, and 8000 ms hold. Arc runs also require
`--arc-rings 2` or `--arc-rings 4`. A verified legacy destination is crossed
only with the separately named `--takeover-legacy` flag after explicit
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
ports so it can later run beside the two-Grid workbench, and mirrors normalized
encoder events to the loopback-only `tools/live_arc_events.py` observer.
