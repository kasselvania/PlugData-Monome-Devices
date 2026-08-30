# Session lifecycle workbench

`monome-session` owns one explicitly selected SerialOSC device lifecycle. It
does not discover or auto-select devices. It probes current settings without
changing them, claims only on command, verifies every ownership assertion from
readback, detects displacement, and releases only while the destination still
matches the session.

This workbench uses fake per-device servers. It does not open USB devices or
send anything to live SerialOSC discovery port `12002`.

## Destination policies

`monome-session` retains the accepted legacy behavior by default. Before a
probe, a caller may explicitly select:

```text
protocol legacy
protocol lease
```

Lease policy sends both non-mutating `/sys/info` and `/sys/lease/info` during
probe. Missing lease capability fails closed; it never falls back to legacy.
`claim` acquires only a `free` destination. A probed `legacy` destination
requires the separate `takeover` command, and a different active lease is
always refused. A verified lease uses a 6000 ms TTL renewed every 2000 ms.
Release is complete only after `/sys/lease/released` (or `no_lease`) is
followed by an independent `free`, port-`0` state readback.

The live Grid and Arc slots opt into lease policy automatically. Existing fake
smoke patches remain on legacy policy as the regression lane.

## Ports

- `12012` — fake discovery server;
- `17001` — fake `m100` device server;
- `17002` — fake `m200` device server;
- `17780` — first PlugData session callback;
- `17781` — second callback used by the contention test.

The simulator refuses to bind live discovery port `12002`.

## Contract

Commands accepted by `monome-session <callback-port> <info-window-ms>`:

```text
start
select <serial-id> <model> <device-server-port>
prefix <osc-prefix>
protocol <legacy|lease>
probe
claim
takeover
check
release
deselect
remove <serial-id>
stop
bang
```

The abstraction's second inlet accepts prefixed capability OSC from the Grid
or Arc owner. It is emitted only while the session is verified `connected` and
only when the address begins with the session's exact prefix plus `/`. Direct
capability output while available, probing, displaced, or released fails
closed.

The required nominal order is:

```text
start -> select -> probe -> claim -> check -> release -> stop
```

`probe` sends only `/sys/info <host> <port>`. It cannot change the device's
application destination.

`claim` requires a completed probe. It reserves the serial ID inside the
current PlugData process, sends `/sys/prefix`, `/sys/host`, and `/sys/port`,
then requests `/sys/info` again. State becomes `connected` only if serial ID,
host, port, and prefix all match.

`check` requests another non-mutating `/sys/info`. A mismatch changes state to
`displaced` and drops the local ownership assertion.

`release` first performs the same ownership readback. It sends `/sys/port 0`
only when the readback still matches. If another application has displaced the
session, release reports `release_skipped` and does not overwrite the other
destination.

Step 2 owns destination lifecycle only. The Grid capability layer now darkens
its valid surface before requesting release. The session layer still does not
guess a device's LED protocol; Arc will own the equivalent ring cleanup.

## Nominal PlugData run

Start the simulator from the repository root:

```sh
python3 tools/fake_serialosc.py
```

Open `monome-session-smoke.pd`. The patch automatically binds, selects `m100`,
probes, claims, verifies, releases, prints a snapshot, and stops.

Required terminal events include:

```text
state available probed
probed m100 127.0.0.1 0 /monome 0 16 8
state connected verified_claim
connected m100 127.0.0.1 17780 /monome 0 16 8
state connected verified
state available released
released m100 verified
snapshot available ready m100 monome 128 17001 /monome 0
transport stopped
```

In the simulator terminal, `state m100` must then report destination port `0`.

## Displacement and safe release

Open `monome-session-displacement-smoke.pd`. Before its four-second `check`,
run:

```text
displace m100 127.0.0.1 19999 /rival
```

Required results:

```text
state connected verified_claim
state displaced destination_changed
displaced m100 destination_changed ... 127.0.0.1 19999 /rival
state available release_skipped
release_skipped m100 displaced
```

After the patch stops, `state m100` must still show port `19999` and prefix
`/rival`. That readback proves release did not overwrite another application's
destination. Run `reset` before another nominal test.

## Same-process contention

Open `monome-session-contention-smoke.pd`. Two session instances probe `m100`
using callback ports `17780` and `17781`. The first starts claiming 30 ms before
the second.

Required result:

```text
contention-first: state connected verified_claim
contention-second: error claimed_in_process m100
contention-first: state available released
```

The second instance emits no claim OSC. This guard is process-local; external
applications are detected by readback rather than by a nonexistent SerialOSC
lock.

## Callback collision

If another process owns `17780`, opening the nominal smoke patch must report:

