# SteamOS lease-candidate acceptance

This is the bounded physical record for the x86-64 SteamOS build of the
SerialOSC leased-destination fork. It is not a release-promotion claim.

## Exact authority

The 2026-08-31 run used:

- SteamOS `3.8.16` on x86-64 with `steamos-readonly` still enabled;
- SerialOSC source revision
  `7187832c349202b1a94a9b10080ae57d40069946`, reporting
  `serialoscd 1.4.8 (7187832)`;
- Steam Deck packaging commit
  `33fda574524dc495fd0eb8ce364d72a8bf437d1d`;
- pinned candidate executable hashes:
  - `cb43323035fbf7098fa3caa8a0f46ab191dac3925586478e653b7a63b40d969a`
    for `serialoscd`;
  - `5d7e47954bc1a40c06350f14c07b9d96a9b7b96357e24b9e15ba4c48c6541db3`
    for `serialosc-detector`; and
  - `59ec189e4ed2573ffa7c44d7b06538a2a1bab87e61db0d7b5bda487a86e124b1`
    for `serialosc-device`;
- the official Debian x64 PlugData `0.9.4` nightly identified by download
  metadata commit `1c83c0c08c5a3d8d33f27b632e9772726ef56098`, with archive SHA-256
  `c31cd38f5317ea9e97ca6a8cfab0b63c2d0a0d03574238936afd7c36385a2ae3`;
- this workbench at commit
  `4ad7d9c7451c4e6aac708e8f32730e29ead3efa6`; and
- legacy Grid `m1000853`, reported as `monome 128` with a 16-by-8 surface.

The PlugData build was the compatible Debian artifact. The contemporaneous
Arch nightly required newer glibc symbols than both the SteamOS host and
Bitwig Flatpak runtime and was not installed.

## Passed slices

The rootless candidate installation, its exact build receipt, its binary
hashes, the active user service, and UDP discovery passed verification while
SteamOS remained read-only. The legacy Grid then passed the traditional-client
compatibility lane and the direct lease protocol lanes:

- read-only lease capability and state probing;
- explicit refusal of an unapproved legacy takeover;
- operator-approved takeover followed by autonomous expiry and visible
  darkness;
- renewal beyond the initial 6000 ms TTL;
- token-guarded release; and
- independent `free` state at `127.0.0.1:0` after expiry and release.

The legacy Grid also passed the attended PlugData standalone no-unplug and
host-death slice:

1. Fresh PlugData startup bound its callbacks but left the Grid dark and free.
2. Explicit selection and probe remained non-mutating.
3. Explicit claim leased callback `17780`; renewals kept the lease alive beyond
   its first TTL.
4. PlugData lit all 128 LEDs and emitted exact machine-readable top-left input
   events `a_key 0 0 1` and `a_key 0 0 0`.
5. Orderly release visibly darkened the Grid before independent free port-`0`
   readback.
6. On a second lit lease, `SIGKILL` terminated only the test-owned PlugData
   process. Immediate readback remained leased; SerialOSC then logged
   `lease expired`, visibly darkened the Grid, and returned it to free port
   `0` without restarting the daemon.
7. A fresh PlugData process again started dark and free, required explicit
   reselection/probe/claim, lit successfully, and completed a final orderly
   dark release.

The evidence session retained separate snapshots labeled:

- `legacy-plugdata-standalone-orderly-passed`;
- `legacy-plugdata-standalone-host-death-passed`; and
- `legacy-plugdata-standalone-restart-recovery-passed`.

`serialoscd.service` remained active with `NRestarts=0` throughout these
PlugData slices.

The same live PlugData process then passed the legacy-Grid hotplug continuation:

1. The Grid held a renewable lease and a distinct dim-surface/bright-corner
   pattern before unplug.
2. Removal produced the exact stable-ID notification, removed only the device
   worker, and freed device port `16874`; PlugData and SerialOSC stayed active.
3. Reconnect restored `m1000853` on the same device port, but its lease state
   was free at port `0` and the surface stayed dark.
4. An output command before reselection and claim left the device free and
   physically dark.
5. Explicit reselection, non-mutating probe, and claim restored callback
   `17780` and the exact prior pattern.
6. Orderly release again produced visible full darkness and independent free
   port-`0` readback.

That continuation retained snapshots labeled
`legacy-plugdata-hotplug-preclaim-free`,
`legacy-plugdata-hotplug-claimed-lit`,
`legacy-plugdata-hotplug-disconnected`,
`legacy-plugdata-hotplug-reclaimed-lit`, and
`legacy-plugdata-hotplug-passed`.

## Still open on SteamOS

This evidence does not accept the candidate package. The remaining Deck gates
include:

- the isolated Zero/256 lease lifecycle;
- the isolated Arc lease lifecycle;
- Grid/Grid, Grid/Arc, and three-device lease isolation and survivor recovery;
- PlugData CLAP inside Bitwig, including abrupt plug-in-host death and fresh
  fail-closed recovery; and
- the remaining dock, suspend/resume, update, and reboot lifecycle rows called
  for by the Steam Deck hardware protocol.

The previous upstream 1.4.7 package remains the accepted rollback release.
Candidate warnings and the `lease-candidate` channel must remain until the
complete SteamOS matrix passes.
