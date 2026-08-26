# PlugData Monome Device Layer

## Product boundary

This is a PlugData-first project. Vanilla Pure Data compatibility is explicitly
out of scope.

PlugData patches provide OSC transport and visible UI. Pd-Lua is the preferred
tool for stateful logic such as device registries and LED framebuffers because
it is bundled with PlugData and works in its standalone and plugin builds.
Native third-party externals are not part of the design.

The stable device ID reported by SerialOSC is identity. Discovery order, USB
path, device-server port, and menu index are not identity.

## Non-negotiable behavior

- Discovery never claims a device.
- A device is claimed only after explicit user selection and `claim`.
- No device is silently replaced because another device was added or removed.
- Connection truth comes from SerialOSC readback, not a button or menu label.
- SerialOSC has one outgoing application destination per device but no atomic
  lock. The UI therefore says **claimed** or **displaced**, never **locked**.
- Every internal Pd send/receive is instance-scoped; global names are forbidden.
- Grid and Arc capabilities have separate output paths.
- Demos consume the public device API and never manage SerialOSC themselves.

## Architecture

```text
SerialOSC discovery :12002
          |
    monome.discovery
          |
    monome-registry ------> PlugData popmenu + status
          |
     explicit select
          |
     monome.session
       /        \
monome.grid   monome.arc
       \        /
      applications and demos
```

### `monome.discovery`

Owns the discovery callback, sends `/serialosc/list` and
`/serialosc/notify`, re-arms the one-shot notification after every add/remove,
and forwards records to the registry. It does not send `/sys/host`,
`/sys/port`, or `/sys/prefix`.

Because `/serialosc/list` has no end marker, a rescan is a bounded collection
window: `scan_begin`, zero or more device replies, then `scan_end`. Only
`scan_end` may sweep records that were not seen.

### `monome-registry`

Maintains deterministic records keyed by serial ID. It preserves selection by
ID across scan order changes and emits menu projection data. It does not open
ports, infer ownership, or communicate with hardware.

### `monome.session`

Implements one selected device lifecycle:

```text
absent -> available -> probing -> available
             |
             +------> claiming -> connected
                                   |       |
                    check mismatch|       |verified release
                                   v       v
                              displaced  available
                                   |
                          release intent -> available
```

It probes `/sys/info` before claiming, changes host/port/prefix only during an
explicit claim, verifies readback, detects displacement, and releases only if
it is still the current destination. A verified release sends `/sys/port 0`;
it does not delete SerialOSC preferences. Grid and Arc capability owners must
darken their valid surfaces before requesting release rather than making the
generic session layer guess an LED protocol.

### `monome.grid`

Normalizes key events and `/sys/size`. LED state is buffered as a maximum
16-by-16 surface and dirty 8-by-8 level maps are flushed at a bounded frame
rate. A 128 and a 256 use the same API.

### `monome.arc`

Normalizes encoder delta/key events and owns one 64-level framebuffer per
ring. Dirty rings are emitted with `/ring/map` at a bounded frame rate.

## Public message contract

The final `monome-device` abstraction will accept:

```text
rescan
select <serial-id>
deselect
probe
claim
check
release
prefix <osc-prefix>
rotation <0|90|180|270>
```

It will produce three streams:

1. normalized Grid or Arc input events;
2. status and lifecycle events;
3. selected-device metadata.

The status projection must show state, serial ID, model, capability, device
server port, local callback port, prefix, dimensions/ring count, last event,
and any displacement reason.

## Stepped delivery

### Step 0 — Workbench and state core

- Use a supported native SerialOSC on the development Mac.
- Quarantine the inherited first-device patches.
- Implement and unit-test the identity-based registry.

Acceptance: registry tests pass; no code in this step sends a claim.

### Step 1 — Discovery tracer bullet

- Build a configurable fake SerialOSC discovery server.
- Bind a real callback port and surface bind failure.
- Populate a PlugData `popmenu` from registry projection events.
- Re-arm notifications and preserve selection through add/remove/rescan.

Acceptance: simulated two-device discovery, reordering, duplicate replies,
unrelated removal, selected removal, and callback collision all have explicit
deterministic results.

Status on 2026-08-25: complete on the accepted official PlugData 0.9.4 nightly
at commit `6bb2b60c8`. Discovery transport, notification re-arm, registry
behavior, selected removal, hot-add, callback collision, and dynamic
`else/popmenu` population/output pass. Stable 0.9.3 retains a known menu
failure and is not the current workbench basis. Real SerialOSC's full
add/remove tuples are represented by the fake server and normalized before
registry mutation. See `docs/DISCOVERY-WORKBENCH.md`.

### Step 2 — Explicit session lifecycle

- Probe with `/sys/info` without claiming.
- Implement `claim`, verified readback, displacement detection, and release.
- Prevent two sessions in one PlugData process from claiming the same serial.

Acceptance: a second app can displace the first, and the first reports
`displaced` rather than claiming it remains connected.

