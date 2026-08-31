# macOS SerialOSC lease candidate

The lease daemon is installed beside the accepted null-port-safe SerialOSC
build. It has a different binary root, LaunchAgent label, log, metadata file,
and checksum manifest. Preparing it does not stop or replace the running
stable service.

Pinned source:

- repository: `kasselvania/serialosc`;
- revision: `7187832c349202b1a94a9b10080ae57d40069946`;
- reported version: `serialoscd 1.4.8 (7187832)`; and
- protocol: opt-in leased destinations version 1.

This remains an acceptance candidate, not an upstream SerialOSC release.

## Prepare without changing the service

From this repository, either build from the pinned remote:

```sh
./tools/macos_serialosc_lease_candidate.sh prepare
```

or from an exact clean local checkout of the fork:

```sh
./tools/macos_serialosc_lease_candidate.sh prepare /absolute/path/to/serialosc
```

The candidate manager verifies the full Git revision, checked-out optparse
submodule, native ARM64 output, embedded short revision, and SHA-256 hashes.
It installs the candidate below:

```text
~/Library/Application Support/PlugData Monome Devices/
  serialosc-lease-candidate/7187832/
```

The accepted build remains untouched at `serialosc/`.

## Inspect the boundary

```sh
./tools/macos_serialosc_lease_candidate.sh status
```

Before first activation, the expected state is:

- accepted stable service loaded;
- lease candidate prepared but stopped; and
- exactly one stable daemon owning UDP `12002`.

## Activate for physical acceptance

First quit PlugData standalone and close or deactivate every PlugData device
in Bitwig. Make every connected Grid and Arc dark. Then run:

```sh
./tools/macos_serialosc_lease_candidate.sh activate
./tools/macos_serialosc_lease_candidate.sh verify
```

Activation is allowed only when the accepted stable service is already
running and available as rollback. It stops that service, starts the separate
candidate job, and verifies exact program path, PID, and sole ownership of UDP
`12002`. If candidate activation does not verify, the script automatically
restores the accepted service.

Service labels:

```text
stable:    com.kasselvania.plugdata-monome.serialosc
candidate: com.kasselvania.plugdata-monome.serialosc-lease-candidate
```

The switch restarts SerialOSC device workers. It does not delete device
preferences or either set of binaries.

## Restore the accepted service

```sh
./tools/macos_serialosc_lease_candidate.sh restore-stable
```

This stops and disables the candidate, re-enables the existing stable
LaunchAgent, and verifies that its PID alone owns UDP `12002`. Candidate files
remain available for inspection and another bounded run.

## Acceptance sequence

Candidate service verification proves only process identity and discovery-port
ownership. Hardware acceptance remains separate:

1. read-only discovery and lease-capability readback;
2. one direct daemon expiry run that lights a free device, deliberately omits
   renew/release, and verifies free port `0` afterward;
3. standalone PlugData claim, renewal, output/input, orderly release, and
   expiry after forced client termination;
4. one Grid, the other Grid, the Arc, and then all three together;
5. hot-unplug and reconnect in each direction while surviving leases remain;
6. Bitwig CLAP editor close/reopen and ordinary bypass;
7. full PlugData plug-in-host termination, followed by daemon expiry, hardware
   darkening, and free port-`0` readback; and
8. restoration of the accepted stable service if any gate fails.

The direct read-only and expiry commands are:

```sh
python3 tools/live_serialosc_lease.py probe
python3 tools/live_serialosc_lease.py expiry-test --serial SERIAL
python3 tools/live_serialosc_lease.py expiry-test --serial SERIAL --takeover-legacy
python3 tools/live_serialosc_lease.py expiry-test --serial ARC_SERIAL --arc-rings 4
```

The expiry harness never takes over a legacy or rival leased destination. It
acts automatically only after exact readback says `free` with port `0`.
`--takeover-legacy` is a separately named, explicit authorization for a
verified legacy destination and must be used only after the operator approves
that crossing. It still never replaces a different active lease.

## Accepted direct-daemon slice

On 2026-08-29, candidate revision
`6701959e432665b1d081ca68523966666d53b75a` passed acceptance steps 1 and 2
with physical legacy 128 `m1000853`:

- the candidate was the sole owner of UDP discovery port `12002`;
- a read-only probe reported lease version 1 and the exact legacy destination
  `127.0.0.1:17780`, prefix `/monome`, with no lease owner;
- the operator explicitly approved `--takeover-legacy`;
- a three-second lease was granted and independently read back;
- the complete 16-by-8 surface visibly lit at level 4;
- the harness deliberately sent no renewal and no release;
- `/sys/lease/lost` and the daemon's `lease expired` record were both observed;
- the full physical surface automatically went dark; and
- a separate post-test probe reported `free` at `127.0.0.1:0`, remaining time
  `0`, and owner `0`.

