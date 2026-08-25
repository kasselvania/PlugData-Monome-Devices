# Session lifecycle workbench

`monome-session` owns one explicitly selected SerialOSC device lifecycle. It
does not discover or auto-select devices. It probes current settings without
changing them, claims only on command, verifies every ownership assertion from
readback, detects displacement, and releases only while the destination still
matches the session.

This workbench uses fake per-device servers. It does not open USB devices or
send anything to live SerialOSC discovery port `12002`.

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
probe
claim
check
release
deselect
remove <serial-id>
stop
bang
```

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

Step 2 owns destination lifecycle only. The Grid and Arc capability layers
will darken their valid LED surfaces before requesting release in Steps 3 and
4. The session layer does not guess a device's LED protocol.

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
python3 -m unittest -v tests/fake_serialosc_spec.py
python3 -m unittest -v tests/pd_patch_spec.py
luac -p monome_session.lua monome-session-core.pd_lua
```

The session core suite covers non-mutating probe, probe-before-claim, verified
claim, claim mismatch, displacement, verified release, release after
displacement, process-local contention, removal, callback readiness, and
incomplete readback. Python tests exercise the actual loopback OSC wire
behavior of the fake device server.

## Acceptance boundary

Passed in PlugData stable `0.9.3` on 2026-08-25:

- real callback bind and self-probe;
- non-mutating `/sys/info` probe;
- claim followed by exact settings readback;
- connected-state verification;
- simulated external displacement detection;
- release refusal after displacement with rival state preserved;
- verified release to port `0`;
- same-process duplicate-claim refusal;
- callback collision refusal before device traffic.

Still open:

- physical Grid and Arc session acceptance;
- Grid key/LED capability;
- Arc encoder/ring capability;
- standalone-versus-Bitwig contention;
- native dynamic device-menu behavior in stable PlugData.
