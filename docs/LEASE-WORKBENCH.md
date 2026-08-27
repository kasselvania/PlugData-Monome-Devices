# SerialOSC lease workbench

The fake SerialOSC device server implements the proposed version 1 leased
application-destination protocol from the
[`kasselvania/serialosc`](https://github.com/kasselvania/serialosc/blob/feature/leased-destinations/docs/leased-destinations.md)
fork.

This is the executable contract for the daemon and PlugData changes. The fork
worker and opt-in `monome-session` policy now implement it; the installed
macOS and Steam Deck SerialOSC services do not support leases yet.

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

## Remaining boundary

The fork worker and PlugData session are implemented but have not yet replaced
either installed service. No physical device, PlugData standalone process,
Bitwig plug-in host, or Steam Deck service has passed the lease candidate.
Those layers gain no crash-safe claim until their own readback and
process-death acceptance steps pass.