Status on 2026-08-25: complete against isolated fake device servers and the
accepted PlugData nightly standalone. Non-mutating probe, verified claim,
periodic readback, simulated external displacement, release refusal after
displacement, verified `/sys/port 0` release, callback collision, and
process-local duplicate claim refusal pass. The same probe, exact claim
readback, and verified release
also pass on a physical legacy 128 and modern 16-by-16 zero Grid. Arc,
multi-device, and Bitwig session acceptance remain open. See
`docs/SESSION-WORKBENCH.md`.

### Step 3 — Grid capability

- Normalize key input and dynamic dimensions.
- Add a level framebuffer and bounded map flushing.
- Validate legacy 128 and modern 256 hardware.

Status on 2026-08-25: the Grid core, Pd-Lua bridge, session composition, fake
device framebuffer, and 128/256/dual smoke patches are implemented. Unit and
loopback acceptance cover dynamic 16-by-8 and 16-by-16 surfaces, 0-15 levels,
dirty 8-by-8 map batching, duplicate-key suppression, synthetic held-key
release, capability routing only through a verified session, and
dark-before-release ordering.

The physical legacy 128 passed discovery, explicit selection, 16-by-8
`/sys/info`, verified claim, full-surface and corner brightness, corner key
press/release, all-dark cleanup, verified `/sys/port 0` release, hot-remove,
hot-add, released-state probe, re-claim, and claimed hot-unplug cleanup. The
apparent CalDigit continuity failure was a reproducible upstream SerialOSC
null-port crash after release; the project now carries a narrow source patch
and pinned Apple-silicon service installer. The installed production service
also passed claimed unplug with a physically held key and emitted the required
synthetic release before detach.

The physical modern zero Grid then passed discovery, explicit selection,
16-by-16 `/sys/info`, verified claim, full-surface and opposite-corner
brightness, top-left key press/release, all-dark cleanup, verified release,
released-port readback, held-key claimed unplug with synthetic release,
same-ID hot-add, re-probe, re-claim, bottom-right output, and final orderly
release. This completes Step 3's single-Grid physical acceptance. Grid-pair
removal tests remain part of Step 5. See `docs/GRID-WORKBENCH.md`.

### Step 4 — Arc capability

- Normalize encoder delta/key input.
- Add bounded ring-map flushing and reliable all-dark cleanup.
- Validate the four-ring Arc.

Status on 2026-08-26: the Arc core, Pd-Lua bridge, verified-session
composition, fake device server, automated smoke patch, and dedicated live
workbench are implemented. Unit and loopback acceptance cover explicit two- or
four-ring attachment, 64-position level maps, dirty-ring batching, bounds
validation, delta and optional key normalization, duplicate-key suppression,
synthetic held-key release, stale-buffer clearing, and four all-dark maps
before verified `/sys/port 0` release. The accepted PlugData nightly completed
the fake four-ring lifecycle and input-routing pass with independent all-dark
and port-`0` simulator readback. Physical four-ring Arc acceptance remains
open and is not inferred from the simulator.

### Step 5 — Host and hot-swap acceptance

- Run the same patch in PlugData standalone and Bitwig CLAP.
- Test UI close/reopen, transport stopped, bypass, save/reload, and plugin
  process restart.
- Test one device, pairs, all three devices, removal in each direction, and
  contention between standalone and Bitwig.

Status on 2026-08-26: the physical legacy 128 and zero Grid passed the Grid-pair
slice in PlugData standalone. Both devices held simultaneous verified claims
on separate callback ports, routed distinct LED and key traffic, survived
removal of the other device, restored the removed stable identity in both
directions, and released independently to port `0`. Grid-plus-Arc, all-three,
and all Bitwig lifecycle/contention gates remain open.

### Step 6 — Demos and package

- Grid demo: dynamic 128/256 layout with momentary and latch modes.
- Arc demo: encoder-following animation with bounded refresh.
- Add help patches, release metadata, installation documentation, and a
  `.plugdata` package.

Packaging starts only after standalone and Bitwig physical acceptance pass.

## Current workbench boundary

As of 2026-08-26, this Mac uses the pinned official SerialOSC source at
`ff53885` with the project's two null-port guards, built as native arm64 and
run as a user LaunchAgent. Homebrew supplies the native libraries but its stock
SerialOSC job remains stopped. The older 1.4.1 Intel launch job is preserved
but disabled. Service verification and physical Grid results remain separate
acceptance layers.

The installed PlugData standalone is the official 0.9.4 nightly from successful
run `32892289806`, commit `6bb2b60c8`. It launches, loads the workbench, and
passes the dynamic-menu gate. The installed VST3 remains a separate stale
compatibility lane and no Bitwig plugin claim is made. See
`docs/PLUGDATA-MACOS.md`.

Fake-server acceptance remains the deterministic regression layer. It exposes
the same `/sys/info`, `/sys/host`, `/sys/port`, `/sys/prefix`,
`/sys/rotation`, Grid key, and Grid level-map surfaces without opening USB
hardware or touching live SerialOSC port `12002`.

## Deferred decisions

- Repository license.
- Final `.plugdata` package metadata after inspecting the schema used by the
  release version of PlugData.
- Whether the legacy patches remain in release archives after the new Grid and
  Arc demos replace their educational value.
