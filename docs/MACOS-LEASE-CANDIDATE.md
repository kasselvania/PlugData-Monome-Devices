# macOS SerialOSC lease candidate

The lease daemon is installed beside the accepted null-port-safe SerialOSC
build. It has a different binary root, LaunchAgent label, log, metadata file,
and checksum manifest. Preparing it does not stop or replace the running
stable service.

Pinned source:

- repository: `kasselvania/serialosc`;
- revision: `6701959e432665b1d081ca68523966666d53b75a`;
- reported version: `serialoscd 1.4.8 (6701959)`; and
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
  serialosc-lease-candidate/6701959/
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

No crash-safe or cross-platform claim is earned until this Mac sequence and
the corresponding Steam Deck sequence both pass physically.
