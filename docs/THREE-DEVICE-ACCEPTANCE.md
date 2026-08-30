# Three-device physical acceptance

The standalone PlugData workbench passed simultaneous physical acceptance with
two Grids and one Arc on 2026-08-26. This record covers routing, ownership,
active hot-unplug recovery, and independent release across all three devices.
It does not cover Bitwig or standalone-versus-plugin contention.

## Accepted environment

- PlugData standalone: official 0.9.4 nightly, commit `6bb2b60c8`;
- SerialOSC: pinned Apple-silicon build from source commit `ff53885`, with the
  project's null-port guards, running as the installed user LaunchAgent;
- Grid workbench: `monome-grid-live.pd`;
- Arc workbench: `monome-arc-live.pd`.

Both live patches were open in the same PlugData process. Their loopback ports
were deliberately separate:

| Device | Stable ID | Reported shape | Workbench route |
| --- | --- | --- | --- |
| zero Grid | `m23215901` | 16 by 16 | Grid slot A, callback `17780` |
| legacy 128 | `m1000853` | 16 by 8 | Grid slot B, callback `17781` |
| four-ring Arc | `m1001113` | Arc `/sys/size 0 0` | Arc session, callback `17782` |

Grid and Arc discovery used callbacks `17779` and `17778`; their live-control
ports were `17900` and `17901`.

## Accepted sequence

1. A non-mutating probe reported destination port `0` for every device.
2. Each stable ID was explicitly selected, claimed on its assigned callback,
   and verified by exact `/sys/info` readback. All three claims remained valid
   simultaneously.
3. Output routing was visibly distinct: the zero displayed a full dim surface,
   only the legacy Grid's bottom-right LED was bright, and all four Arc rings
   were evenly lit.
4. Input routing was isolated: zero top-left press/release produced only slot-A
   `key 0 0 1/0`; legacy bottom-right press/release produced only slot-B
   `key 15 7 1/0`; clockwise motion on Arc ring `1` produced only positive
   `delta 1 ...` events.
5. Fresh ownership checks passed for all three sessions while they were active.
6. Each device was actively unplugged and reconnected in turn. Only the removed
   device detached; both survivors kept their visible state and passed fresh
   ownership checks. The returning device kept the same stable ID, was
   re-probed, explicitly reclaimed, and restored without disturbing either
   survivor.
7. Arc, zero, and legacy reconnects retained their own prior callback in
   SerialOSC. The workbench treated the missing device as locally detached and
   fail-closed, then recovered through stable-ID selection, fresh probe, and an
   explicit verified claim. No rival destination was overwritten.
8. The sessions released independently: legacy first, Arc second, and zero
   last. Each capability sent its dark cleanup before its session was released;
   the remaining sessions stayed verified until their own release.
9. Final non-mutating probes reported port `0` for all three devices, and both
   Grids plus all four Arc rings were physically confirmed dark.

This also accepts the standalone Grid-plus-Arc survivor combinations: removing
the zero left the legacy 128 plus Arc verified, and removing the legacy 128 left
the zero plus Arc verified. Removing the Arc left both Grids verified.

## Lease-candidate record

On 2026-08-29, the same hardware passed the opt-in lease matrix with PlugData
0.9.4 candidate `98ae0f78` and SerialOSC candidate `7187832`:

1. Both live patches opened in one fresh PlugData process. It alone bound the
   seven expected loopback ports: Grid control/discovery/session ports `17900`,
   `17779`, `17780`, and `17781`, plus Arc control/discovery/session ports
   `17901`, `17778`, and `17782`. Opening the patches did not auto-claim.
2. Independent readback found all three lease-capable devices free on port `0`.
   The registry's observed menu mapping was explicitly probed before use: zero
   at index `2`, legacy at index `0`, and Arc at index `1`. Initial wrong-slot
   probes remained non-mutating and exposed their actual model/shape before the
   assignments were corrected.
3. Zero, legacy, and Arc then held simultaneous renewable leases on `17780`,
   `17781`, and `17782`. A readback after more than the original six-second TTL
   showed every lease refreshed independently.
4. Output remained isolated: all 256 zero LEDs were dim, only legacy position
   `(15,7)` was bright, and all four Arc rings were dim. Input remained
   isolated: zero produced only slot-A `key 0 0 1/0`, legacy produced only
   slot-B `key 15 7 1/0`, and clockwise motion on Arc ring `1` produced only
   positive `delta 1 ...` events.
5. Legacy, zero, and Arc were actively unplugged and reconnected one at a time.
   Each removal deleted only that device while both survivors kept their exact
   visible patterns, renewed their leases, and stayed in the same PlugData
   process.
6. Every device returned with the same stable ID and a fresh, non-persisted
   free destination at port `0`. Its PlugData session reported
   `no_device_selected` until the operator explicitly reselected the stable-ID
   entry, reprobed the exact model and shape, reclaimed the assigned callback,
   and restored the visible pattern. Neither survivor changed.
7. Orderly release of legacy, then Arc, then zero darkened only the released
   surface, returned it to free port `0`, and preserved every still-owned
   survivor. Final readback found all three free, and all hardware was visibly
   dark.
8. All three were freshly reclaimed and relit, then the exact shared PlugData
   process was terminated with `SIGKILL`. Immediate readback still showed all
   three leases and their distinct callback ports with roughly four seconds
   remaining. After the deadline, all three independently reported free port
   `0`; both Grids and all four Arc rings visibly went dark by themselves.

The candidate daemon log independently recorded each grant, USB-worker
disconnect/reconnect, orderly release, fresh grant, and final expiry. This
accepts the complete macOS PlugData-standalone multi-device lease lifecycle. It
does not accept Bitwig process death or any Steam Deck lease behavior.

## Boundary

SerialOSC destination ownership is cooperative state verified through
`/sys/info`; it is not an atomic operating-system lock. This run proves the
workbench detects and verifies the destination it owns, detaches on removal,
and does not claim a rival destination as its own.

## Separate Bitwig companion record

The pinned PlugData candidate at commit `98ae0f78` subsequently completed a
separate Bitwig CLAP physical run with these same three stable IDs. That run
covered stopped transport, ordinary bypass, save/reload, one device, both
Grids, all three devices, active removal/recovery in every direction,
standalone displacement, safe release refusal by the displaced Bitwig session,
fresh reclaim, and final all-dark port-`0` cleanup.

The evidence remains separate because the host and callback assignment differ
from this standalone record. Bitwig's full device-deactivation/process-restart
gate failed: terminating the isolated host left a stale SerialOSC destination
and lit hardware. See `docs/PLUGDATA-BITWIG-AB.md` for the exact accepted
surface and the unresolved lifecycle gap.
