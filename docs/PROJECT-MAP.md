# Monome project map

The work is divided into three related projects with separate authority. The
separation keeps the proven device layer, the SerialOSC protocol change, and
platform installation from becoming one unreviewable package.

## 1. PlugData Monome Devices

Repository: `kasselvania/PlugData-Monome-Devices`

This repository owns the PlugData-facing product:

- discovery and stable device identity;
- explicit selection, claim, displacement detection, and safe release;
- Grid and Arc capability abstractions;
- the fake SerialOSC server and deterministic tests;
- standalone and Bitwig workbench patches; and
- the eventual user-facing Grid and Arc examples.

Commit `ae71bc6` is the accepted pre-lease hardware and Bitwig baseline. It
passes the documented standalone, multi-device, hot-swap, contention, and
bounded Bitwig checks. It does not pass full Bitwig device deactivation:
Bitwig terminates the isolated PlugData host before client cleanup can run.

The complete committed source can be emitted as a development workbench
bundle. That bundle preserves the tests and known failure; it is not the final
user package. See [WORKBENCH-BUNDLE.md](WORKBENCH-BUNDLE.md).

The `feature/serialosc-leases` branch now contains the opt-in PlugData lease
client, renewal timer, explicit legacy takeover command, and fake-daemon
contract tests. Legacy policy remains the default and the physical live slots
opt in explicitly. This is deterministic implementation evidence, not macOS,
Bitwig, or Steam Deck acceptance.

## 2. SerialOSC for Steam Deck

Repository: `kasselvania/serialOSC-steam-deck`

This repository owns SteamOS-safe distribution:

- a rootless build and installation path;
- a user systemd service;
- diagnostics and hardware test tooling;
- immutable-SteamOS boundaries; and
- the physically accepted x86-64 release.

Its current release packages unmodified upstream SerialOSC 1.4.7. That release
remains the stable rollback and must not be silently replaced by an
experimental lease build.

After the lease implementation passes macOS tests, this installer can gain a
separately identified candidate that pins the accepted fork revision. The
installer remains packaging; it does not become the authority for SerialOSC
protocol behavior.

## 3. SerialOSC lease fork

Repository: [`kasselvania/serialosc`](https://github.com/kasselvania/serialosc),
forked from `monome/serialosc`.

This repository owns the smallest upstream-oriented change required for
crash-safe application destinations. Legacy `/sys/port`, `/sys/host`, and
`/sys/prefix` behavior remains available and unchanged. Lease behavior is
opt-in.

The implemented version 1 design specifies:

- an opaque session identity;
- explicit claim, renewal, release, and displacement rules;
- a monotonic expiry deadline;
- safe Grid and Arc darkening on expiry;
- clearing the dead runtime destination without persisting it;
- exact status/readback for persistent versus leased destinations;
- compatibility when a legacy client writes `/sys/port`; and
- event-loop behavior on macOS, Linux/SteamOS, and Windows.

The source fork owns that behavior. Platform installers consume a pinned fork
commit only after its acceptance gates pass.

The version 1 implementation and protocol are recorded on the fork's
[`feature/leased-destinations`](https://github.com/kasselvania/serialosc/blob/feature/leased-destinations/docs/leased-destinations.md)
branch at commit `6701959`. Its timer core, runtime transitions, loopback OSC
wire behavior, legacy compatibility, port-`0` persistence boundary, and idle
event-loop expiry pass automated tests. That revision also normalizes
libmonome's protocol-dependent success returns: series/40h report zero while
mext/OSC report a positive byte count, and only negative values are failures.
The current candidate pin is `7187832`, which adds correct per-device IOKit
property-buffer handling so a short serial path cannot prevent a later, longer
FTDI Arc path from being detected. It is not an upstream release or a physical
acceptance claim.

The PlugData repository carries the macOS acceptance wrapper because that
wrapper owns the known-good local rollback and PlugData/Bitwig test sequence.
It pins the full fork revision, installs beside the stable daemon, and switches
distinct LaunchAgents; it does not own or duplicate lease protocol behavior.

## Delivery order

1. Freeze the current PlugData tree as a reproducible development workbench.
2. Specify lease behavior in a protocol note and executable fake-server tests.
3. Implement the opt-in lease in the SerialOSC fork.
4. Align `monome.session` with lease claim, renewal, status, and release while
   retaining a clearly identified legacy mode.
5. Pass deterministic compatibility and failure tests without hardware.
6. Pass PlugData standalone and Bitwig CLAP lifecycle tests on macOS, including
   actual plug-in-host termination and lease expiry.
7. Build a separately identified SteamOS candidate, then repeat Grid, Arc,
   hot-swap, multi-device, and process-death acceptance on the Steam Deck.
8. Only then publish the end-user PlugData package and begin musical Grid and
   Arc example patches.

## Release boundaries

- A workbench bundle is reproducible development custody, not end-user
  installation acceptance.
- Existing Steam Deck and macOS builds remain rollback evidence while the
  lease candidate is experimental.
- The PlugData package must not claim crash-safe cleanup until both the macOS
  Bitwig and Steam Deck process-death gates pass.
- Legacy SerialOSC clients must behave exactly as before unless they opt into
  the lease extension.
- Public package publication also requires an explicit repository license and
  a final decision about PlugData package/store layout.

## Later creative layer

Once the device and service layers are accepted, music-making patches consume
the public PlugData device API. They do not discover devices, manage leases,
or talk directly to SerialOSC. Initial examples remain:

- a Grid patch that adapts between 128 and 256 surfaces and demonstrates
  momentary and latch interaction; and
- an Arc patch with encoder-driven animation and bounded LED refresh.
