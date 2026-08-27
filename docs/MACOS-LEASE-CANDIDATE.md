# macOS SerialOSC lease candidate

The lease daemon is installed beside the accepted null-port-safe SerialOSC
build. It has a different binary root, LaunchAgent label, log, metadata file,
and checksum manifest. Preparing it does not stop or replace the running
stable service.

Pinned source:

- repository: `kasselvania/serialosc`;
- revision: `65ca6c2ff4d8589c5e75d5e8b4e9cd38bec96bec`;
- reported version: `serialoscd 1.4.8 (65ca6c2)`; and
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
  serialosc-lease-candidate/65ca6c2/
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
2. standalone PlugData claim, renewal, output/input, orderly release, and
   expiry after forced client termination;
3. one Grid, the other Grid, the Arc, and then all three together;
4. hot-unplug and reconnect in each direction while surviving leases remain;
5. Bitwig CLAP editor close/reopen and ordinary bypass;
6. full PlugData plug-in-host termination, followed by daemon expiry, hardware
   darkening, and free port-`0` readback; and
7. restoration of the accepted stable service if any gate fails.

No crash-safe or cross-platform claim is earned until this Mac sequence and
the corresponding Steam Deck sequence both pass physically.
