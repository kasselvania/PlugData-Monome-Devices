# SerialOSC lease workbench

The fake SerialOSC device server implements the proposed version 1 leased
application-destination protocol from the
[`kasselvania/serialosc`](https://github.com/kasselvania/serialosc/blob/feature/leased-destinations/docs/leased-destinations.md)
fork.

This is the executable contract for the daemon and PlugData changes. The fork
worker and opt-in `monome-session` policy now implement it. A separately rooted
macOS candidate runs the lease daemon while the accepted stable installation
remains preserved; the accepted stable daemon and Steam Deck service do not
support leases.

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
and then requires free port-`0` readback after the deadline.

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

Bitwig plug-in-host termination, the zero Grid, the Arc, the combined-device
matrix, and every Steam Deck lease gate remain open. Those layers gain no
crash-safe claim until their own physical readback and process-death acceptance
steps pass. See
[MACOS-LEASE-CANDIDATE.md](MACOS-LEASE-CANDIDATE.md).