The first physical attempt against the preceding candidate failed closed with
`device_error` before a grant. It exposed a libmonome transport difference:
series writes return zero on success, while mext writes may return a positive
byte count. The candidate now treats only negative Grid or Arc write results as
failures. Its deterministic C suite passed before the corrected physical run.
At no point did the failed attempt overwrite the verified legacy destination.

This record does not accept PlugData standalone, Bitwig, the zero Grid, the
Arc, simultaneous devices, or Steam Deck. Those gates remain in the sequence
above.

## Accepted standalone legacy-128 slice

Also on 2026-08-29, the installed PlugData 0.9.4 candidate opened
`monome-grid-live.pd` through macOS LaunchServices. This unattended run
established the following narrower evidence:

- no PlugData or Bitwig host was running before launch;
- the patch bound only its expected local ports `17779`, `17780`, `17781`, and
  `17900`;
- opening the patch did not claim the free Grid;
- discovery, explicit index selection, and probe left the Grid free at port
  `0`;
- explicit claim produced a lease at `127.0.0.1:17780`;
- independent reads spanning longer than the original six-second TTL remained
  leased and showed the remaining time reset upward, proving renewal;
- orderly PlugData release returned an independently verified free port `0`;
- a second claim was followed by `SIGKILL` of the exact PlugData process opened
  for the test;
- immediate readback after process death remained leased, proving that no
  orderly release had run; and
- after the lease deadline, independent readback reported free port `0`, the
  daemon log recorded expiry, and the candidate remained the sole healthy owner
  of discovery port `12002`.

An attended continuation then completed the physical I/O boundary:

- PlugData lit the full 16-by-8 surface at level 4;
- it independently raised the top-left LED to level 15;
- the user confirmed both physical patterns;
- PlugData's console recorded exact top-left `key 0 0 1` and `key 0 0 0`
  events while lease renewals continued;
- orderly release visibly darkened the entire Grid before independent free
  port-`0` readback;
- PlugData reclaimed and relit the full surface for the process-death run;
- `SIGKILL` left the destination leased immediately after client death;
- the full Grid remained lit briefly, then visibly went completely dark by
  itself on lease expiry; and
- final independent readback reported free port `0`, while the candidate
  remained the sole healthy discovery owner.

Together, the unattended control-plane and attended physical runs accept the
legacy-128 PlugData standalone lifecycle: explicit selection, non-mutating
probe, claim, renewal, output, input, orderly dark/release, and abrupt-client
expiry with automatic hardware darkening. They do not accept Bitwig, the zero
Grid, Arc, simultaneous devices, or Steam Deck.

## Accepted standalone zero-Grid slice

On 2026-08-29, physical zero Grid `m23215901` passed the equivalent isolated
PlugData standalone lifecycle in OSC/SerialOSC mode:

- discovery identified `monome zero` and lease version 1 while free at port
  `0`;
- loading the workbench did not auto-claim;
- explicit selection and probe remained non-mutating;
- explicit claim verified callback port `17780` and renewed beyond the original
  TTL;
- all 256 LEDs visibly lit at level 4;
- the bottom-right LED independently rose to level 15, proving 16-by-16
  addressing;
- PlugData printed exact `key 15 15 1` and `key 15 15 0` input;
- orderly release visibly darkened the complete surface before independent
  free port-`0` readback;
- a second full-surface pattern remained lit immediately after `SIGKILL`
  terminated only the test PlugData process; and
- the zero Grid then visibly went completely dark by itself on lease expiry,
  after which independent readback reported free port `0` and the candidate
  remained healthy.

This accepts the isolated zero-Grid standalone lease lifecycle. It does not
accept Arc, simultaneous devices, Bitwig, or Steam Deck.

## Arc detector correction

The initial Arc gate exposed a separate macOS discovery defect, not a lease
failure. macOS listed physical Arc `m1001113` at
`/dev/tty.usbserial-m1001113`, but the candidate did not create its device
worker. The detector passed one mutable IOKit property-buffer length through
the whole enumeration. Earlier, shorter modem paths reduced that in/out length,
so the later, longer FTDI Arc path could not be read.

SerialOSC revision `7187832c349202b1a94a9b10080ae57d40069946` resets the
buffer length for every enumerated device and requires a successful property
read before dispatching a connection. Its native ARM64 build and complete CTest
suite passed. The rollback-safe candidate manager installed it in its own
revision root, activated it as the sole owner of UDP `12002`, and immediately
discovered `m1001113` on device-server port `18226`. The earlier `6701959`
physical Grid records remain historical evidence for the lease core; the
current candidate pin is `7187832`.

