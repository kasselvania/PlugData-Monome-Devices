# SerialOSC lease workbench

The fake SerialOSC device server implements the proposed version 1 leased
application-destination protocol from the
[`kasselvania/serialosc`](https://github.com/kasselvania/serialosc/blob/feature/leased-destinations/docs/leased-destinations.md)
fork.

This is the executable contract for the daemon and PlugData changes. The fork
worker and opt-in `monome-session` policy now implement it. The pinned macOS
candidate and the separately packaged SteamOS candidate run the lease daemon
while their accepted stable rollback installations remain preserved. The
publicly accepted Steam Deck package is still the non-lease 1.4.7 build until
the candidate completes its own physical matrix.

## Covered behavior

The deterministic fake-server suite proves:

- versioned `free`, `legacy`, and `leased` state readback;
- acquisition only from a free destination;
- explicit takeover of a legacy destination;
- dark-before-grant and non-persistence of the leased callback;
- same-token idempotent acquisition;
- refusal of a different token and changed same-token settings;
- explicit callback replies for renew and release;
- token-guarded renewal and release;
- expiry even when no OSC or hardware event arrives;
- dark-before-free ordering for Grid and two- and four-ring Arc;
- rejection of a late renewal after expiry;
- legacy `/sys/*` displacement without adding darkening to legacy behavior;
  and
- fail-closed TTL validation.

Run the focused contract:

```sh
python3 -m unittest -v tests/fake_serialosc_spec.py
```

The test uses only loopback UDP and simulated LED state. It never opens USB
hardware or live SerialOSC discovery port `12002`.

The PlugData state-machine suite proves the corresponding client boundary:

```sh
lua tests/lease_session_spec.lua
```

It covers capability probing, fail-closed unsupported behavior, acquisition,
explicit legacy takeover, rival refusal, grant readback, renewal and renewal
timeout, token rejection, lost notification, release, and independent
free-state verification. `monome-session` remains legacy by default; the live
Grid and Arc workbench slots explicitly send `protocol lease` at load so the
A/B boundary stays visible.

`tools/live_serialosc_lease.py` carries the same fail-closed boundary into
physical acceptance. Its default `probe` is read-only. The separately named
`expiry-test` refuses anything except a verified free device, sends a bounded
map only after a grant and owner readback, omits renewal/release on purpose,
and then requires free port-`0` readback after the deadline. The independent
`renew-release-test` renews beyond the initial TTL, requires an owned-lease
readback after that boundary, sends a token-guarded release, and requires a
separate free port-`0` readback. Its defaults match the PlugData policy: a
6000 ms TTL, 2000 ms renewal interval, and 8000 ms hold.

## Physical acceptance boundary

On 2026-08-29, the pinned macOS candidate at SerialOSC revision `6701959e`
passed one direct-daemon expiry run with physical legacy 128 `m1000853`. The
read-only probe first reported lease version 1 in `legacy` mode at
`127.0.0.1:17780`. After explicit operator approval, the harness crossed that
boundary with `--takeover-legacy`, verified the grant, lit the full Grid at
level 4, and deliberately omitted renewal and release. The client observed
`/sys/lease/lost`; the daemon recorded `lease expired`; the user confirmed the
full surface lit dimly and then went completely dark; and a separate probe
reported `free`, port `0`, and owner `0`.

That run also verifies the corrected libmonome result boundary: Grid and Arc
writes fail only on a negative result. Positive mext byte counts are successful
writes. The earlier candidate rejected this physical Grid because it treated
every nonzero result as failure; it never granted that attempted lease and
preserved the legacy destination.

The same day, an unattended PlugData standalone control-plane run passed. The
live Grid patch opened through LaunchServices, bound only its expected local
ports, and did not auto-claim. Explicit probe remained non-mutating. Explicit
claim produced a lease at port `17780`; independent state reads spanning more
than the original six-second TTL proved renewal; and orderly release returned
free port `0`. A second claim followed by `SIGKILL` of the exact test-owned
PlugData process stayed leased immediately after death, then expired to free
port `0`. The daemon log independently recorded grant, release, grant, and
expiry.

An attended continuation completed the legacy-128 standalone physical gate.
PlugData-routed output visibly lit the full 16-by-8 surface at level 4 and made
the top-left LED independently bright. PlugData printed exact `key 0 0 1` and
`key 0 0 0` events while lease renewals continued. Orderly release visibly
darkened the complete surface before independent free port-`0` readback. A
final full-surface pattern remained lit immediately after `SIGKILL` proved the
client had not released; it then went completely dark on daemon expiry, with a
separate probe again reporting free port `0`.

The physical zero Grid `m23215901` then passed the equivalent isolated
standalone lifecycle in OSC/SerialOSC mode. The accepted evidence includes
16-by-16 readback, all-256 output, independent bottom-right output, exact
bottom-right press/release input, renewal, orderly all-dark release to port
`0`, and a second lit lease that automatically darkened and became free after
`SIGKILL` terminated PlugData.

Current candidate revision `7187832` then corrected the macOS detector's reuse
of a shortened IOKit serial-property buffer length, which had hidden the later,
longer FTDI path for Arc `m1001113`. With discovery restored, that four-ring Arc
passed explicit legacy takeover, renewal, all-ring and isolated-position output,
positive ring-`0` and negative ring-`3` encoder input, orderly all-dark release,
and automatic all-dark expiry after `SIGKILL` terminated PlugData. Independent
readback ended at free port `0`, and the daemon recorded takeover, release,
fresh grant, and expiry.

The complete simultaneous standalone matrix then passed with zero, legacy 128,
and Arc in one PlugData process. Three renewable callbacks stayed isolated;
output and input routing passed; and every hot-unplug left both survivors
unchanged. Each reconnect returned as the same stable ID at free port `0` and
required explicit reselection, reprobe, and reclaim. Independent releases
passed. After a final `SIGKILL`, all three leases remained active briefly, then
expired independently and visibly darkened every surface before free port-`0`
readback.

Bitwig plug-in-host termination passed on macOS on 2026-08-31: the shared host
died without release, all three leases expired, every surface auto-darkened,
and a fresh host started fail-closed before explicit reclaim.

The exact x86-64 SteamOS candidate then passed corresponding bounded
single-device lanes with the legacy 128, Zero/256, and four-ring Arc. Each
device proved fail-closed startup, renewal beyond the first TTL, exact
input/output, orderly dark release, automatic darkness and free port `0` after
abrupt PlugData death, fresh fail-closed recovery, and active-lease
unplug/reconnect followed by dark/free refusal before explicit reselection and
reclaim. The legacy-plus-Zero simultaneous lane then passed isolated routing,
both hotplug directions, independent release, shared-host expiry, and fresh
fail-closed recovery. The legacy-plus-Arc lane then passed isolated Grid/ring
output and input, both hotplug directions, independent release, and reciprocal
process-isolation expiry/recovery. Because that lane used separate Grid and
Arc PlugData processes, it does not satisfy the all-device shared-host-death
gate. The Zero-plus-Arc functional lane then passed isolated routing, both
removal directions, independent release, and reciprocal process isolation.
Arc reconnect preserved Zero unchanged. Zero reconnect physically reset and
re-enumerated Arc through the dock in both port orientations; SerialOSC
returned both stable IDs dark/free and recovered them only after explicit
action. That is a documented Zero-boot dock/power boundary, not an
uninterrupted-survivor claim. SerialOSC did not restart. Three-device, Bitwig,
and the remaining Deck lifecycle rows remain open, so no complete
cross-platform release claim is earned yet. See
[MACOS-LEASE-CANDIDATE.md](MACOS-LEASE-CANDIDATE.md) and
[STEAMOS-LEASE-CANDIDATE.md](STEAMOS-LEASE-CANDIDATE.md).
