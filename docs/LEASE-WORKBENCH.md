# SerialOSC lease workbench

The fake SerialOSC device server implements the proposed version 1 leased
application-destination protocol from the
[`kasselvania/serialosc`](https://github.com/kasselvania/serialosc/blob/feature/leased-destinations/docs/leased-destinations.md)
fork.

This is the executable contract for the daemon and PlugData changes. It does
not claim that the installed macOS or Steam Deck SerialOSC service supports
leases yet.

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

## Remaining boundary

The production SerialOSC worker, PlugData `monome.session`, macOS service,
Bitwig lifecycle, Steam Deck installer, and physical devices still use the
legacy destination protocol. Those layers gain no lease claim until they pass
their own implementation and acceptance steps.