## Accepted standalone Arc slice

On 2026-08-29, physical four-ring Arc `m1001113` passed the isolated PlugData
standalone lease lifecycle against corrected candidate `7187832`:

- opening `monome-arc-live.pd` bound control port `17901`, discovery callback
  `17778`, and Arc callback `17782` without auto-claiming;
- explicit discovery, selection, and probe preserved the verified legacy
  destination at `127.0.0.1:17782`;
- after explicit operator approval, takeover produced a version-1 lease on
  callback `17782` and independent readback proved renewal beyond the original
  six-second TTL;
- all four rings visibly lit at level 4, with distinct ring `0`/position `0`
  and ring `3`/position `63` markers;
- PlugData printed positive encoder deltas for ring `0` and negative deltas for
  ring `3`; this physical Arc has no buttons;
- orderly release visibly darkened all four rings before independent free
  port-`0` readback;
- a fresh lease and full-ring pattern remained active immediately after
  `SIGKILL` terminated only the verified PlugData process; and
- after the deadline, all four rings visibly went dark by themselves and
  independent readback reported free port `0`.

The daemon log independently recorded the takeover grant, orderly release,
fresh grant, and expiry. The candidate remained the sole healthy owner of UDP
`12002`. This accepted the isolated Arc standalone lease lifecycle. At that
point the simultaneous-device matrix, Bitwig process death, and every Steam
Deck lease gate remained open.

## Accepted simultaneous three-device slice

Also on 2026-08-29, corrected candidate `7187832` passed the complete
standalone PlugData matrix with zero `m23215901`, legacy 128 `m1000853`, and
four-ring Arc `m1001113`:

- one fresh PlugData process opened both live workbenches, bound their seven
  distinct loopback ports, and did not auto-claim;
- explicit selection and non-mutating probes verified zero `16×16`, legacy
  `16×8`, and Arc `0×0` before any claim;
- all three leases renewed simultaneously beyond the original TTL on callback
  ports `17780`, `17781`, and `17782`;
- full-zero, single-legacy-position, and four-ring patterns were visibly
  isolated, while exact zero and legacy key events and positive Arc ring-`1`
  deltas reached only their assigned sessions;
- active removal of each device left both surviving patterns and leases
  unchanged in the same PlugData process;
- every reconnect restored the same stable ID as free on port `0`. PlugData
  reported `no_device_selected` until explicit reselection, exact reprobe,
  reclaim, and pattern restore;
- independent orderly releases darkened and freed legacy, Arc, then zero while
  preserving each remaining lease; and
- after all three were freshly reclaimed and relit, `SIGKILL` of the exact
  shared PlugData process left all three immediately leased. The daemon expired
  every abandoned lease after its deadline, both Grids and all four Arc rings
  visibly darkened by themselves, and independent readback found all three free
  on port `0`.

The candidate log independently recorded all grants, device-worker reconnects,
orderly releases, and final expiries while the candidate remained the sole
healthy owner of UDP `12002`. This accepts the macOS PlugData-standalone
simultaneous-device and shared-process-death lifecycle. At the end of that
slice, Bitwig process death and every Steam Deck lease gate remained open.

## Accepted Bitwig shared-host process-death slice

On 2026-08-31, candidate `7187832` passed the remaining macOS Bitwig gate with
the pinned PlugData CLAP candidate at commit `98ae0f78`:

- one isolated Bitwig host loaded both live patches without auto-claiming;
- explicit non-mutating probes established menu indices `0` legacy 128, `1`
  Arc, and `2` zero before use;
- legacy, zero, and Arc renewed simultaneous leases on `17780`, `17781`, and
  `17782` beyond the six-second TTL;
- the operator confirmed distinct visible output across both Grids and all
  four Arc rings, and legacy input reached only its assigned session;
- full Bitwig device deactivation terminated the exact shared PlugData host
  without running an orderly release;
- the daemon recorded three expiries, both Grids and every Arc ring visibly
  auto-darkened, and independent readback found all three free on port `0`;
- reactivation created a fresh host with empty selections and no claims;
- explicit reprobe/reclaim restored all three leases, successful heartbeat
  acknowledgements stayed silent in the console, and zero plus Arc input
  remained isolated; and
- final orderly release returned every device to free port `0`.

This accepts macOS crash-safe Bitwig host termination for the pinned candidate
pair. It does not transfer to arbitrary builds. At the time of this macOS run,
every Steam Deck lease gate remained open. The later exact x86-64 candidate run
closed only the bounded legacy direct-protocol and complete single-device
standalone slice, including hotplug and host death; the remaining Deck matrix
still prevents a complete cross-platform crash-safety or end-user packaging
claim. See `docs/STEAMOS-LEASE-CANDIDATE.md`.