```text
error callback_unavailable 127.0.0.1 17780
error transport_not_ready
```

It must send no probe or claim to the device server.

## Automated tests

```sh
lua tests/session_spec.lua
lua tests/lease_session_spec.lua
python3 -m unittest -v tests/fake_serialosc_spec.py
python3 -m unittest -v tests/pd_patch_spec.py
luac -p monome_session.lua monome-session-core.pd_lua
```

The session core suite covers non-mutating probe, probe-before-claim, verified
claim, claim mismatch, displacement, verified release, release after
displacement, process-local contention, removal, stale self-destination
recovery after same-ID reconnect, refusal to overwrite a rival destination,
callback readiness, and incomplete readback. Python tests exercise the actual
loopback OSC wire behavior of the fake device server.

The lease suite separately covers unsupported capability, free acquire,
explicit legacy takeover, rival refusal, exact grant and release readback,
renewal, renewal timeout, rejection, lost notification, and grant timeout.

## Acceptance boundary

Passed in the accepted PlugData nightly `0.9.4` across 2026-08-25 and
2026-08-26:

- real callback bind and self-probe;
- non-mutating `/sys/info` probe;
- claim followed by exact settings readback;
- connected-state verification;
- simulated external displacement detection;
- release refusal after displacement with rival state preserved;
- verified release to port `0`;
- same-process duplicate-claim refusal;
- callback collision refusal before device traffic;
- capability OSC refusal before a verified claim or outside the exact prefix;
- physical legacy-128 non-mutating probe and exact claim readback;
- physical legacy-128 orderly release with verified destination port `0`;
- released-state `/sys/info` readback of port `0` without a worker crash using
  the project SerialOSC patch;
- claimed-device hot-unplug with local session and registry teardown;
- physical held-key synthesis (`key 0 0 0 synthetic`) during disconnect; and
- the same legacy-128 lifecycle on the installed production LaunchAgent;
- physical zero-Grid non-mutating probe, exact 16-by-16 claim readback, orderly
  release, and released destination port `0` readback;
- physical zero-Grid claimed hot-unplug with held-key synthesis and worker
  teardown while the production LaunchAgent remained alive; and
- same-ID zero-Grid rediscovery, re-probe, re-claim, output, and final release;
- simultaneous zero and legacy claims on callback ports `17780` and `17781`,
  with distinct 16-by-16 and 16-by-8 readback;
- surviving-session verification and live output after removing either Grid;
- same-ID rediscovery, re-probe, and re-claim in both pair-removal directions;
- isolated orderly release of each Grid to port `0` while the other session
  remained verified;
- physical Arc probe, claim, ring output, signed encoder input, all-dark
  cleanup, verified release, and same-ID reconnect; and
- physical active-claim Arc unplug followed by exact stale-self-destination
  recovery and verified port-`0` readback while both Grids remained present;
- simultaneous physical claims for zero, legacy 128, and Arc on three distinct
  callback ports, with isolated visible output and input routing;
- active removal and same-ID recovery of each of the three devices while both
  surviving sessions retained state and passed fresh ownership checks; and
- independent dark cleanup, release, and final port-`0` readback for all three
  devices. See `docs/THREE-DEVICE-ACCEPTANCE.md`;
- the same three callback routes inside Bitwig CLAP, including removal and
  stable-ID recovery of every device with both survivors unchanged; and
- deliberate legacy-Grid displacement from Bitwig `17780` to standalone
  `18780`: Bitwig reported `displaced destination_changed`, detached
  capability output, refused an LED update, skipped release, and left the
  rival destination untouched. The standalone owner released to port `0`,
  after which Bitwig freshly probed and reclaimed the device;
- physical legacy-128 lease claim and renewal beyond the original daemon TTL;
- PlugData-routed legacy-128 output and exact top-left press/release input;
- orderly lease darkening and independently verified release to free port `0`;
  and
- abrupt PlugData standalone process death while the Grid remained lit and
  leased, followed by automatic daemon expiry, visible full darkness, and
  independent free port-`0` readback;
- the equivalent isolated lease lifecycle on physical zero Grid `m23215901`,
  including renewal, full 16-by-16 output, exact bottom-right input, orderly
  dark/release, and automatic all-dark expiry after abrupt PlugData death.

The remaining macOS host lifecycle gap is Bitwig process death, not standalone
process death or displacement handling. In the accepted pre-lease Bitwig lane,
full device deactivation terminates the plug-in host before it can darken or
release, so stable SerialOSC retains a stale destination. The lease candidate
has closed the equivalent physical standalone failure, but it has not yet
passed the Bitwig process-death gate. See
`docs/PLUGDATA-BITWIG-AB.md`.
